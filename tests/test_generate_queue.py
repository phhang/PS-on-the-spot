import base64
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import generate as generate_router


ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK9cAAAAASUVORK5CYII="
)
ONE_BY_ONE_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK9cAAAAASUVORK5CYII="
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(generate_router.router)
    return app


def test_generate_queues_background_work_and_saves_recent_history(monkeypatch, tmp_path):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    history_file = tmp_path / "data" / "generated_history.json"

    monkeypatch.setattr(generate_router, "_generated_dir", generated_dir)
    monkeypatch.setattr(generate_router, "_history_file", history_file)

    captured = {}

    async def fake_generate(image_bytes: bytes, prompt: str, width: int, height: int, n: int):
        captured["image_bytes"] = image_bytes
        captured["prompt"] = prompt
        captured["width"] = width
        captured["height"] = height
        captured["n"] = n
        return [ONE_BY_ONE_DATA_URI]

    monkeypatch.setattr(generate_router.gpt_image, "generate", fake_generate)

    app = _make_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            files={"image": ("upload.png", ONE_BY_ONE_PNG, "image/png")},
            data={
                "model": "gpt-image-1.5",
                "prompt": "Add dramatic lighting",
                "width": "1024",
                "height": "1024",
            },
        )

        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        assert captured["prompt"] == "Add dramatic lighting"
        assert captured["width"] == 1024
        assert captured["height"] == 1024
        assert captured["n"] == 1
        assert captured["image_bytes"] == ONE_BY_ONE_PNG

        recent = client.get("/api/generations/recent")
        assert recent.status_code == 200

    history = json.loads(history_file.read_text())
    assert len(history) == 1
    assert history[0]["prompt"] == "Add dramatic lighting"
    assert history[0]["model"] == "gpt-image-1.5"
    assert history[0]["url"].startswith("/generated/")
    assert (generated_dir / history[0]["filename"]).exists()


def test_recent_generations_respects_limit(monkeypatch, tmp_path):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    history_file = tmp_path / "data" / "generated_history.json"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        json.dumps(
            [
                {"id": "1", "prompt": "Newest", "url": "/generated/newest.png"},
                {"id": "2", "prompt": "Second", "url": "/generated/second.png"},
                {"id": "3", "prompt": "Third", "url": "/generated/third.png"},
            ]
        )
    )

    monkeypatch.setattr(generate_router, "_generated_dir", generated_dir)
    monkeypatch.setattr(generate_router, "_history_file", history_file)

    app = _make_app()
    with TestClient(app) as client:
        response = client.get("/api/generations/recent", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [item["prompt"] for item in payload["items"]] == ["Newest", "Second"]