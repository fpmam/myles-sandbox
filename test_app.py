from app import greeting


def test_greeting_returns_expected_message() -> None:
    assert greeting() == "Hello, Myles!"
