from flask import Flask, jsonify


app = Flask(__name__)


def greeting(name: str = "Myles") -> str:
    return f"Hello, {name}!"


@app.get("/health")
def health() -> tuple[object, int]:
    return jsonify({"status": "ok"}), 200
