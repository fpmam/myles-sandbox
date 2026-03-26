from scripts.download_referee_artifact import ArtifactError, artifact_present, select_run_id


def test_select_run_id_uses_matching_successful_workflow() -> None:
    payload = {
        "workflow_runs": [
            {"id": 10, "name": "Claude Referee Review", "status": "completed", "conclusion": "failure"},
            {"id": 11, "name": "CI", "status": "completed", "conclusion": "success"},
            {"id": 12, "name": "Claude Referee Review", "status": "completed", "conclusion": "success"},
        ]
    }

    assert select_run_id(payload, "Claude Referee Review") == 12


def test_select_run_id_raises_when_no_successful_match_exists() -> None:
    payload = {
        "workflow_runs": [
            {"id": 10, "name": "Claude Referee Review", "status": "completed", "conclusion": "failure"},
        ]
    }

    try:
        select_run_id(payload, "Claude Referee Review")
    except ArtifactError as exc:
        assert "No successful" in str(exc)
    else:
        raise AssertionError("expected ArtifactError")


def test_artifact_present_ignores_expired_entries() -> None:
    payload = {
        "artifacts": [
            {"name": "referee-verdict", "expired": True},
            {"name": "other", "expired": False},
            {"name": "referee-verdict", "expired": False},
        ]
    }

    assert artifact_present(payload, "referee-verdict") is True
