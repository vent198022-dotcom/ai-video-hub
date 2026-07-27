"""SQLite 資料存取層：影片與中繼資料的唯一儲存介面。"""
import json
import sqlite3

DIFFICULTIES = ("入門", "進階", "專家")
REGIONS = ("國內", "國外")
SAFETY = ("安全", "疑慮")

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
    search_terms     TEXT,
    url              TEXT,
    content_type     TEXT NOT NULL DEFAULT 'video',
    difficulty       TEXT,
    region           TEXT,
    license          TEXT,
    security_score   REAL,
    safety           TEXT,
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
    _migrate(conn)
    return conn


def _migrate(conn):
    """既有資料庫缺新欄位時補上（ALTER TABLE，不動既有資料）。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(videos)")}
    added = False
    if "search_terms" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN search_terms TEXT")
        added = True
    if "url" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN url TEXT")
        added = True
    if "content_type" not in cols:
        # 既有列一律視為影片
        conn.execute(
            "ALTER TABLE videos ADD COLUMN content_type TEXT NOT NULL DEFAULT 'video'")
        added = True
    if "difficulty" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN difficulty TEXT")
        added = True
    if "region" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN region TEXT")
        added = True
    if "license" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN license TEXT")
        added = True
    if "security_score" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN security_score REAL")
        added = True
    if "safety" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN safety TEXT")
        added = True
    if added:
        conn.commit()


def video_exists(conn, video_id):
    row = conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    return row is not None


def insert_video(conn, video):
    """寫入一筆內容（影片或文章）。content_type 未給時預設為 video。"""
    row = {"content_type": "video", "url": None, "license": None, "security_score": None, **video}
    conn.execute(
        "INSERT OR IGNORE INTO videos"
        " (video_id, title, channel, description, published_at,"
        "  thumbnail_url, duration_seconds, view_count, url, content_type, license, security_score, status)"
        " VALUES (:video_id, :title, :channel, :description, :published_at,"
        "  :thumbnail_url, :duration_seconds, :view_count, :url, :content_type,"
        "  :license, :security_score, 'pending')",
        row,
    )
    conn.commit()


def get_videos_by_status(conn, status):
    rows = conn.execute(
        "SELECT * FROM videos WHERE status = ? ORDER BY collected_at", (status,)
    ).fetchall()
    return [dict(r) for r in rows]


def update_classification(conn, video_id, is_relevant, category, summary, tags,
                          search_terms=None, difficulty=None, region=None, safety=None):
    status = "classified" if is_relevant else "excluded"
    conn.execute(
        "UPDATE videos SET status = ?, category = ?, summary = ?, tags = ?,"
        " search_terms = ?, difficulty = ?, region = ?, safety = ? WHERE video_id = ?",
        (status, category, summary,
         json.dumps(tags or [], ensure_ascii=False),
         json.dumps(search_terms or [], ensure_ascii=False),
         difficulty if difficulty in DIFFICULTIES else None,
         region if region in REGIONS else None,
         safety if safety in SAFETY else None,
         video_id),
    )
    conn.commit()


def mark_failed(conn, video_id):
    conn.execute("UPDATE videos SET status = 'failed' WHERE video_id = ?", (video_id,))
    conn.commit()


def mark_removed(conn, video_ids):
    """批次標記影片為已失效（下架／轉私人），回傳筆數。"""
    if not video_ids:
        return 0
    placeholders = ",".join("?" * len(video_ids))
    cur = conn.execute(
        f"UPDATE videos SET status = 'removed' WHERE video_id IN ({placeholders})",
        list(video_ids),
    )
    conn.commit()
    return cur.rowcount


def drop_items(conn, video_ids):
    """把指定項目標記為人工下架，回傳實際變更筆數。

    不刪除資料列——保留紀錄，下次收集才不會又把它抓回來。

    已標記為 removed（失效清理判定的死連結）的項目略過不處理：
    它已經不會出現在網站上、也已被 video_id 主鍵擋掉重複收集，
    若讓它轉成 dropped，日後從 remove.txt 移除該行會被
    restore_dropped 誤判為「要復原」而讓死連結重新上架。
    """
    ids = [i for i in dict.fromkeys(video_ids) if i]
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE videos SET status = 'dropped'"
        f" WHERE video_id IN ({placeholders})"
        f" AND status NOT IN ('dropped', 'removed')",
        ids,
    )
    conn.commit()
    return cur.rowcount


def restore_dropped(conn, keep_ids):
    """復原不在 keep_ids 內的人工下架項目，回傳復原筆數。

    先前分類過的（有 category）回到 classified；未分類過的回到 pending 重新分類。
    """
    keep = [i for i in dict.fromkeys(keep_ids) if i]
    where = "status = 'dropped'"
    params = []
    if keep:
        where += f" AND video_id NOT IN ({','.join('?' * len(keep))})"
        params = keep
    cur = conn.execute(
        f"UPDATE videos SET status ="
        f" CASE WHEN category IS NOT NULL THEN 'classified' ELSE 'pending' END"
        f" WHERE {where}",
        params,
    )
    conn.commit()
    return cur.rowcount


def set_difficulty(conn, video_id, difficulty):
    """單獨設定難易度（供補標腳本使用）。值不合法時不寫入並回傳 False。"""
    if difficulty not in DIFFICULTIES:
        return False
    conn.execute("UPDATE videos SET difficulty = ? WHERE video_id = ?",
                 (difficulty, video_id))
    conn.commit()
    return True


def set_region(conn, video_id, region):
    """單獨設定國內／國外（供補標腳本使用）。值不合法時不寫入並回傳 False。"""
    if region not in REGIONS:
        return False
    conn.execute("UPDATE videos SET region = ? WHERE video_id = ?",
                 (region, video_id))
    conn.commit()
    return True


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
        " thumbnail_url, view_count, category, summary, tags, search_terms, url, content_type,"
        " difficulty, region, license, security_score, safety"
        " FROM videos WHERE status = 'classified' ORDER BY published_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        d["search_terms"] = json.loads(d["search_terms"] or "[]")
        out.append(d)
    return out
