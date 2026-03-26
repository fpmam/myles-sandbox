#!/usr/bin/env python3

import argparse
import os
import subprocess
from pathlib import Path

from build_release_bundle import build_release_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", default="dist/release")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    bundle_path, manifest_path = build_release_bundle(repo_root, args.version, output_dir)
    tag = f"sandbox-v{args.version}"
    title = f"Myles Sandbox {args.version}"
    notes = (
        f"Automated Myles sandbox release for `{args.version}`.\n\n"
        f"- Commit: `{subprocess.run(['git', '-C', str(repo_root), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()}`\n"
        f"- Assets: `{bundle_path.name}`, `{manifest_path.name}`"
    )

    if args.dry_run:
        print(tag)
        print(bundle_path)
        print(manifest_path)
        return

    if not os.getenv("GH_TOKEN"):
        raise SystemExit("GH_TOKEN is required to publish a release")

    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            str(bundle_path),
            str(manifest_path),
            "--title",
            title,
            "--notes",
            notes,
        ],
        check=True,
        cwd=repo_root,
    )
    print(tag)


if __name__ == "__main__":
    main()
