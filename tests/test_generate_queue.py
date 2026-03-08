import base64
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import generate as generate_router
from app.services import history_store


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
    history_db = tmp_path / "data" / "generated_history.db"

    monkeypatch.setattr(generate_router, "_generated_dir", generated_dir)
    monkeypatch.setattr(history_store, "_db_path", history_db)
    monkeypatch.setattr(history_store, "_legacy_json_path", tmp_path / "data" / "generated_history.json")

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

    with sqlite3.connect(history_db) as connection:
        row = connection.execute(
            "SELECT prompt, model, url, filename FROM generation_history"
        ).fetchone()

    assert row is not None
    assert row[0] == "Add dramatic lighting"
    assert row[1] == "gpt-image-1.5"
    assert row[2].startswith("/generated/")
    assert (generated_dir / row[3]).exists()


def test_recent_generations_respects_limit(monkeypatch, tmp_path):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    history_db = tmp_path / "data" / "generated_history.db"

    monkeypatch.setattr(generate_router, "_generated_dir", generated_dir)
    monkeypatch.setattr(history_store, "_db_path", history_db)
    monkeypatch.setattr(history_store, "_legacy_json_path", tmp_path / "data" / "generated_history.json")

    history_store.init_db()
    with sqlite3.connect(history_db) as connection:
        connection.executemany(
            """
            INSERT INTO generation_history (
                id, job_id, filename, url, prompt, model, submitted_at, created_at, source_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "1",
                    "job-1",
                    "newest.png",
                    "/generated/newest.png",
                    "Newest",
                    "gpt-image-1.5",
                    "2026-03-08T10:00:00+00:00",
                    "2026-03-08T10:00:00+00:00",
                    "upload.png",
                ),
                (
                    "2",
                    "job-2",
                    "second.png",
                    "/generated/second.png",
                    "Second",
                    "gpt-image-1.5",
                    "2026-03-08T09:00:00+00:00",
                    "2026-03-08T09:00:00+00:00",
                    "upload.png",
                ),
                (
                    "3",
                    "job-3",
                    "third.png",
                    "/generated/third.png",
                    "Third",
                    "gpt-image-1.5",
                    "2026-03-08T08:00:00+00:00",
                    "2026-03-08T08:00:00+00:00",
                    "upload.png",
                ),
            ],
        )
        connection.commit()

    app = _make_app()
    with TestClient(app) as client:
        response = client.get("/api/generations/recent", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [item["prompt"] for item in payload["items"]] == ["Newest", "Second"]


def test_init_db_imports_legacy_json_once(monkeypatch, tmp_path):
    history_db = tmp_path / "data" / "generated_history.db"
    legacy_json = tmp_path / "data" / "generated_history.json"
    legacy_json.parent.mkdir(parents=True, exist_ok=True)
    legacy_json.write_text(
        """
        [
          {
            "id": "legacy-1",
            "job_id": "job-legacy-1",
            "filename": "legacy.png",
            "url": "/generated/legacy.png",
            "prompt": "Legacy prompt",
            "model": "gpt-image-1.5",
            "submitted_at": "2026-03-08T10:00:00+00:00",
            "created_at": "2026-03-08T10:00:00+00:00",
            "source_filename": "legacy-upload.png"
          }
        ]
        """.strip()
    )

    monkeypatch.setattr(history_store, "_db_path", history_db)
    monkeypatch.setattr(history_store, "_legacy_json_path", legacy_json)

    history_store.init_db()
    history_store.init_db()

    items = history_store.list_recent(10)
    assert len(items) == 1
    assert items[0]["prompt"] == "Legacy prompt"