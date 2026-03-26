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


def _snapshot(snapshot_hash: str = "hash-123") -> dict:
    return {
        "schema_version": "1.0",
        "issue_id": "AND-260",
        "repo": "fpmam/myles-sandbox",
        "lane_tag": "local-app/autonomous",
        "acceptance_criteria": [{"id": "AC-1", "description": "Health endpoint returns ok"}],
        "edge_cases": [{"id": "EC-1", "description": "Health endpoint returns JSON"}],
        "risk_flags": ["none"],
        "snapshot_hash": snapshot_hash,
        "snapshotted_at": "2026-03-25T20:00:00Z",
    }


def _plan(snapshot_hash: str = "hash-123") -> dict:
    return {
        "schema_version": "1.0",
        "issue_id": "AND-260",
        "repo": "fpmam/myles-sandbox",
        "lane_tag": "local-app/autonomous",
        "contract_snapshot_hash": snapshot_hash,
        "brief_link": "obsidian://open?vault=bhduck&file=Myles",
        "approach_summary": "Keep the existing endpoint behaviour intact.",
        "subsystem_ids": ["api"],
        "acceptance_criteria": [{"id": "AC-1", "planned_checks": ["pytest -q"]}],
        "edge_cases": [{"id": "EC-1", "planned_checks": ["pytest -q"]}],
        "risk_flags": ["none"],
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_note": None,
    }


def _manifest(snapshot_hash: str = "hash-123") -> dict:
    return {
        "schema_version": "1.0",
        "issue_id": "AND-260",
        "repo": "fpmam/myles-sandbox",
        "pr_number": 26,
        "lane_tag": "local-app/autonomous",
        "contract_snapshot_hash": snapshot_hash,
        "execution_plan_digest": "digest-123",
        "acceptance_criteria": [{"id": "AC-1", "test_files": ["test_app.py"]}],
        "edge_cases": [{"id": "EC-1", "test_files": ["test_app.py"]}],
        "risk_flags": ["none"],
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_declared": False,
        "plan_deviation_note": None,
    }


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ops" / "schemas").mkdir(parents=True)
    for schema_path in (ROOT / "ops" / "schemas").glob("*.json"):
        _write((repo / "ops" / "schemas" / schema_path.name), schema_path.read_text())
    _write(repo / "ops" / "agents" / "claude-referee.md", (ROOT / "ops" / "agents" / "claude-referee.md").read_text())
    _write(repo / ".symphony" / "config.yml", yaml.safe_dump({"subsystems": [{"id": "api"}]}))
    _write_json(repo / ".symphony" / "contract-snapshot" / "AND-260.json", _snapshot())
    _write_json(repo / ".symphony" / "execution-plan" / "AND-260.json", _plan())
    _write_json(repo / ".symphony" / "contract-evidence" / "AND-260.json", _manifest())
    _write(repo / ".symphony" / "pr-evidence" / "AND-260.md", "# Plain-English summary\nSynthetic proof.")
    _write(repo / "test_app.py", "def test_placeholder():\n    assert True\n")
    return repo


def test_run_referee_review_writes_valid_verdict(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    simulated_response = repo / "response.json"
    simulated_response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "issue_id": "AND-260",
                "repo": "fpmam/myles-sandbox",
                "contract_snapshot_hash": "hash-123",
                "review_stage": "pr",
                "pr_number": 26,
                "head_sha": "abc123",
                "verdict": "Pass",
                "explanation": "Synthetic evidence is coherent.",
                "confidence": 0.91,
                "findings": [],
                "review_passed": True,
                "reviewed_at": "2026-03-25T21:30:00Z",
            }
        )
    )
    output_path = repo / ".artifacts" / "referee-verdict.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_referee_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-260",
            "--pr-number",
            "26",
            "--head-sha",
            "abc123",
            "--simulate-response-file",
            str(simulated_response),
            "--output-path",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(output_path.read_text())
    assert verdict["verdict"] == "Pass"
    assert verdict["review_passed"] is True
    assert verdict["pr_number"] == 26


def test_run_referee_review_rejects_invalid_verdict(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    simulated_response = repo / "response.json"
    simulated_response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "issue_id": "AND-260",
                "repo": "fpmam/myles-sandbox",
                "contract_snapshot_hash": "hash-123",
                "review_stage": "pr",
                "pr_number": 26,
                "head_sha": "abc123",
                "verdict": "Pass",
                "explanation": "This is invalid because review_passed disagrees.",
                "confidence": 0.91,
                "findings": [],
                "review_passed": False,
                "reviewed_at": "2026-03-25T21:30:00Z",
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_referee_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-260",
            "--pr-number",
            "26",
            "--head-sha",
            "abc123",
            "--simulate-response-file",
            str(simulated_response),
            "--output-path",
            str(repo / ".artifacts" / "referee-verdict.json"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "schema validation" in result.stderr


def test_run_referee_review_prunes_extra_fields(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    simulated_response = repo / "response.json"
    simulated_response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "issue_id": "AND-260",
                "repo": "fpmam/myles-sandbox",
                "contract_snapshot_hash": "hash-123",
                "review_stage": "pr",
                "pr_number": 26,
                "head_sha": "abc123",
                "summary": "Noise from the model that should be dropped.",
                "verdict": "Pass",
                "explanation": "Synthetic evidence is coherent.",
                "confidence": 0.91,
                "findings": [],
                "review_passed": True,
                "reviewed_at": "2026-03-25T21:30:00Z",
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_referee_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-260",
            "--pr-number",
            "26",
            "--head-sha",
            "abc123",
            "--simulate-response-file",
            str(simulated_response),
            "--output-path",
            str(repo / ".artifacts" / "referee-verdict.json"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_run_referee_review_uses_summary_when_explanation_is_missing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    simulated_response = repo / "response.json"
    simulated_response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "issue_id": "AND-260",
                "repo": "fpmam/myles-sandbox",
                "contract_snapshot_hash": "hash-123",
                "review_stage": "pr",
                "pr_number": 26,
                "head_sha": "abc123",
                "summary": "Use this summary as the explanation.",
                "verdict": "Pass",
                "confidence": 0.91,
                "findings": [],
                "review_passed": True,
                "reviewed_at": "2026-03-25T21:30:00Z",
            }
        )
    )

    output_path = repo / ".artifacts" / "referee-verdict.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_referee_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-260",
            "--pr-number",
            "26",
            "--head-sha",
            "abc123",
            "--simulate-response-file",
            str(simulated_response),
            "--output-path",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(output_path.read_text())
    assert verdict["explanation"] == "Use this summary as the explanation."


def test_run_referee_review_derives_review_passed_when_missing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    simulated_response = repo / "response.json"
    simulated_response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "issue_id": "AND-260",
                "repo": "fpmam/myles-sandbox",
                "contract_snapshot_hash": "hash-123",
                "review_stage": "pr",
                "pr_number": 26,
                "head_sha": "abc123",
                "summary": "The package is coherent.",
                "verdict": "Pass",
                "reviewed_at": "2026-03-25T21:30:00Z",
            }
        )
    )

    output_path = repo / ".artifacts" / "referee-verdict.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_referee_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-260",
            "--pr-number",
            "26",
            "--head-sha",
            "abc123",
            "--simulate-response-file",
            str(simulated_response),
            "--output-path",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(output_path.read_text())
    assert verdict["review_passed"] is True
    assert verdict["confidence"] == 0.5
    assert verdict["findings"] == []


def test_run_referee_review_normalizes_sparse_findings(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    simulated_response = repo / "response.json"
    simulated_response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "issue_id": "AND-260",
                "repo": "fpmam/myles-sandbox",
                "contract_snapshot_hash": "hash-123",
                "review_stage": "pr",
                "pr_number": 26,
                "head_sha": "abc123",
                "summary": "There is a problem.",
                "verdict": "Fail",
                "reviewed_at": "2026-03-25T21:30:00Z",
                "findings": [
                    {
                        "title": "Missing edge-case evidence",
                        "severity": "major",
                        "category": "contract_match",
                    }
                ],
            }
        )
    )

    output_path = repo / ".artifacts" / "referee-verdict.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_referee_review.py"),
            "--repo-root",
            str(repo),
            "--issue-id",
            "AND-260",
            "--pr-number",
            "26",
            "--head-sha",
            "abc123",
            "--simulate-response-file",
            str(simulated_response),
            "--output-path",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(output_path.read_text())
    assert verdict["review_passed"] is False
    assert verdict["findings"][0]["summary"] == "Missing edge-case evidence"
    assert verdict["findings"][0]["blocking"] is True
    assert verdict["findings"][0]["category"] == "other"
