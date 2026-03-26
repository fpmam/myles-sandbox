#!/usr/bin/env python3

from pathlib import Path

from _gate_common import (
    GateError,
    acceptance_step_ids,
    ensure_exact_ids,
    find_issue_id,
    load_json,
    load_schema,
    parse_markdown_sections,
    parser_with_issue_id,
    repo_identities,
    require_heading_once,
    section_body,
    sha256_file,
    validate_json,
)


def main():
    parser = parser_with_issue_id()
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--repo")
    parser.add_argument("--pr-body-path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    issue_id = find_issue_id(repo_root, args.issue_id, "contract-evidence")
    snapshot_path = repo_root / ".symphony" / "contract-snapshot" / f"{issue_id}.json"
    plan_path = repo_root / ".symphony" / "execution-plan" / f"{issue_id}.json"
    manifest_path = repo_root / ".symphony" / "contract-evidence" / f"{issue_id}.json"
    pr_body_path = Path(args.pr_body_path).resolve() if args.pr_body_path else repo_root / ".symphony" / "pr-evidence" / f"{issue_id}.md"

    for path, label in (
        (snapshot_path, "contract snapshot"),
        (plan_path, "execution plan"),
        (manifest_path, "contract evidence manifest"),
        (pr_body_path, "PR evidence pack"),
    ):
        if not path.exists():
            raise GateError(f"Missing {label}: {path}")

    snapshot = load_json(snapshot_path)
    plan = load_json(plan_path)
    manifest = load_json(manifest_path)
    validate_json(snapshot, load_schema(repo_root, "contract-snapshot.schema.json"), "contract snapshot")
    validate_json(plan, load_schema(repo_root, "execution-plan.schema.json"), "execution plan")
    validate_json(manifest, load_schema(repo_root, "contract-evidence.schema.json"), "contract evidence manifest")

    expected_repo = args.repo or manifest["repo"]
    expected_pr_number = args.pr_number or manifest["pr_number"]
    if manifest["issue_id"] != issue_id:
        raise GateError("manifest issue_id does not match issue id")
    if manifest["repo"] != plan["repo"] or manifest["repo"] != snapshot["repo"]:
        raise GateError("manifest repo does not match plan/snapshot repo")
    if manifest["repo"] != expected_repo:
        raise GateError("manifest repo does not match expected repo")
    if manifest["repo"] not in repo_identities(repo_root):
        raise GateError(f"manifest repo {manifest['repo']} does not match this repo")
    if manifest["pr_number"] != expected_pr_number:
        raise GateError("manifest pr_number does not match expected pr number")
    if manifest["lane_tag"] != snapshot["lane_tag"]:
        raise GateError("manifest lane_tag does not match contract snapshot")
    if manifest["contract_snapshot_hash"] != snapshot["snapshot_hash"]:
        raise GateError("manifest contract_snapshot_hash does not match snapshot_hash")
    if manifest["execution_plan_digest"] != sha256_file(plan_path):
        raise GateError("manifest execution_plan_digest does not match execution plan SHA-256")

    ensure_exact_ids(snapshot["acceptance_criteria"], manifest["acceptance_criteria"], "acceptance criteria")
    ensure_exact_ids(snapshot["edge_cases"], manifest["edge_cases"], "edge cases")

    for item in manifest["acceptance_criteria"]:
        for test_file in item["test_files"]:
            if not (repo_root / test_file).exists():
                raise GateError(f"Missing acceptance test file at HEAD: {test_file}")
    for item in manifest["edge_cases"]:
        for test_file in item.get("test_files", []):
            if not (repo_root / test_file).exists():
                raise GateError(f"Missing edge-case test file at HEAD: {test_file}")

    sections = parse_markdown_sections(pr_body_path)
    required_headings = [
        "# Plain-English summary",
        "## Execution-plan summary",
        "## Contract-evidence summary",
        "## Migration note",
        "## Rollback note",
        "## Plan deviation note",
        "## Acceptance script",
    ]
    for heading in required_headings:
        require_heading_once(sections, heading)

    non_empty_required = [
        "# Plain-English summary",
        "## Execution-plan summary",
        "## Contract-evidence summary",
        "## Acceptance script",
    ]
    for heading in non_empty_required:
        if not section_body(sections[heading]):
            raise GateError(f"Required heading body is empty: {heading}")

    step_ids = acceptance_step_ids(section_body(sections["## Acceptance script"]))
    if not step_ids:
        raise GateError("Acceptance script must contain at least one [STEP-XX] identifier")

    for item in manifest["edge_cases"]:
        waiver = item.get("waiver")
        if waiver and waiver["linked_acceptance_step_id"] not in step_ids:
            raise GateError(
                f"Waiver for edge case {item['id']} references unknown acceptance step {waiver['linked_acceptance_step_id']}"
            )

    if set(manifest["risk_flags"]) != set(snapshot["risk_flags"]):
        raise GateError("manifest risk_flags do not exactly match the contract snapshot")

    migration_body = section_body(sections["## Migration note"])
    rollback_body = section_body(sections["## Rollback note"])
    deviation_body = section_body(sections["## Plan deviation note"])
    if manifest["migration_note"] is None and migration_body not in ("", "None"):
        raise GateError("Migration note body must be empty or None when manifest note is null")
    if manifest["rollback_note"] is None and rollback_body not in ("", "None"):
        raise GateError("Rollback note body must be empty or None when manifest note is null")
    if manifest["plan_deviation_declared"] is False:
        if set(item["id"] for item in manifest["acceptance_criteria"]) != set(item["id"] for item in plan["acceptance_criteria"]):
            raise GateError("Manifest acceptance criteria IDs do not match execution plan when no deviation is declared")
        if set(item["id"] for item in manifest["edge_cases"]) != set(item["id"] for item in plan["edge_cases"]):
            raise GateError("Manifest edge-case IDs do not match execution plan when no deviation is declared")
        if set(manifest["risk_flags"]) != set(plan["risk_flags"]):
            raise GateError("Manifest risk_flags do not match execution plan when no deviation is declared")
        if manifest["plan_deviation_note"] is not None or deviation_body not in ("", "None"):
            raise GateError("Plan deviation note must be null/None when no deviation is declared")
    else:
        if not manifest["plan_deviation_note"] or not deviation_body or deviation_body == "None":
            raise GateError("Plan deviation note must be non-empty when a deviation is declared")

    print(f"deterministic PR gate passed for {issue_id}")


if __name__ == "__main__":
    try:
        main()
    except GateError as exc:
        print(f"deterministic PR gate failed: {exc}")
        raise SystemExit(1)
