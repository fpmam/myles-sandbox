#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from review_common import (
    ReviewError,
    extract_json_object,
    load_agent_prompt,
    load_json,
    quantize_confidence,
    load_review_context,
    load_schema,
    repo_full_name,
    utc_now,
    validate_json,
    write_json,
)


def _checker_required(risk_flags: list[str], referee_verdict: dict) -> bool:
    checker_risk_flags = {
        "migration",
        "persistence_change",
        "destructive_action",
        "interface_contract",
        "cross_module_refactor",
        "external_integration",
        "architectural_risk",
        "recent_referee_miss_subsystem",
        "needs_replan_history",
    }
    return any(flag in checker_risk_flags for flag in risk_flags) or (referee_verdict.get("verdict") == "Low Confidence")


def _fallback_allowed(risk_flags: list[str]) -> bool:
    return not any(flag in {"recent_referee_miss_subsystem", "needs_replan_history"} for flag in risk_flags)


def determine_review_mode(risk_flags: list[str], referee_verdict: dict) -> str | None:
    if referee_verdict.get("verdict") == "Unavailable":
        if not _fallback_allowed(risk_flags):
            raise ReviewError("Referee fallback is not allowed for the current risk flags")
        return "fallback"
    if not _checker_required(risk_flags, referee_verdict):
        return None
    if referee_verdict.get("review_passed") is not True:
        raise ReviewError("Checker standard review requires a passing referee verdict")
    return "standard"


def _normalize_finding(finding: dict, index: int) -> dict:
    normalized = dict(finding)
    normalized.setdefault("finding_id", f"CF-{index:03d}")
    severity = str(normalized.get("severity", "minor")).lower()
    normalized["severity"] = {
        "info": "info",
        "minor": "minor",
        "low": "minor",
        "medium": "major",
        "major": "major",
        "high": "critical",
        "critical": "critical",
    }.get(severity, "minor")
    category = str(normalized.get("category", "other")).lower()
    if "accept" in category:
        normalized["category"] = "acceptance"
    elif "edge" in category:
        normalized["category"] = "edge_case"
    elif "risk" in category:
        normalized["category"] = "risk"
    elif "migr" in category:
        normalized["category"] = "migration"
    elif "rollback" in category:
        normalized["category"] = "rollback"
    elif "deviation" in category or category == "plan":
        normalized["category"] = "plan_deviation"
    else:
        normalized["category"] = "other"
    normalized.setdefault(
        "summary",
        finding.get("title")
        or finding.get("description")
        or finding.get("reasoning")
        or "Model reported a finding without a summary.",
    )
    normalized.setdefault("acceptance_criteria_ids", [])
    normalized.setdefault("edge_case_ids", [])
    normalized.setdefault("blocking", normalized["severity"] in {"major", "critical"})
    return normalized


def _normalize_verdict(verdict: dict, payload: dict, review_mode: str) -> dict:
    schema = load_schema(Path(payload["repo_root"]), "checker-verdict.schema.json")
    allowed = set(schema.get("properties", {}).keys())
    pruned = {key: value for key, value in verdict.items() if key in allowed}
    findings = pruned.get("findings", verdict.get("findings", []))
    pruned["findings"] = [
        _normalize_finding(finding, index)
        for index, finding in enumerate(findings, start=1)
        if isinstance(finding, dict)
    ]
    pruned.setdefault("schema_version", "1.0")
    pruned.setdefault("issue_id", payload["issue_id"])
    pruned.setdefault("repo", payload["repo"])
    pruned.setdefault("contract_snapshot_hash", payload["contract_snapshot_hash"])
    pruned.setdefault("review_stage", "pr")
    pruned.setdefault("pr_number", payload["pr_number"])
    pruned.setdefault("head_sha", payload["head_sha"])
    pruned.setdefault("review_mode", review_mode)
    if "agreement_with_referee" not in pruned:
        pruned["agreement_with_referee"] = "n_a" if review_mode == "fallback" else "corroborates"
    pruned.setdefault("explanation", verdict.get("summary") or verdict.get("reasoning") or "No explanation provided.")
    quantized_confidence = quantize_confidence(pruned.get("confidence", 0.5), 0.5)
    pruned["confidence"] = quantized_confidence
    if "review_passed" not in pruned:
        pruned["review_passed"] = pruned.get("verdict") == "Pass"
    pruned.setdefault("reviewed_at", utc_now())
    validate_json(pruned, schema, "checker verdict")
    pruned["confidence"] = float(quantized_confidence)
    return pruned


def _codex_output_schema(review_mode: str) -> dict:
    agreement_values = ["n_a"] if review_mode == "fallback" else ["corroborates", "disputes"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "verdict",
            "review_mode",
            "agreement_with_referee",
            "explanation",
            "confidence",
            "findings",
            "review_passed",
        ],
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["Pass", "Fail", "Low Confidence", "Unavailable", "Needs Product Decision"],
            },
            "review_mode": {
                "type": "string",
                "const": review_mode,
            },
            "agreement_with_referee": {
                "type": "string",
                "enum": agreement_values,
            },
            "explanation": {
                "type": "string",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "review_passed": {
                "type": "boolean",
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "finding_id",
                        "severity",
                        "category",
                        "summary",
                        "acceptance_criteria_ids",
                        "edge_case_ids",
                        "evidence",
                        "blocking",
                    ],
                    "properties": {
                        "finding_id": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["info", "minor", "major", "critical"],
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "acceptance",
                                "edge_case",
                                "risk",
                                "migration",
                                "rollback",
                                "plan_deviation",
                                "other",
                            ],
                        },
                        "summary": {"type": "string"},
                        "acceptance_criteria_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "edge_case_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "evidence": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "blocking": {"type": "boolean"},
                    },
                },
            },
        },
    }


def _run_codex(prompt: str, repo_root: Path, output_schema: Path, output_path: Path) -> str:
    command = [
        "codex",
        "exec",
        "-C",
        str(repo_root),
        "--output-schema",
        str(output_schema),
        "-o",
        str(output_path),
        "--dangerously-bypass-approvals-and-sandbox",
        prompt,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ReviewError(f"codex exec failed: {result.stderr or result.stdout}")
    return output_path.read_text()


def _simulated_response(path: Path) -> str:
    return path.read_text()


def _build_prompt(repo_root: Path, review_mode: str, referee_path: Path | None) -> str:
    base = load_agent_prompt(repo_root / "ops" / "agents" / "codex-checker.md")
    prompt = [
        base,
        "",
        f"Review mode: {review_mode}",
        "Read these repo files before answering:",
        "- .symphony/contract-snapshot/*.json",
        "- .symphony/execution-plan/*.json",
        "- .symphony/contract-evidence/*.json",
        "- .symphony/pr-evidence/*.md",
    ]
    if review_mode == "standard" and referee_path is not None:
        prompt.append(f"- {referee_path}")
    prompt.append("")
    prompt.append("Return JSON only.")
    return "\n".join(prompt)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--issue-id")
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--referee-verdict-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--simulate-response-file")
    parser.add_argument("--allow-skip", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    context = load_review_context(repo_root, args.issue_id)
    referee_verdict_path = Path(args.referee_verdict_path).resolve()
    referee_verdict = load_json(referee_verdict_path)

    risk_flags = list(context.snapshot.get("risk_flags", []))
    review_mode = determine_review_mode(risk_flags, referee_verdict)
    if review_mode is None:
        if args.allow_skip:
            print("checker review skipped: not required for this ticket")
            return
        raise ReviewError("Checker review is not required for this ticket")

    payload = {
        "repo_root": str(repo_root),
        "issue_id": context.issue_id,
        "repo": repo_full_name(repo_root),
        "contract_snapshot_hash": context.snapshot["snapshot_hash"],
        "pr_number": args.pr_number,
        "head_sha": args.head_sha,
    }

    if args.simulate_response_file:
        response_text = _simulated_response(Path(args.simulate_response_file).resolve())
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            schema_path = Path(handle.name)
        schema_path.write_text(json.dumps(_codex_output_schema(review_mode), indent=2))
        response_text = _run_codex(
            _build_prompt(repo_root, review_mode, referee_verdict_path if review_mode == "standard" else None),
            repo_root,
            schema_path,
            output_path,
        )
        schema_path.unlink(missing_ok=True)

    (output_path.parent / "checker-raw-response.txt").write_text(response_text)
    raw_verdict = extract_json_object(response_text)
    verdict = _normalize_verdict(raw_verdict, payload, review_mode)
    write_json(output_path, verdict)
    print(f"wrote checker verdict to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except ReviewError as exc:
        print(f"checker review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
