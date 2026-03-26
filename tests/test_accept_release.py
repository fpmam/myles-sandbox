import json
from pathlib import Path

from scripts.accept_release import resolve_download_dir, run_acceptance
from scripts.build_release_bundle import build_release_bundle


def test_run_acceptance_passes_for_valid_release_bundle(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bundle_path, manifest_path = build_release_bundle(repo_root, "2026.03.26-acceptance", tmp_path / "release")

    run_acceptance(bundle_path, manifest_path)


def test_run_acceptance_fails_when_bundle_root_is_wrong(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bundle_path, manifest_path = build_release_bundle(repo_root, "2026.03.26-bad", tmp_path / "release")
    manifest = json.loads(manifest_path.read_text())
    manifest["bundle_root"] = "missing-root"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    try:
        run_acceptance(bundle_path, manifest_path)
    except SystemExit as exc:
        assert "Bundle root missing" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_resolve_download_dir_defaults_to_tag_scoped_acceptance_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert resolve_download_dir("sandbox-v2026.03.26-23594946063", None) == (
        tmp_path / "dist" / "acceptance" / "sandbox-v2026.03.26-23594946063"
    ).resolve()


def test_resolve_download_dir_respects_explicit_path(tmp_path: Path) -> None:
    explicit = tmp_path / "downloads"

    assert resolve_download_dir("sandbox-v2026.03.26-23594946063", str(explicit)) == explicit.resolve()
