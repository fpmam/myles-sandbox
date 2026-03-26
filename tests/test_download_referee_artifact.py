from scripts.download_referee_artifact import ArtifactError, artifact_present, select_run_id


def test_select_run_id_uses_matching_successful_workflow() -> None:
    payload = {
        "workflow_runs": [
            {
                "id": 10,
                "name": "Claude Referee Review",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "failure",
                "run_attempt": 1,
            },
            {
                "id": 11,
                "name": "CI",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
            },
            {
                "id": 12,
                "name": "Claude Referee Review",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
            },
        ]
    }

    assert select_run_id(payload, "Claude Referee Review", "abc123") == 12


def test_select_run_id_prefers_latest_successful_attempt_for_same_head() -> None:
    payload = {
        "workflow_runs": [
            {
                "id": 12,
                "name": "Claude Referee Review",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
                "updated_at": "2026-03-26T12:00:00Z",
            },
            {
                "id": 13,
                "name": "Claude Referee Review",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 2,
                "updated_at": "2026-03-26T12:05:00Z",
            },
        ]
    }

    assert select_run_id(payload, "Claude Referee Review", "abc123") == 13


def test_select_run_id_ignores_other_head_shas() -> None:
    payload = {
        "workflow_runs": [
            {
                "id": 12,
                "name": "Claude Referee Review",
                "head_sha": "other",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
            },
            {
                "id": 13,
                "name": "Claude Referee Review",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
            },
        ]
    }

    assert select_run_id(payload, "Claude Referee Review", "abc123") == 13


def test_select_run_id_raises_when_no_successful_match_exists() -> None:
    payload = {
        "workflow_runs": [
            {
                "id": 10,
                "name": "Claude Referee Review",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "failure",
                "run_attempt": 1,
            },
        ]
    }

    try:
        select_run_id(payload, "Claude Referee Review", "abc123")
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
