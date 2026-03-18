from app import app, greeting


def test_greeting_returns_expected_message() -> None:
    assert greeting() == "Hello, Myles!"


def test_health_returns_ok_status() -> None:
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
