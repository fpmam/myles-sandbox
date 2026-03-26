#!/usr/bin/env python3

import argparse
import importlib.util
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path


def download_release_assets(repo: str, tag: str, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--dir",
            str(output_dir),
            "--pattern",
            "*.tar.gz",
            "--pattern",
            "release-manifest-*.json",
            "--clobber",
        ],
        check=True,
    )

    bundles = sorted(output_dir.glob("*.tar.gz"))
    manifests = sorted(output_dir.glob("release-manifest-*.json"))
    if len(bundles) != 1 or len(manifests) != 1:
        raise SystemExit("Expected exactly one bundle and one manifest in the downloaded release assets")
    return bundles[0], manifests[0]


def load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_acceptance(bundle_path: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        with tarfile.open(bundle_path, "r:gz") as archive:
            archive.extractall(temp_path)

        bundle_root = temp_path / manifest["bundle_root"]
        if not bundle_root.exists():
            raise SystemExit(f"Bundle root missing from extracted release: {bundle_root}")

        app_module = load_module(bundle_root / "app.py", "released_app")
        client = app_module.app.test_client()

        health_response = client.get("/health")
        if health_response.status_code != 200 or health_response.get_json() != {"status": "ok"}:
            raise SystemExit("Released artifact failed /health acceptance check")

        greet_response = client.get("/greet?name=andrew&style=shout")
        if greet_response.status_code != 200:
            raise SystemExit("Released artifact failed /greet status acceptance check")
        if greet_response.get_json() != {
            "message": "HELLO, ANDREW!",
            "name": "Andrew",
            "style": "shout",
        }:
            raise SystemExit("Released artifact failed /greet payload acceptance check")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-path")
    parser.add_argument("--manifest-path")
    parser.add_argument("--repo", default="fpmam/myles-sandbox")
    parser.add_argument("--tag")
    parser.add_argument("--download-dir", default="dist/acceptance")
    args = parser.parse_args()

    bundle_path = Path(args.bundle_path).resolve() if args.bundle_path else None
    manifest_path = Path(args.manifest_path).resolve() if args.manifest_path else None

    if bundle_path is None or manifest_path is None:
        if not args.tag:
            raise SystemExit("Either --bundle-path/--manifest-path or --tag must be provided")
        bundle_path, manifest_path = download_release_assets(
            args.repo,
            args.tag,
            Path(args.download_dir).resolve(),
        )

    run_acceptance(bundle_path, manifest_path)
    print(f"accepted release bundle {bundle_path.name}")


if __name__ == "__main__":
    main()
