"""SQLite 資料存取層：影片與中繼資料的唯一儲存介面。"""
import json
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id         TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    channel          TEXT,
    description      TEXT,
    published_at     TEXT,
    thumbnail_url    TEXT,
    duration_seconds INTEGER,
    view_count       INTEGER,
    category         TEXT,
    summary          TEXT,
    tags             TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    collected_at     TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def video_exists(conn, video_id):
    row = conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    return row is not None


def insert_video(conn, video):
    conn.execute(
        "INSERT OR IGNORE INTO videos"
        " (video_id, title, channel, description, published_at,"
        "  thumbnail_url, duration_seconds, view_count, status)"
        " VALUES (:video_id, :title, :channel, :description, :published_at,"
        "  :thumbnail_url, :duration_seconds, :view_count, 'pending')",
        video,
    )
    conn.commit()


def get_videos_by_status(conn, status):
    rows = conn.execute(
        "SELECT * FROM videos WHERE status = ? ORDER BY collected_at", (status,)
    ).fetchall()
    return [dict(r) for r in rows]


def update_classification(conn, video_id, is_relevant, category, summary, tags):
    status = "classified" if is_relevant else "excluded"
    conn.execute(
        "UPDATE videos SET status = ?, category = ?, summary = ?, tags = ?"
        " WHERE video_id = ?",
        (status, category, summary, json.dumps(tags or [], ensure_ascii=False), video_id),
    )
    conn.commit()


def mark_failed(conn, video_id):
    conn.execute("UPDATE videos SET status = 'failed' WHERE video_id = ?", (video_id,))
    conn.commit()


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_site_videos(conn):
    rows = conn.execute(
        "SELECT video_id, title, channel, duration_seconds, published_at,"
        " thumbnail_url, view_count, category, summary, tags"
        " FROM videos WHERE status = 'classified' ORDER BY published_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        out.append(d)
    return out
