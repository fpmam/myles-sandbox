from pathlib import Path

from scripts._gate_common import find_issue_id
from scripts.review_common import infer_issue_id


def _write(path: Path, content: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_gate_common_uses_branch_issue_id_when_multiple_candidates_exist(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _write(repo / ".symphony" / "execution-plan" / "MYLES-SYN-001.json")
    _write(repo / ".symphony" / "execution-plan" / "AND-117.json")
    monkeypatch.setenv("GITHUB_HEAD_REF", "a/and-117-add-a-greet-endpoint")

    assert find_issue_id(repo, None, "execution-plan") == "AND-117"


def test_review_common_uses_branch_issue_id_when_multiple_candidates_exist(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _write(repo / ".symphony" / "contract-snapshot" / "MYLES-SYN-001.json")
    _write(repo / ".symphony" / "execution-plan" / "MYLES-SYN-001.json")
    _write(repo / ".symphony" / "contract-snapshot" / "AND-117.json")
    _write(repo / ".symphony" / "execution-plan" / "AND-117.json")
    monkeypatch.setenv("GITHUB_HEAD_REF", "a/and-117-add-a-greet-endpoint")

    assert infer_issue_id(repo) == "AND-117"
