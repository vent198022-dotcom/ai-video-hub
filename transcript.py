"""字幕抓取模組：取得影片字幕文字，供 AI 產生深度摘要。

無字幕、字幕關閉、網路失敗一律回傳空字串——字幕是加分項，
絕不可因為抓不到字幕而讓分類流程中斷。

youtube-transcript-api 在 1.x 版把 API 從類別方法改為實例方法：
- 舊版（<1.0）：YouTubeTranscriptApi.get_transcript(video_id, languages=[...])
  回傳 list[dict]，每個 dict 有 "text" 鍵。
- 新版（>=1.0）：YouTubeTranscriptApi().fetch(video_id, languages=[...])
  回傳 FetchedTranscript 物件，其 .to_raw_data() 會轉成 list[dict]（含 "text" 鍵），
  與舊版格式一致。
本模組依實際安裝版本自動適配，統一回傳 list[dict]。
"""
import logging

from youtube_transcript_api import YouTubeTranscriptApi

LANGUAGES = ["zh-TW", "zh-Hant", "zh", "zh-CN", "zh-Hans", "en"]

log = logging.getLogger(__name__)


def _raw_segments(video_id, languages):
    """回傳字幕片段清單，每段為含 text 鍵的 dict。依安裝版本適配套件 API。"""
    try:
        # 新版（1.x+）：實例方法 fetch，回傳 FetchedTranscript，
        # 用 to_raw_data() 轉成 list[dict]
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
        return fetched.to_raw_data()
    except AttributeError:
        # 舊版（<1.0）：類別方法 get_transcript，本身就回傳 list[dict]
        return YouTubeTranscriptApi.get_transcript(video_id, languages=languages)


def fetch(video_id, max_chars=3000):
    """回傳影片字幕純文字（截斷至 max_chars）；取不到時回傳空字串。"""
    try:
        segments = _raw_segments(video_id, LANGUAGES)
        text = " ".join(s["text"].strip() for s in segments if s.get("text"))
        return text[:max_chars]
    except Exception as e:  # 套件會擲出多種自訂例外，一律視為「沒有字幕」
        log.debug("影片 %s 無可用字幕：%s", video_id, e)
        return ""
