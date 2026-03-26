#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path

import yaml


def canonical_snapshot_hash(snapshot: dict) -> str:
    payload = {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--issue-id", default="MYLES-SYN-001")
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--lane-tag", default="local-app/autonomous")
    parser.add_argument("--risk-flag", action="append", dest="risk_flags")
    parser.add_argument("--snapshotted-at", default="2026-03-25T22:00:00Z")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    risk_flags = args.risk_flags or ["none"]

    config = {"subsystems": [{"id": "api"}]}
    (repo_root / ".symphony").mkdir(parents=True, exist_ok=True)
    (repo_root / ".symphony" / "config.yml").write_text(yaml.safe_dump(config, sort_keys=False))

    snapshot = {
        "schema_version": "1.0",
        "issue_id": args.issue_id,
        "repo": "fpmam/myles-sandbox",
        "lane_tag": args.lane_tag,
        "acceptance_criteria": [
            {"id": "AC-1", "description": "Synthetic proof preserves the health endpoint response"}
        ],
        "edge_cases": [
            {"id": "EC-1", "description": "Synthetic proof keeps the health endpoint JSON payload stable"}
        ],
        "risk_flags": risk_flags,
        "snapshotted_at": args.snapshotted_at,
    }
    snapshot["snapshot_hash"] = canonical_snapshot_hash(snapshot)
    write_json(repo_root / ".symphony" / "contract-snapshot" / f"{args.issue_id}.json", snapshot)

    plan = {
        "schema_version": "1.0",
        "issue_id": args.issue_id,
        "repo": snapshot["repo"],
        "lane_tag": snapshot["lane_tag"],
        "contract_snapshot_hash": snapshot["snapshot_hash"],
        "brief_link": "obsidian://open?vault=bhduck&file=Myles",
        "approach_summary": "Synthetic PR proving deterministic gates and review-worker wiring.",
        "subsystem_ids": ["api"],
        "acceptance_criteria": [{"id": "AC-1", "planned_checks": ["pytest -q"]}],
        "edge_cases": [{"id": "EC-1", "planned_checks": ["pytest -q"]}],
        "risk_flags": risk_flags,
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_note": None,
    }
    plan_path = repo_root / ".symphony" / "execution-plan" / f"{args.issue_id}.json"
    write_json(plan_path, plan)

    manifest = {
        "schema_version": "1.0",
        "issue_id": args.issue_id,
        "repo": snapshot["repo"],
        "pr_number": args.pr_number,
        "lane_tag": snapshot["lane_tag"],
        "contract_snapshot_hash": snapshot["snapshot_hash"],
        "execution_plan_digest": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "acceptance_criteria": [{"id": "AC-1", "test_files": ["test_app.py"]}],
        "edge_cases": [{"id": "EC-1", "test_files": ["test_app.py"]}],
        "risk_flags": risk_flags,
        "migration_note": None,
        "rollback_note": None,
        "plan_deviation_declared": False,
        "plan_deviation_note": None,
    }
    write_json(repo_root / ".symphony" / "contract-evidence" / f"{args.issue_id}.json", manifest)

    pr_evidence = "\n".join(
        [
            "# Plain-English summary",
            "Synthetic Myles sandbox PR proving the referee and checker pipeline.",
            "",
            "## Execution-plan summary",
            "The synthetic contract keeps the health endpoint untouched and exercises the pipeline only.",
            "",
            "## Contract-evidence summary",
            "Evidence points to the existing health endpoint pytest coverage.",
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
    )
    pr_evidence_path = repo_root / ".symphony" / "pr-evidence" / f"{args.issue_id}.md"
    pr_evidence_path.parent.mkdir(parents=True, exist_ok=True)
    pr_evidence_path.write_text(pr_evidence + "\n")

    print(f"wrote synthetic bundle for {args.issue_id} with pr_number={args.pr_number}")


if __name__ == "__main__":
    main()
