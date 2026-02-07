"""
Database layer - SQLite per gestione video scaricati.
"""

import os
import sqlite3
from datetime import datetime


DB_NAME = "ytdownloader.db"


def _get_db_path():
    """Ritorna il path del database, compatibile Android e desktop."""
    try:
        from android.storage import app_storage_path  # type: ignore
        base = app_storage_path()
    except ImportError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, DB_NAME)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Crea le tabelle se non esistono."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL,
            title       TEXT NOT NULL DEFAULT '',
            filepath    TEXT NOT NULL DEFAULT '',
            filesize    INTEGER NOT NULL DEFAULT 0,
            duration    TEXT NOT NULL DEFAULT '',
            quality     TEXT NOT NULL DEFAULT '',
            thumbnail   TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'pending',
            progress    REAL NOT NULL DEFAULT 0,
            error_msg   TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_video(url: str, quality: str) -> int:
    """Inserisce un nuovo video e ritorna l'id."""
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO videos (url, quality, status, created_at, updated_at) VALUES (?, ?, 'pending', ?, ?)",
        (url, quality, now, now),
    )
    vid = cur.lastrowid
    conn.commit()
    conn.close()
    return vid


def update_video(vid: int, **fields):
    """Aggiorna i campi specificati."""
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [vid]
    conn = get_connection()
    conn.execute(f"UPDATE videos SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_video(vid: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (vid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_videos() -> list[dict]:
    """Ritorna tutti i video ordinati per data (piu recenti prima)."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM videos ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_completed_videos() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM videos WHERE status = 'completed' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_video(vid: int):
    """Elimina il record e il file associato."""
    video = get_video(vid)
    if video and video.get("filepath") and os.path.exists(video["filepath"]):
        try:
            os.remove(video["filepath"])
        except OSError:
            pass
    conn = get_connection()
    conn.execute("DELETE FROM videos WHERE id = ?", (vid,))
    conn.commit()
    conn.close()


def get_total_size() -> int:
    """Ritorna la dimensione totale in byte dei file scaricati."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(filesize), 0) as total FROM videos WHERE status = 'completed'"
    ).fetchone()
    conn.close()
    return row["total"] if row else 0
