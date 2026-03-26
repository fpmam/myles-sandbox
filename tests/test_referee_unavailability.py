import json
import subprocess
import sys
from pathlib import Path

from scripts.referee_unavailability import load_state, parse_time, poll_outage, register_outage


ROOT = Path(__file__).resolve().parents[1]


def test_unavailability_alert_starts_at_thirty_minutes() -> None:
    state, notifications = register_outage({}, "MYLES-SYN-001", parse_time("2026-03-25T10:00:00Z"))
    assert notifications == []

    state, notifications = poll_outage(state, parse_time("2026-03-25T10:29:00Z"), service_available=False)
    assert notifications == []

    state, notifications = poll_outage(state, parse_time("2026-03-25T10:30:00Z"), service_available=False)
    assert len(notifications) == 1
    assert notifications[0].kind == "still_down"


def test_unavailability_recovery_reports_blocked_ticket_count() -> None:
    state, _ = register_outage({}, "MYLES-SYN-001", parse_time("2026-03-25T10:00:00Z"))
    state, _ = register_outage(state, "MYLES-SYN-002", parse_time("2026-03-25T10:05:00Z"))

    state, notifications = poll_outage(state, parse_time("2026-03-25T10:35:00Z"), service_available=True)
    assert len(notifications) == 1
    assert notifications[0].kind == "recovery"
    assert "Blocked tickets resuming: 2" in notifications[0].body
    assert state["status"] == "healthy"


def test_unavailability_times_out_at_four_hours() -> None:
    state, _ = register_outage({}, "MYLES-SYN-001", parse_time("2026-03-25T10:00:00Z"))

    state, notifications = poll_outage(state, parse_time("2026-03-25T14:00:00Z"), service_available=False)
    assert len(notifications) == 1
    assert notifications[0].kind == "timeout"
    assert state["status"] == "timed_out"


def test_cli_records_notifications_to_email_log(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    email_log = tmp_path / "emails.jsonl"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "referee_unavailability.py"),
            "outage",
            "--state-path",
            str(state_path),
            "--ticket-id",
            "MYLES-SYN-001",
            "--now",
            "2026-03-25T10:00:00Z",
            "--email-log-path",
            str(email_log),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "referee_unavailability.py"),
            "poll",
            "--state-path",
            str(state_path),
            "--now",
            "2026-03-25T10:30:00Z",
            "--email-log-path",
            str(email_log),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = email_log.read_text().strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["kind"] == "still_down"
    assert payload["to"] == "a@lll.re"
    assert load_state(state_path)["status"] == "outage"
