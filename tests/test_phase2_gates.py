import json
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_json(path: Path, data):
    _write(path, json.dumps(data, indent=2))


def _snapshot_hash(snapshot):
    payload = {k: v for k, v in snapshot.items() if k != "snapshot_hash"}
    return __import__("hashlib").sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _base_snapshot():
    snapshot = {
        "schema_version": "1.0",
        "issue_id": "AND-200",
        "repo": "myles-sandbox",
        "lane_tag": "local-app/autonomous",
        "acceptance_criteria": [{"id": "AC-1", "description": "Health endpoint returns ok"}],
        "edge_cases": [{"id": "EC-1", "description": "Health endpoint returns JSON"}],
        "risk_flags": ["none"],
        "snapshotted_at": "2026-03-25T20:00:00Z",
    }
    snapshot["snapshot_hash"] = _snapshot_hash(snapshot)
    return snapshot


def _base_plan(snapshot):
    return {
        "schema_version": "1.0",
        "issue_id": snapshot["issue_id"],
        "repo": snapshot["repo"],
        "lane_tag": snapshot["lane_tag"],
        "contract_snapshot_hash": snapshot["snapshot_hash"],
        "brief_link": "obsidian://open?vault=bhduck&file=Myles",
        "approach_summary": "Add the endpoint and corresponding test.",
        "subsystem_ids": ["api"],
        "acceptance_criteria": [{"id": "AC-1", "planned_checks": ["pytest -q"]}],
        "edge_cases": [{"id": "EC-1", "planned_checks": ["pytest -q"]}],
        "risk_flags": ["none"],
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_note": None,
    }


def _base_manifest(snapshot, plan_path: Path):
    return {
        "schema_version": "1.0",
        "issue_id": snapshot["issue_id"],
        "repo": snapshot["repo"],
        "pr_number": 7,
        "lane_tag": snapshot["lane_tag"],
        "contract_snapshot_hash": snapshot["snapshot_hash"],
        "execution_plan_digest": __import__("hashlib").sha256(plan_path.read_bytes()).hexdigest(),
        "acceptance_criteria": [{"id": "AC-1", "test_files": ["test_app.py"]}],
        "edge_cases": [{"id": "EC-1", "test_files": ["test_app.py"]}],
        "risk_flags": ["none"],
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_declared": False,
        "plan_deviation_note": None,
    }


def _init_fixture_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/fpmam/myles-sandbox.git"], check=True)
    (repo / "ops" / "schemas").mkdir(parents=True)
    for schema_path in (ROOT / "ops" / "schemas").glob("*.json"):
        _write((repo / "ops" / "schemas" / schema_path.name), schema_path.read_text())
    _write(repo / ".symphony" / "config.yml", yaml.safe_dump({"subsystems": [{"id": "api"}]}))
    _write(repo / "test_app.py", "def test_placeholder():\n    assert True\n")
    snapshot = _base_snapshot()
    plan = _base_plan(snapshot)
    _write_json(repo / ".symphony" / "contract-snapshot" / "AND-200.json", snapshot)
    plan_path = repo / ".symphony" / "execution-plan" / "AND-200.json"
    _write_json(plan_path, plan)
    manifest = _base_manifest(snapshot, plan_path)
    _write_json(repo / ".symphony" / "contract-evidence" / "AND-200.json", manifest)
    _write(
        repo / ".symphony" / "pr-evidence" / "AND-200.md",
        "\n".join(
            [
                "# Plain-English summary",
                "Health endpoint change.",
                "",
                "## Execution-plan summary",
                "Matches the posted execution plan.",
                "",
                "## Contract-evidence summary",
                "Evidence references test_app.py.",
                "",
                "## Migration note",
                "None",
                "",
                "## Rollback note",
                "None",
                "",
                "## Plan deviation note",
                "None",
                "",
                "## Acceptance script",
                "[STEP-01] Run pytest -q",
            ]
        ),
    )
    return repo


def test_plan_gate_passes_with_valid_fixture(tmp_path):
    repo = _init_fixture_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_plan_gate.py"), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr_gate_passes_with_valid_fixture(tmp_path):
    repo = _init_fixture_repo(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_pr_gate.py"),
            "--repo-root",
            str(repo),
            "--pr-number",
            "7",
            "--repo",
            "myles-sandbox",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_plan_gate_fails_on_unknown_subsystem(tmp_path):
    repo = _init_fixture_repo(tmp_path)
    plan_path = repo / ".symphony" / "execution-plan" / "AND-200.json"
    plan = json.loads(plan_path.read_text())
    plan["subsystem_ids"] = ["unknown"]
    _write_json(plan_path, plan)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_plan_gate.py"), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Unknown subsystem_ids" in result.stdout
