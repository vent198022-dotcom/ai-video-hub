"""難易度與國內外補標腳本：為既有已上架但尚未標齊難易度、國內外的內容補標。

只送標題、分類與現有摘要（不送正文），因此一次可處理 100 筆，
成本遠低於重新分類，也不會覆蓋既有摘要。

用法：python tag_metadata.py
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

import classifier
import collector
import db

ROOT = Path(__file__).parent
BATCH_SIZE = 100

log = logging.getLogger("tag_metadata")

_PROMPT = """以下是一批 AI 教學內容（JSON），請為每一筆判斷難易度與國內外。

難易度只能填「入門」「進階」「專家」三者之一：
  入門＝不需任何前置知識，看完就能照做（概念介紹、工具初次使用、介面導覽）
  進階＝預期已用過相關工具，涉及多步驟流程、參數調校、跨工具整合
  專家＝需要程式、API、部署或系統架構背景才能跟上

國內外只能填「國內」「國外」二者之一：
  國內＝文件為繁體中文
  國外＝文件為英文或簡體中文

內容清單：
{items}

只回傳 JSON 陣列，格式：
[{{"video_id": "...", "difficulty": "入門", "region": "國內"}}]"""


def build_prompt(items):
    slim = [{"video_id": i["video_id"], "title": i.get("title", ""),
             "category": i.get("category", ""), "summary": i.get("summary", "")}
            for i in items]
    return _PROMPT.format(items=json.dumps(slim, ensure_ascii=False, indent=1))


def call_gemini(api_key, model, prompt):
    """呼叫 Gemini 並回傳純文字回應。"""
    url = classifier.GEMINI_URL.format(model=model)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    resp = requests.post(url, headers={"x-goog-api-key": api_key},
                         json=body, timeout=120)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def tag_batch(api_key, model, items):
    """回傳 {video_id: {"difficulty": ..., "region": ...}}；
    單筆內非法值會被略去，整批失敗或格式錯誤回傳空 dict。"""
    try:
        text = call_gemini(api_key, model, build_prompt(items))
        results = classifier.parse_response(text)
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        log.warning("補標批次失敗：%s", collector._safe_err(e))
        return {}
    out = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        vid = r.get("video_id")
        if not vid:
            continue
        fields = {}
        if r.get("difficulty") in db.DIFFICULTIES:
            fields["difficulty"] = r["difficulty"]
        if r.get("region") in db.REGIONS:
            fields["region"] = r["region"]
        out[vid] = fields
    return out


def pending_items(conn):
    """已上架但難易度或國內外尚未補齊的內容。"""
    rows = conn.execute(
        "SELECT video_id, title, category, summary FROM videos"
        " WHERE status = 'classified'"
        " AND (difficulty IS NULL OR region IS NULL)"
        " ORDER BY published_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def run(conn, api_key, model, batch_size=BATCH_SIZE, pause_seconds=7):
    """分批補標，回傳成功標記的筆數。單批失敗不中斷後續批次。"""
    items = pending_items(conn)
    log.info("待補標：%d 筆", len(items))
    tagged = 0
    for i in range(0, len(items), batch_size):
        if i > 0 and pause_seconds:
            time.sleep(pause_seconds)
        batch = items[i:i + batch_size]
        for vid, fields in tag_batch(api_key, model, batch).items():
            wrote = False
            if "difficulty" in fields and db.set_difficulty(conn, vid, fields["difficulty"]):
                wrote = True
            if "region" in fields and db.set_region(conn, vid, fields["region"]):
                wrote = True
            if wrote:
                tagged += 1
        log.info("已補標 %d／%d", tagged, len(items))
    return tagged


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("缺少 GEMINI_API_KEY，請檢查 .env")
        return 1
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    conn = db.connect(ROOT / "videos.db")
    n = run(conn, api_key, cfg["gemini"]["model"],
            pause_seconds=cfg["gemini"].get("pause_seconds", 7))
    log.info("補標完成：%d 筆", n)
    log.info("請執行 python main.py 重新產生網頁並發佈")
    return 0


if __name__ == "__main__":
    sys.exit(main())
