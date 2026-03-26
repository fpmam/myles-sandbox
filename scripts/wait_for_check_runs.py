#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import time


class CheckRunError(RuntimeError):
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


def status_for_checks(repo: str, head_sha: str) -> dict[str, dict]:
    payload = gh_api(f"/repos/{repo}/commits/{head_sha}/check-runs")
    return {item["name"]: item for item in payload.get("check_runs", [])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--required-check", action="append", dest="required_checks", default=[])
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    deadline = time.time() + args.timeout_seconds
    while time.time() < deadline:
        checks = status_for_checks(args.repo, args.head_sha)
        missing = [name for name in args.required_checks if name not in checks]
        if missing:
            time.sleep(args.poll_seconds)
            continue

        incomplete = [
            name
            for name in args.required_checks
            if checks[name]["status"] != "completed"
        ]
        if incomplete:
            time.sleep(args.poll_seconds)
            continue

        failed = [
            name
            for name in args.required_checks
            if checks[name]["conclusion"] != "success"
        ]
        if failed:
            raise CheckRunError(f"Required checks did not pass: {failed}")

        print(f"required checks passed for {args.head_sha}")
        return

    raise CheckRunError(
        f"Timed out after {args.timeout_seconds}s waiting for checks: {args.required_checks}"
    )


if __name__ == "__main__":
    try:
        main()
    except CheckRunError as exc:
        print(f"wait-for-check-runs failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
