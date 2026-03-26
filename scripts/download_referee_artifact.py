#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode


class ArtifactError(RuntimeError):
    pass


def gh_api(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    return json.loads(result.stdout)


def workflow_run_sort_key(run: dict) -> tuple[int, str, str, int]:
    return (
        int(run.get("run_attempt") or 0),
        str(run.get("updated_at") or ""),
        str(run.get("created_at") or ""),
        int(run.get("id") or 0),
    )


def select_run_id(payload: dict, workflow_name: str, head_sha: str) -> int:
    candidates = []
    for run in payload.get("workflow_runs", []):
        if run.get("name") != workflow_name:
            continue
        if run.get("head_sha") != head_sha:
            continue
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") != "success":
            continue
        candidates.append(run)

    if not candidates:
        raise ArtifactError(
            f"No successful '{workflow_name}' run matched head SHA {head_sha}"
        )

    latest = max(candidates, key=workflow_run_sort_key)
    return int(latest["id"])


def artifact_present(payload: dict, artifact_name: str) -> bool:
    return any(
        artifact.get("name") == artifact_name and not artifact.get("expired", False)
        for artifact in payload.get("artifacts", [])
    )


def download_artifact(repo: str, run_id: int, artifact_name: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "gh",
            "run",
            "download",
            str(run_id),
            "-R",
            repo,
            "-n",
            artifact_name,
            "-D",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        raise ArtifactError(result.stderr.strip() or result.stdout.strip() or "gh run download failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--workflow-name", default="Claude Referee Review")
    parser.add_argument("--artifact-name", default="referee-verdict")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    query = urlencode(
        {
            "event": "pull_request",
            "head_sha": args.head_sha,
            "per_page": 50,
        }
    )
    runs = gh_api(f"/repos/{args.repo}/actions/runs?{query}")
    run_id = select_run_id(runs, args.workflow_name, args.head_sha)
    artifacts = gh_api(f"/repos/{args.repo}/actions/runs/{run_id}/artifacts")
    if not artifact_present(artifacts, args.artifact_name):
        raise ArtifactError(
            f"Run {run_id} did not publish a non-expired '{args.artifact_name}' artifact"
        )
    download_artifact(args.repo, run_id, args.artifact_name, Path(args.output_dir).resolve())
    print(f"downloaded {args.artifact_name} from run {run_id}")


if __name__ == "__main__":
    try:
        main()
    except ArtifactError as exc:
        print(f"download-referee-artifact failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
