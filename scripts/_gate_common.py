import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


class GateError(RuntimeError):
    pass


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise GateError(f"Failed to parse JSON at {path}: {exc}") from exc


def load_schema(repo_root: Path, schema_name: str):
    schema_path = repo_root / "ops" / "schemas" / schema_name
    if not schema_path.exists():
        raise GateError(f"Missing schema file: {schema_path}")
    return load_json(schema_path)


def validate_json(instance, schema, label: str):
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise GateError(f"{label} failed schema validation at {location}: {first.message}")


def canonical_snapshot_hash(snapshot: dict) -> str:
    data = {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_issue_id(repo_root: Path, issue_id: str | None, subdir: str) -> str:
    if issue_id:
        return issue_id
    files = sorted((repo_root / ".symphony" / subdir).glob("*.json"))
    stems = {path.stem for path in files}
    if len(stems) != 1:
        raise GateError(
            f"Could not infer issue id from .symphony/{subdir}; expected exactly one JSON file, found {len(stems)}"
        )
    return next(iter(stems))


def repo_identities(repo_root: Path) -> set[str]:
    identities = {repo_root.name}
    try:
        remote = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return identities
    remote = remote.removesuffix(".git")
    ssh_match = re.search(r"[:/]([^/:]+/[^/]+)$", remote)
    if ssh_match:
        identities.add(ssh_match.group(1))
        identities.add(ssh_match.group(1).split("/")[-1])
    return identities


def load_subsystem_registry(repo_root: Path) -> set[str]:
    config_path = repo_root / ".symphony" / "config.yml"
    if not config_path.exists():
        raise GateError(f"Missing subsystem registry config: {config_path}")
    data = yaml.safe_load(config_path.read_text()) or {}
    candidates = []
    for key in ("subsystems", "subsystem_registry", "canonical_subsystem_registry"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    ids = set()
    for item in candidates:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.add(item["id"])
        elif isinstance(item, str):
            ids.add(item)
    if not ids:
        raise GateError(f"No subsystem IDs found in {config_path}")
    return ids


def ensure_exact_ids(expected_items: list[dict], actual_items: list[dict], label: str):
    expected = [item["id"] for item in expected_items]
    actual = [item["id"] for item in actual_items]
    if sorted(expected) != sorted(actual):
        raise GateError(f"{label} IDs do not match snapshot. expected={sorted(expected)} actual={sorted(actual)}")
    if len(actual) != len(set(actual)):
        raise GateError(f"{label} IDs contain duplicates")


def parse_markdown_sections(path: Path) -> dict[str, list[str]]:
    text = path.read_text()
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("# "):
            current = line.strip()
            sections.setdefault(current, [])
            continue
        if line.startswith("## "):
            current = line.strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {heading: lines for heading, lines in sections.items()}


def section_body(lines: list[str]) -> str:
    body = "\n".join(lines).strip()
    return body


def require_heading_once(sections: dict[str, list[str]], heading: str):
    if heading not in sections:
        raise GateError(f"Missing required heading: {heading}")


def acceptance_step_ids(body: str) -> set[str]:
    return set(re.findall(r"(?m)^\[(STEP-\d{2})\]", body))


def parser_with_issue_id():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--issue-id")
    return parser
