"""測試共用工廠函式。"""


def make_video(video_id="abc123", **over):
    v = {
        "video_id": video_id,
        "title": "測試影片標題",
        "channel": "測試頻道",
        "description": "這是一部測試用的 AI 教學影片描述",
        "published_at": "2026-07-01T00:00:00Z",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "duration_seconds": 300,
        "view_count": 100,
    }
    v.update(over)
    return v
