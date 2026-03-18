from pathlib import Path


def test_readme_matches_issue_requirements() -> None:
    readme = Path("README.md").read_text().splitlines()

    assert readme[:2] == [
        "# Myles Sandbox",
        "",
    ]
    assert readme[2] == "Smoke-test repository for the Myles autonomous development pipeline."
