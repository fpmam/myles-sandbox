import json
import subprocess
import tarfile
from pathlib import Path

from scripts.build_release_bundle import build_release_bundle


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Codex"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "codex@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/fpmam/myles-sandbox.git"], check=True)
    _write(repo / "README.md", "# Repo\n")
    _write(repo / "app.py", "print('hello')\n")
    _write(repo / "requirements.txt", "flask==3.1.0\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    return repo


def test_build_release_bundle_writes_bundle_and_manifest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    bundle_path, manifest_path = build_release_bundle(repo, "2026.03.26-123", repo / "dist")

    assert bundle_path.exists()
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == "1.0"
    assert manifest["repo"] == "fpmam/myles-sandbox"
    assert manifest["version"] == "2026.03.26-123"
    assert manifest["bundle_name"] == bundle_path.name
    assert manifest["acceptance_targets"] == ["/health", "/greet"]

    with tarfile.open(bundle_path, "r:gz") as archive:
        names = archive.getnames()

    assert "myles-sandbox-2026.03.26-123/README.md" in names
    assert "myles-sandbox-2026.03.26-123/app.py" in names
    assert "myles-sandbox-2026.03.26-123/requirements.txt" in names
