import subprocess
from pathlib import Path


def _check_ignore(*paths: str) -> list[str]:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "check-ignore", *paths],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line]


def test_dist_artifact_paths_are_ignored() -> None:
    ignored = _check_ignore(
        "dist/release/example.tar.gz",
        "dist/acceptance/example.tar.gz",
        "dist/acceptance-and-133/release-manifest.json",
    )
    assert ignored == [
        "dist/release/example.tar.gz",
        "dist/acceptance/example.tar.gz",
        "dist/acceptance-and-133/release-manifest.json",
    ]


def test_tracked_repo_files_are_not_hidden_by_dist_ignore_rule() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "check-ignore", ".symphony/config.yml"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
