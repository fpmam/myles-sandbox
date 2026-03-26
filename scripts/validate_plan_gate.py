#!/usr/bin/env python3

from pathlib import Path

from _gate_common import (
    GateError,
    canonical_snapshot_hash,
    ensure_exact_ids,
    find_issue_id,
    load_json,
    load_schema,
    load_subsystem_registry,
    parser_with_issue_id,
    repo_identities,
    validate_json,
)


def main():
    parser = parser_with_issue_id()
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    issue_id = find_issue_id(repo_root, args.issue_id, "execution-plan")

    snapshot_path = repo_root / ".symphony" / "contract-snapshot" / f"{issue_id}.json"
    plan_path = repo_root / ".symphony" / "execution-plan" / f"{issue_id}.json"
    if not snapshot_path.exists():
        raise GateError(f"Missing contract snapshot: {snapshot_path}")
    if not plan_path.exists():
        raise GateError(f"Missing execution plan: {plan_path}")

    snapshot = load_json(snapshot_path)
    plan = load_json(plan_path)
    validate_json(snapshot, load_schema(repo_root, "contract-snapshot.schema.json"), "contract snapshot")
    validate_json(plan, load_schema(repo_root, "execution-plan.schema.json"), "execution plan")

    computed_snapshot_hash = canonical_snapshot_hash(snapshot)
    if snapshot["snapshot_hash"] != computed_snapshot_hash:
        raise GateError("snapshot_hash does not match canonical SHA-256 of the snapshot payload")
    if plan["contract_snapshot_hash"] != snapshot["snapshot_hash"]:
        raise GateError("execution plan contract_snapshot_hash does not match snapshot_hash")
    if plan["issue_id"] != snapshot["issue_id"]:
        raise GateError("execution plan issue_id does not match contract snapshot")
    if plan["lane_tag"] != snapshot["lane_tag"]:
        raise GateError("execution plan lane_tag does not match contract snapshot")
    if plan["repo"] != snapshot["repo"]:
        raise GateError("execution plan repo does not match contract snapshot")
    if plan["repo"] not in repo_identities(repo_root):
        raise GateError(f"execution plan repo {plan['repo']} does not match this repo")

    ensure_exact_ids(snapshot["acceptance_criteria"], plan["acceptance_criteria"], "acceptance criteria")
    ensure_exact_ids(snapshot["edge_cases"], plan["edge_cases"], "edge cases")

    if set(plan["risk_flags"]) != set(snapshot["risk_flags"]):
        raise GateError("execution plan risk_flags do not exactly match the contract snapshot")
    if plan["plan_deviation_note"] is not None:
        raise GateError("execution plan plan_deviation_note must be null")

    subsystem_registry = load_subsystem_registry(repo_root)
    unknown_subsystems = sorted(set(plan["subsystem_ids"]) - subsystem_registry)
    if unknown_subsystems:
        raise GateError(f"Unknown subsystem_ids in execution plan: {unknown_subsystems}")

    print(f"deterministic plan gate passed for {issue_id}")


if __name__ == "__main__":
    try:
        main()
    except GateError as exc:
        print(f"deterministic plan gate failed: {exc}")
        raise SystemExit(1)
