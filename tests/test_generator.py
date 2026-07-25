"""generator 模組測試。"""
import json

from conftest import make_video

import db
import generator


def test_generate_writes_videos_json(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.insert_video(conn, make_video("v1"))
    db.update_classification(conn, "v1", True, "工具教學", "教學摘要", ["ChatGPT"])
    db.insert_video(conn, make_video("v2"))  # pending，不應出現在輸出

    count = generator.generate(conn, tmp_path / "docs")

    data = json.loads((tmp_path / "docs" / "videos.json").read_text(encoding="utf-8"))
    assert count == 1
    assert data["count"] == 1
    assert "generated_at" in data
    v = data["videos"][0]
    assert v["video_id"] == "v1"
    assert v["category"] == "工具教學"
    assert v["tags"] == ["ChatGPT"]
    assert v["summary"] == "教學摘要"


def test_generate_empty_db(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    count = generator.generate(conn, tmp_path / "docs")
    data = json.loads((tmp_path / "docs" / "videos.json").read_text(encoding="utf-8"))
    assert count == 0
    assert data["videos"] == []


def test_generate_creates_dir_if_missing(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    target = tmp_path / "深層" / "目錄" / "docs"
    generator.generate(conn, target)
    assert (target / "videos.json").exists()
