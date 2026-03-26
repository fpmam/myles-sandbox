#!/usr/bin/env python3

import argparse
import json
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

IGNORED_PARTS = {
    ".git",
    ".hal",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def repo_identity(repo_root: Path) -> str:
    remote = git_output(repo_root, "remote", "get-url", "origin")
    if remote.endswith(".git"):
        remote = remote[:-4]
    if remote.startswith("https://"):
        remote = remote.split("https://", 1)[1]
    if remote.startswith("http://"):
        remote = remote.split("http://", 1)[1]
    if "github.com/" in remote:
        remote = remote.split("github.com/", 1)[1]
    elif ":" in remote:
        remote = remote.split(":", 1)[1]
    return remote.rstrip("/")


def build_release_bundle(repo_root: Path, version: str, output_dir: Path) -> tuple[Path, Path]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle_name = f"myles-sandbox-{version}.tar.gz"
    bundle_path = output_dir / bundle_name
    prefix = f"myles-sandbox-{version}/"

    with tarfile.open(bundle_path, "w:gz") as archive:
        for path in sorted(repo_root.rglob("*")):
            relative = path.relative_to(repo_root)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if path.is_dir():
                continue
            archive.add(path, arcname=f"{prefix}{relative.as_posix()}")

    manifest = {
        "schema_version": "1.0",
        "repo": repo_identity(repo_root),
        "version": version,
        "git_commit_sha": git_output(repo_root, "rev-parse", "HEAD"),
        "released_at": utc_now(),
        "bundle_name": bundle_name,
        "bundle_root": prefix.rstrip("/"),
        "acceptance_targets": [
            "/health",
            "/greet",
        ],
    }
    manifest_path = output_dir / f"release-manifest-{version}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return bundle_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", default="dist/release")
    args = parser.parse_args()

    bundle_path, manifest_path = build_release_bundle(
        Path(args.repo_root),
        args.version,
        Path(args.output_dir),
    )
    print(bundle_path)
    print(manifest_path)


if __name__ == "__main__":
    main()
