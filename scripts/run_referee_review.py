#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from review_common import (
    ReviewError,
    extract_json_object,
    load_agent_prompt,
    load_review_context,
    load_schema,
    repo_full_name,
    utc_now,
    validate_json,
    write_json,
)


DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _anthropic_request(prompt: str, payload: dict, model: str) -> str:
    api_key = os.getenv("ANTHROPIC_MYLES_API_KEY")
    if not api_key:
        raise ReviewError("ANTHROPIC_MYLES_API_KEY is required for referee reviews")

    request_payload = {
        "model": model,
        "max_tokens": 1800,
        "system": prompt,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(payload, indent=2),
            }
        ],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ReviewError(f"Anthropic request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ReviewError(f"Anthropic request failed: {exc}") from exc

    parts = []
    for item in data.get("content", []):
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
    text = "\n".join(parts).strip()
    if not text:
        raise ReviewError("Anthropic response did not contain text output")
    return text


def _simulated_response(path: Path) -> str:
    return path.read_text()


def _prune_verdict_to_schema(verdict: dict, schema: dict) -> dict:
    allowed = set(schema.get("properties", {}).keys())
    pruned = {key: value for key, value in verdict.items() if key in allowed}
    finding_schema = schema.get("$defs", {}).get("finding", {})
    finding_allowed = set(finding_schema.get("properties", {}).keys())
    if isinstance(pruned.get("findings"), list):
        normalized_findings = []
        for finding in verdict.get("findings", []):
            if not isinstance(finding, dict):
                continue
            compact = {key: value for key, value in finding.items() if key in finding_allowed}
            if "summary" not in compact:
                compact["summary"] = (
                    finding.get("title")
                    or finding.get("description")
                    or finding.get("reasoning")
                    or "Model reported a finding without a summary."
                )
            normalized_findings.append(compact)
        pruned["findings"] = normalized_findings
    return pruned


def _normalize_findings(verdict: dict) -> None:
    normalized = []
    for index, finding in enumerate(verdict.get("findings", []), start=1):
        if not isinstance(finding, dict):
            continue
        finding.setdefault("finding_id", f"RF-{index:03d}")
        finding.setdefault("severity", "minor")
        finding.setdefault("category", "other")
        finding.setdefault(
            "summary",
            "Model reported a finding without a summary.",
        )
        finding.setdefault("acceptance_criteria_ids", [])
        finding.setdefault("edge_case_ids", [])
        finding.setdefault("blocking", finding.get("severity") in {"major", "critical"})
        normalized.append(finding)
    verdict["findings"] = normalized


def build_payload(repo_root: Path, issue_id: str, pr_number: int, head_sha: str) -> dict:
    context = load_review_context(repo_root, issue_id)
    pr_evidence_path = repo_root / ".symphony" / "pr-evidence" / f"{context.issue_id}.md"

    payload = {
        "issue_id": context.issue_id,
        "repo": repo_full_name(repo_root),
        "review_stage": "pr",
        "pr_number": pr_number,
        "head_sha": head_sha,
        "contract_snapshot": context.snapshot,
        "execution_plan": context.plan,
        "contract_evidence_manifest": context.manifest,
        "pr_evidence_markdown": pr_evidence_path.read_text() if pr_evidence_path.exists() else "",
        "instructions": {
            "return_json_only": True,
            "required_schema": "ops/schemas/referee-verdict.schema.json",
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--issue-id")
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--model", default=os.getenv("MYLES_ANTHROPIC_MODEL", DEFAULT_MODEL))
    parser.add_argument("--simulate-response-file")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output_path).resolve()
    prompt = load_agent_prompt(repo_root / "ops" / "agents" / "claude-referee.md")
    payload = build_payload(repo_root, args.issue_id, args.pr_number, args.head_sha)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.simulate_response_file:
        response_text = _simulated_response(Path(args.simulate_response_file).resolve())
    else:
        response_text = _anthropic_request(prompt, payload, args.model)
    (output_path.parent / "referee-raw-response.txt").write_text(response_text)

    raw_verdict = extract_json_object(response_text)
    schema = load_schema(repo_root, "referee-verdict.schema.json")
    verdict = _prune_verdict_to_schema(raw_verdict, schema)
    verdict.setdefault("schema_version", "1.0")
    verdict.setdefault("issue_id", payload["issue_id"])
    verdict.setdefault("repo", payload["repo"])
    verdict.setdefault("contract_snapshot_hash", payload["contract_snapshot"]["snapshot_hash"])
    verdict.setdefault("review_stage", "pr")
    verdict.setdefault("pr_number", args.pr_number)
    verdict.setdefault("head_sha", args.head_sha)
    verdict.setdefault("findings", [])
    _normalize_findings(verdict)
    verdict.setdefault("confidence", 0.0 if verdict.get("verdict") == "Unavailable" else 0.5)
    if "review_passed" not in verdict:
        verdict["review_passed"] = verdict.get("verdict") == "Pass"
    verdict.setdefault(
        "explanation",
        raw_verdict.get("summary") or raw_verdict.get("reasoning") or "No explanation provided by referee model.",
    )
    verdict.setdefault("reviewed_at", utc_now())

    validate_json(verdict, schema, "referee verdict")
    write_json(output_path, verdict)
    print(f"wrote referee verdict to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except ReviewError as exc:
        print(f"referee review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
