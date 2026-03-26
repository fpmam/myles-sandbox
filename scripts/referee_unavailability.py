#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


class UnavailabilityError(RuntimeError):
    pass


POLL_INTERVAL = timedelta(minutes=5)
FIRST_ALERT_AFTER = timedelta(minutes=30)
ALERT_CADENCE = timedelta(minutes=30)
MAX_OUTAGE = timedelta(hours=4)


@dataclass(frozen=True)
class Notification:
    subject: str
    body: str
    kind: str


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def parse_time(value: str | None) -> datetime:
    if not value:
        return utc_now()
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(UTC).replace(microsecond=0)


def to_iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_state() -> dict:
    return {
        "status": "healthy",
        "outage_started_at": None,
        "last_polled_at": None,
        "last_alert_at": None,
        "timeout_alert_sent_at": None,
        "recovery_alert_sent_at": None,
        "blocked_ticket_ids": [],
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return default_state()
    return json.loads(path.read_text())


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def _duration_label(duration: timedelta) -> str:
    total_minutes = int(duration.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _blocked_count(state: dict) -> int:
    return len(state.get("blocked_ticket_ids", []))


def register_outage(state: dict, ticket_id: str, now: datetime) -> tuple[dict, list[Notification]]:
    updated = dict(state)
    if updated.get("status") not in {"outage", "timed_out"}:
        updated["status"] = "outage"
        updated["outage_started_at"] = to_iso(now)
        updated["last_alert_at"] = None
        updated["timeout_alert_sent_at"] = None
        updated["recovery_alert_sent_at"] = None
        updated["blocked_ticket_ids"] = []
    if ticket_id not in updated["blocked_ticket_ids"]:
        updated["blocked_ticket_ids"] = sorted([*updated["blocked_ticket_ids"], ticket_id])
    updated["last_polled_at"] = to_iso(now)
    return updated, []


def poll_outage(state: dict, now: datetime, service_available: bool) -> tuple[dict, list[Notification]]:
    updated = dict(state)
    notifications: list[Notification] = []
    updated["last_polled_at"] = to_iso(now)
    if updated.get("status") not in {"outage", "timed_out"}:
        return updated, notifications

    started_at = parse_time(updated.get("outage_started_at"))
    duration = now - started_at
    blocked = _blocked_count(updated)

    if service_available:
        notifications.append(
            Notification(
                kind="recovery",
                subject="Myles referee recovered",
                body=(
                    "Claude Referee availability has recovered.\n\n"
                    f"Blocked tickets resuming: {blocked}\n"
                    f"Outage duration: {_duration_label(duration)}\n"
                    f"Recovered at: {to_iso(now)}"
                ),
            )
        )
        updated.update(default_state())
        updated["recovery_alert_sent_at"] = to_iso(now)
        return updated, notifications

    if duration >= MAX_OUTAGE and updated.get("timeout_alert_sent_at") is None:
        notifications.append(
            Notification(
                kind="timeout",
                subject="Myles referee outage timed out",
                body=(
                    "Claude Referee is still unavailable after the maximum polling window.\n\n"
                    f"Blocked tickets: {blocked}\n"
                    f"Outage duration: {_duration_label(duration)}\n"
                    "Polling has stopped and manual intervention is required."
                ),
            )
        )
        updated["status"] = "timed_out"
        updated["timeout_alert_sent_at"] = to_iso(now)
        return updated, notifications

    if duration < FIRST_ALERT_AFTER:
        return updated, notifications

    last_alert = parse_time(updated.get("last_alert_at")) if updated.get("last_alert_at") else None
    if last_alert is None or now - last_alert >= ALERT_CADENCE:
        notifications.append(
            Notification(
                kind="still_down",
                subject="Myles referee still unavailable",
                body=(
                    "Claude Referee is still unavailable.\n\n"
                    f"Blocked tickets: {blocked}\n"
                    f"Current outage duration: {_duration_label(duration)}\n"
                    f"Last checked at: {to_iso(now)}"
                ),
            )
        )
        updated["last_alert_at"] = to_iso(now)
    return updated, notifications


def send_postmark_email(notification: Notification, recipient: str) -> None:
    token = os.getenv("POSTMARK_SERVER_TOKEN_CODEX_STATUS") or os.getenv("POSTMARK_SERVER_TOKEN")
    sender = os.getenv("POSTMARK_FROM_EMAIL_CODEX_STATUS") or os.getenv("POSTMARK_FROM_EMAIL")
    if not token or not sender:
        raise UnavailabilityError("Postmark env vars are required to send referee unavailability emails")

    payload = {
        "From": sender,
        "To": recipient,
        "Subject": notification.subject,
        "TextBody": notification.body,
        "Tag": "myles-referee-unavailability",
        "MessageStream": "outbound",
    }
    request = urllib.request.Request(
        "https://api.postmarkapp.com/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise UnavailabilityError(f"Postmark send failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise UnavailabilityError(f"Postmark send failed: {exc}") from exc


def record_notifications(
    notifications: list[Notification],
    *,
    recipient: str,
    email_log_path: Path | None,
    send_email: bool,
    now: datetime,
) -> None:
    if email_log_path is not None:
        email_log_path.parent.mkdir(parents=True, exist_ok=True)
    for notification in notifications:
        if send_email:
            send_postmark_email(notification, recipient)
        if email_log_path is not None:
            payload = {
                "at": to_iso(now),
                "to": recipient,
                "kind": notification.kind,
                "subject": notification.subject,
                "body": notification.body,
            }
            with email_log_path.open("a") as handle:
                handle.write(json.dumps(payload) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["outage", "poll"])
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--ticket-id")
    parser.add_argument("--now")
    parser.add_argument("--service-available", action="store_true")
    parser.add_argument("--recipient", default="a@lll.re")
    parser.add_argument("--email-log-path")
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args()

    now = parse_time(args.now)
    state_path = Path(args.state_path).resolve()
    state = load_state(state_path)

    if args.command == "outage":
        if not args.ticket_id:
            raise SystemExit("--ticket-id is required for outage")
        updated, notifications = register_outage(state, args.ticket_id, now)
    else:
        updated, notifications = poll_outage(state, now, args.service_available)

    save_state(state_path, updated)
    record_notifications(
        notifications,
        recipient=args.recipient,
        email_log_path=Path(args.email_log_path).resolve() if args.email_log_path else None,
        send_email=args.send_email,
        now=now,
    )
    print(json.dumps({"state": updated, "notifications": [item.__dict__ for item in notifications]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except UnavailabilityError as exc:
        print(f"referee-unavailability failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
