from scripts.wait_for_check_runs import required_check_state, select_latest_check_runs


def test_select_latest_check_runs_prefers_newer_rerun_by_id() -> None:
    payload = {
        "check_runs": [
            {"id": 10, "name": "pytest", "status": "completed", "conclusion": "success"},
            {"id": 12, "name": "pytest", "status": "queued", "conclusion": None},
            {"id": 11, "name": "deterministic-plan-gate", "status": "completed", "conclusion": "success"},
        ]
    }

    latest = select_latest_check_runs(payload)

    assert latest["pytest"]["id"] == 12


def test_required_check_state_reports_missing_checks() -> None:
    missing, incomplete, failed = required_check_state(
        {"pytest": {"status": "completed", "conclusion": "success"}},
        ["pytest", "referee-review"],
    )

    assert missing == ["referee-review"]
    assert incomplete == []
    assert failed == []


def test_required_check_state_reports_incomplete_checks() -> None:
    missing, incomplete, failed = required_check_state(
        {
            "pytest": {"status": "completed", "conclusion": "success"},
            "referee-review": {"status": "in_progress", "conclusion": None},
        },
        ["pytest", "referee-review"],
    )

    assert missing == []
    assert incomplete == ["referee-review"]
    assert failed == []


def test_required_check_state_treats_newer_failed_rerun_as_authoritative() -> None:
    checks = select_latest_check_runs(
        {
            "check_runs": [
                {"id": 20, "name": "pytest", "status": "completed", "conclusion": "success"},
                {"id": 21, "name": "pytest", "status": "completed", "conclusion": "failure"},
            ]
        }
    )

    missing, incomplete, failed = required_check_state(checks, ["pytest"])

    assert missing == []
    assert incomplete == []
    assert failed == ["pytest"]
