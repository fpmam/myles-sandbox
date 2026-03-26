from flask import Flask, jsonify, request


app = Flask(__name__)
ALLOWED_STYLES = ("plain", "shout")


def normalize_name(name: str | None) -> str:
    trimmed = (name or "").strip()
    if not trimmed:
        return "Myles"
    return trimmed.title()


def greeting(name: str = "Myles", style: str = "plain") -> str:
    message = f"Hello, {name}!"
    if style == "shout":
        return message.upper()
    return message


@app.get("/health")
def health() -> tuple[object, int]:
    return jsonify({"status": "ok"}), 200


@app.get("/greet")
def greet() -> tuple[object, int]:
    style = request.args.get("style", "plain")
    if style not in ALLOWED_STYLES:
        return jsonify({"error": "invalid_style", "allowed": list(ALLOWED_STYLES)}), 400

    name = normalize_name(request.args.get("name"))
    return jsonify({"message": greeting(name, style=style), "name": name, "style": style}), 200
