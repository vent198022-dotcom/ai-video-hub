"""title_filter 模組測試：依標題排除非中文、日文、廣東話影片。"""
import pytest

import title_filter


@pytest.mark.parametrize("title", [
    "ChatGPT 教學：10 分鐘學會寫提示詞",
    "【n8n 自動化】從零打造 AI Agent",
    "Claude Code 入门教程，小白也能上手",          # 簡體中文照收
    "Google Vids 手機教學：AI 讓貓咪跳舞",           # 「咪」不得誤判為廣東話
    "NotebookLM 教學・完整版",                      # 全形中點不是日文
    "AI 繪圖教學ー進階篇",                          # 長音符號單獨出現不算日文
    "AI・ChatGPT・教學ー入門",                      # 「・」「ー」出現多次也不算假名
    "【白話看AI】從『電腦揀花生』看懂 AI 意圖分類",   # 「揀」是國語常用字
    "這個 AI 工具真的這麼好用咩？實測給你看",         # 「咩」在台灣網路用語是語尾
    "AI 強強聯手：NotebookLM + Gemini｜Google應用微課程｜すごい知識站",  # 頻道名夾少量假名
    "我の AI 日常：用 ChatGPT 規劃一週",              # 台灣標題借用「の」
    "【最新热播AI剧】《简助理你为何那样》#短编剧",     # 簡體字「编」不是日文
    "AI 出錯 ¯\\_(ツ)_/¯",                          # 顏文字裡的單一片假名不算日文
])
def test_accepts_mandarin_titles(title):
    assert title_filter.reject_reason(title) is None


@pytest.mark.parametrize("title", [
    "How to Scrape LinkedIn for Free Using Claude",
    "Google Gemini Notebook 2026: 10 tính năng",
    "",
    "🔥🔥 2026 !!!",
])
def test_rejects_titles_without_chinese(title):
    assert title_filter.reject_reason(title) == "非中文"


@pytest.mark.parametrize("title", [
    "【速報】Gemini 4 Argon登場！3大AI比較検証と使ってみた",
    "究極のクエスト：バリ取りの極意に会社プレゼン喰わせて",
    "Claude Codeで業務自動化",                      # 只有一個假名，但用了日文助詞
    "【中国AI速報】EC完全自動化、日本は？",
])
def test_rejects_japanese_titles(title):
    assert title_filter.reject_reason(title) == "日文"


@pytest.mark.parametrize("title", [
    "【Codex 教學】請唔起人？打造你的AI員工",
    "用 Claude Opus 5 寫咗個鋼鐵俠 JARVIS",
    "睇完呢支 你係辦公室最識用 AI 嘅人",
    "AI 剪片實測：新手都出到專業級廣告片（廣東話）",
    "【粵語AI教學】AI繪圖入門教學",
    "請兩個 AI 同事住喺你個 chat",
    "9成人冇用嘅功能",
    "AI自動搵工系統",
])
def test_rejects_cantonese_titles(title):
    assert title_filter.reject_reason(title) == "廣東話"


def test_none_title_treated_as_non_chinese():
    assert title_filter.reject_reason(None) == "非中文"
