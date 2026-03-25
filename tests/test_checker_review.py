import json
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_json(path: Path, payload: dict) -> None:
    _write(path, json.dumps(payload, indent=2))


def _snapshot(risk_flags: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "issue_id": "AND-270",
        "repo": "fpmam/myles-sandbox",
        "lane_tag": "local-app/autonomous",
        "acceptance_criteria": [{"id": "AC-1", "description": "Health endpoint returns ok"}],
        "edge_cases": [{"id": "EC-1", "description": "Health endpoint returns JSON"}],
        "risk_flags": risk_flags,
        "snapshot_hash": "hash-270",
        "snapshotted_at": "2026-03-25T20:00:00Z",
    }


def _plan(risk_flags: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "issue_id": "AND-270",
        "repo": "fpmam/myles-sandbox",
        "lane_tag": "local-app/autonomous",
        "contract_snapshot_hash": "hash-270",
        "brief_link": "obsidian://open?vault=bhduck&file=Myles",
        "approach_summary": "Synthetic checker proof.",
        "subsystem_ids": ["api"],
        "acceptance_criteria": [{"id": "AC-1", "planned_checks": ["pytest -q"]}],
        "edge_cases": [{"id": "EC-1", "planned_checks": ["pytest -q"]}],
        "risk_flags": risk_flags,
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_note": None,
    }


def _manifest(risk_flags: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "issue_id": "AND-270",
        "repo": "fpmam/myles-sandbox",
        "pr_number": 27,
        "lane_tag": "local-app/autonomous",
        "contract_snapshot_hash": "hash-270",
        "execution_plan_digest": "digest-270",
        "acceptance_criteria": [{"id": "AC-1", "test_files": ["test_app.py"]}],
        "edge_cases": [{"id": "EC-1", "test_files": ["test_app.py"]}],
        "risk_flags": risk_flags,
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_declared": False,
        "plan_deviation_note": None,
    }


def _init_repo(tmp_path: Path, risk_flags: list[str]) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ops" / "schemas").mkdir(parents=True)
    for schema_path in (ROOT / "ops" / "schemas").glob("*.json"):
        _write((repo / "ops" / "schemas" / schema_path.name), schema_path.read_text())
    _write(repo / "ops" / "agents" / "codex-checker.md", (ROOT / "ops" / "agents" / "codex-checker.md").read_text())
    _write(repo / ".symphony" / "config.yml", yaml.safe_dump({"subsystems": [{"id": "api"}]}))
    _write_json(repo / ".symphony" / "contract-snapshot" / "AND-270.json", _snapshot(risk_flags))
    _write_json(repo / ".symphony" / "execution-plan" / "AND-270.json", _plan(risk_flags))
    _write_json(repo / ".symphony" / "contract-evidence" / "AND-270.json", _manifest(risk_flags))
    _write(repo / ".symphony" / "pr-evidence" / "AND-270.md", "# Plain-English summary\nSynthetic proof.")
    _write(repo / "test_app.py", "def test_placeholder():\n    assert True\n")
    referee_path = repo / "referee-verdict.json"
    return repo, referee_path


def test_checker_review_standard_mode(tmp_path: Path) -> None:
    repo, referee_path = _init_repo(tmp_path, ["recent_referee_miss_subsystem"])
    _write_json(
        referee_path,
        {
            "schema_version": "1.0",
            "issue_id": "AND-270",
            "repo": "fpmam/myles-sandbox",
            "contract_snapshot_hash": "hash-270",
            "review_stage": "pr",
            "pr_number": 27,
            "head_sha": "abc123",
            "verdict": "Pass",
            "explanation": "Referee passed.",
            "confidence": 0.8,
            "findings": [],
            "review_passed": True,
            "reviewed_at": "2026-03-25T21:00:00Z",
        },
    )
    simulated = repo / "checker-response.json"
    _write_json(
        simulated,
        {
            "verdict": "Pass",
            "review_mode": "standard",
            "agreement_with_referee": "corroborates",
            "summary": "The checker agrees.",
            "findings": [],
        },
    )
    output_path = repo / ".artifacts" / "checker-verdict.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_checker_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-270",
            "--pr-number",
            "27",
            "--head-sha",
            "abc123",
            "--referee-verdict-path",
            str(referee_path),
            "--simulate-response-file",
            str(simulated),
            "--output-path",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(output_path.read_text())
    assert verdict["review_mode"] == "standard"
    assert verdict["agreement_with_referee"] == "corroborates"


def test_checker_review_fallback_mode(tmp_path: Path) -> None:
    repo, referee_path = _init_repo(tmp_path, ["none"])
    _write_json(
        referee_path,
        {
            "schema_version": "1.0",
            "issue_id": "AND-270",
            "repo": "fpmam/myles-sandbox",
            "contract_snapshot_hash": "hash-270",
            "review_stage": "pr",
            "pr_number": 27,
            "head_sha": "abc123",
            "verdict": "Unavailable",
            "explanation": "Referee unavailable.",
            "confidence": 0.0,
            "findings": [],
            "review_passed": False,
            "reviewed_at": "2026-03-25T21:00:00Z",
        },
    )
    simulated = repo / "checker-response.json"
    _write_json(
        simulated,
        {
            "verdict": "Pass",
            "review_mode": "fallback",
            "agreement_with_referee": "n_a",
            "summary": "Fallback checker passed.",
            "findings": [],
        },
    )
    output_path = repo / ".artifacts" / "checker-verdict.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_checker_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-270",
            "--pr-number",
            "27",
            "--head-sha",
            "abc123",
            "--referee-verdict-path",
            str(referee_path),
            "--simulate-response-file",
            str(simulated),
            "--output-path",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(output_path.read_text())
    assert verdict["review_mode"] == "fallback"
    assert verdict["agreement_with_referee"] == "n_a"
