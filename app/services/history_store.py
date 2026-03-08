import json
import logging
import sqlite3
from pathlib import Path

from app.config import DATA_DIR, GENERATED_HISTORY_DB

logger = logging.getLogger(__name__)

_db_path = Path(GENERATED_HISTORY_DB)
_legacy_json_path = Path(DATA_DIR) / "generated_history.json"


def _connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_history (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                url TEXT NOT NULL,
                prompt TEXT NOT NULL,
                model TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_filename TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_generation_history_created_at
            ON generation_history (created_at DESC)
            """
        )
        connection.commit()

    _migrate_legacy_json_if_needed()


def _migrate_legacy_json_if_needed() -> None:
    if not _legacy_json_path.exists():
        return

    with _connect() as connection:
        existing_count = connection.execute(
            "SELECT COUNT(*) FROM generation_history"
        ).fetchone()[0]
        if existing_count > 0:
            return

    try:
        entries = json.loads(_legacy_json_path.read_text())
    except json.JSONDecodeError:
        logger.exception("Failed to parse legacy history file: %s", _legacy_json_path)
        return

    if not entries:
        return

    _insert_entries(entries)
    logger.info("Imported %d legacy history entries into SQLite", len(entries))


def _insert_entries(entries: list[dict]) -> None:
    rows = [
        (
            entry["id"],
            entry["job_id"],
            entry["filename"],
            entry["url"],
            entry["prompt"],
            entry["model"],
            entry["submitted_at"],
            entry["created_at"],
            entry["source_filename"],
        )
        for entry in entries
    ]

    with _connect() as connection:
        connection.executemany(
            """
            INSERT OR REPLACE INTO generation_history (
                id,
                job_id,
                filename,
                url,
                prompt,
                model,
                submitted_at,
                created_at,
                source_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()


def add_entries(entries: list[dict]) -> None:
    if not entries:
        return

    init_db()
    _insert_entries(entries)


def list_recent(limit: int) -> list[dict]:
    init_db()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, job_id, filename, url, prompt, model, submitted_at, created_at, source_filename
            FROM generation_history
            ORDER BY datetime(created_at) DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]