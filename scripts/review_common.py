#!/usr/bin/env python3

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewContext:
    issue_id: str
    snapshot: dict
    plan: dict
    manifest: dict | None


def infer_issue_id(repo_root: Path, explicit_issue_id: str | None = None) -> str:
    if explicit_issue_id:
        return explicit_issue_id

    for env_name in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        value = os.getenv(env_name, "")
        match = re.search(r"([A-Za-z]+-\d+)", value)
        if match:
            candidate = match.group(1).upper()
            snapshot_path = repo_root / ".symphony" / "contract-snapshot" / f"{candidate}.json"
            plan_path = repo_root / ".symphony" / "execution-plan" / f"{candidate}.json"
            if snapshot_path.exists() and plan_path.exists():
                return candidate

    candidates: set[str] = set()
    for subdir in ("contract-evidence", "execution-plan", "contract-snapshot"):
        path = repo_root / ".symphony" / subdir
        if path.exists():
            candidates.update(item.stem for item in path.glob("*.json"))
    if len(candidates) != 1:
        raise ReviewError(
            f"Could not infer issue id from .symphony artefacts; expected exactly one candidate, found {sorted(candidates)}"
        )
    return next(iter(candidates))


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - defensive parse wrapper
        raise ReviewError(f"Failed to parse JSON at {path}: {exc}") from exc


def load_schema(repo_root: Path, schema_name: str) -> dict:
    path = repo_root / "ops" / "schemas" / schema_name
    if not path.exists():
        raise ReviewError(f"Missing schema file: {path}")
    return load_json(path)


def validate_json(instance: dict, schema: dict, label: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ReviewError(f"{label} failed schema validation at {location}: {first.message}")


def load_review_context(repo_root: Path, issue_id: str | None = None) -> ReviewContext:
    resolved_issue_id = infer_issue_id(repo_root, issue_id)
    snapshot_path = repo_root / ".symphony" / "contract-snapshot" / f"{resolved_issue_id}.json"
    plan_path = repo_root / ".symphony" / "execution-plan" / f"{resolved_issue_id}.json"
    manifest_path = repo_root / ".symphony" / "contract-evidence" / f"{resolved_issue_id}.json"

    if not snapshot_path.exists():
        raise ReviewError(f"Missing contract snapshot: {snapshot_path}")
    if not plan_path.exists():
        raise ReviewError(f"Missing execution plan: {plan_path}")

    snapshot = load_json(snapshot_path)
    plan = load_json(plan_path)
    manifest = load_json(manifest_path) if manifest_path.exists() else None

    validate_json(snapshot, load_schema(repo_root, "contract-snapshot.schema.json"), "contract snapshot")
    validate_json(plan, load_schema(repo_root, "execution-plan.schema.json"), "execution plan")
    if manifest is not None:
        validate_json(manifest, load_schema(repo_root, "contract-evidence.schema.json"), "contract evidence manifest")

    return ReviewContext(issue_id=resolved_issue_id, snapshot=snapshot, plan=plan, manifest=manifest)


def load_agent_prompt(path: Path) -> str:
    if not path.exists():
        raise ReviewError(f"Missing agent prompt: {path}")
    return path.read_text().strip()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    object_match = re.search(r"(\{.*\})", stripped, flags=re.DOTALL)
    if object_match:
        return json.loads(object_match.group(1))

    raise ReviewError("Model response did not contain a JSON object")


def repo_full_name(repo_root: Path) -> str:
    override = os.getenv("GITHUB_REPOSITORY")
    if override:
        return override
    try:
        remote = os.popen(f"git -C '{repo_root}' remote get-url origin").read().strip()
    except Exception:  # pragma: no cover - fallback
        remote = ""
    if remote.endswith(".git"):
        remote = remote[:-4]
    match = re.search(r"[:/]([^/:]+/[^/]+)$", remote)
    if match:
        return match.group(1)
    return repo_root.name
