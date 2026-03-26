# Myles Sandbox

This repository is a minimal public sandbox for validating the Myles, Symphony, and Codex pipeline.

It is intentionally small, but it now carries a real API contract so the full Myles workflow can be
proved against meaningful behavior instead of synthetic plumbing alone.

## Endpoints

### `GET /health`
- Returns `200` with `{"status": "ok"}`.

### `GET /greet`
- Returns `200` with JSON containing `message`, `name`, and `style`.
- Query params:
  - `name`: optional display name. Blank or whitespace-only input falls back to `Myles`.
  - `style`: optional. Allowed values are `plain` and `shout`. Defaults to `plain`.
- Invalid `style` values return `400` with:
  - `{"error": "invalid_style", "allowed": ["plain", "shout"]}`

## Local Verification

Run the app tests with:

```bash
./.venv/bin/python -m pytest -q
```
