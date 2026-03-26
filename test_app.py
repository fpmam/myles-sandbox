from app import app, greeting, normalize_name


def test_greeting_returns_expected_message() -> None:
    assert greeting() == "Hello, Myles!"


def test_normalize_name_title_cases_non_empty_values() -> None:
    assert normalize_name(" andrew ") == "Andrew"


def test_normalize_name_defaults_blank_values_to_myles() -> None:
    assert normalize_name("   ") == "Myles"


def test_health_returns_ok_status() -> None:
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_greet_returns_default_payload() -> None:
    client = app.test_client()

    response = client.get("/greet")

    assert response.status_code == 200
    assert response.get_json() == {
        "message": "Hello, Myles!",
        "name": "Myles",
        "style": "plain",
    }


def test_greet_returns_named_payload() -> None:
    client = app.test_client()

    response = client.get("/greet?name=Andrew")

    assert response.status_code == 200
    assert response.get_json() == {
        "message": "Hello, Andrew!",
        "name": "Andrew",
        "style": "plain",
    }


def test_greet_supports_shout_style() -> None:
    client = app.test_client()

    response = client.get("/greet?name=andrew&style=shout")

    assert response.status_code == 200
    assert response.get_json() == {
        "message": "HELLO, ANDREW!",
        "name": "Andrew",
        "style": "shout",
    }


def test_greet_whitespace_name_falls_back_to_default() -> None:
    client = app.test_client()

    response = client.get("/greet?name=%20%20%20")

    assert response.status_code == 200
    assert response.get_json() == {
        "message": "Hello, Myles!",
        "name": "Myles",
        "style": "plain",
    }


def test_greet_rejects_invalid_style() -> None:
    client = app.test_client()

    response = client.get("/greet?style=whisper")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "invalid_style",
        "allowed": ["plain", "shout"],
    }
