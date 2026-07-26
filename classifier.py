"""AI 分類模組：批次呼叫 Gemini 做相關性過濾、分類、摘要、標籤。"""
import json
import logging
import time

import requests

import db

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """你是影片內容分類助手。以下是內容清單（JSON，可能是 YouTube 影片或網路文章），請逐一判斷：
1. is_relevant：是否為「中文的 AI 相關教學影片」，必須同時滿足兩個條件：
   (a) 語言為中文（繁體或簡體皆可）；英文、日文、韓文等非中文內容一律不相關
   (b) 內容為教學、實作、應用示範；純新聞、廣告、閒聊、蹭關鍵字的不算
2. category：從固定清單中選一個，不得自創：{categories}
3. summary：繁體中文摘要，依下列三種情況擇一（互斥，只符合一種）：
   (a) 附有字幕逐字稿內容 → 必須依據逐字稿內容撰寫 80~120 字的具體摘要，說明實際教了哪些步驟或工具
   (b) 屬於文章（content_type 為 article）→ 依 description 內的正文撰寫 80~120 字摘要
   (c) 以上皆非（無逐字稿的影片）→ 依標題與描述撰寫 50~80 字摘要
4. tags：1~4 個簡短標籤
5. search_terms：5~10 個搜尋詞，涵蓋同義詞、口語說法、英文對照與相關情境用語。
   例如一部教 AI 寫 email 的影片可給：["回信", "email", "電子郵件", "郵件回覆", "客服回信", "書信"]。
   目的是讓使用者用日常說法也搜得到這部影片。
6. difficulty：難易度，只能填「入門」「進階」「專家」三者之一：
   入門＝不需任何前置知識，看完就能照做（概念介紹、工具初次使用、介面導覽）
   進階＝預期已用過相關工具，涉及多步驟流程、參數調校、跨工具整合
   專家＝需要程式、API、部署或系統架構背景才能跟上

影片清單：
{videos}

只回傳 JSON 陣列，每部影片一個物件，格式：
[{{"video_id": "...", "is_relevant": true, "category": "...", "summary": "...", "tags": ["..."], "search_terms": ["..."], "difficulty": "入門"}}]
不相關的影片 is_relevant 填 false、category 填 null、summary 填空字串、tags 填空陣列。"""


def build_prompt(videos, categories):
    slim = []
    for v in videos:
        is_article = v.get("content_type") == "article"
        item = {
            "video_id": v["video_id"],
            "title": v["title"],
            "channel": v.get("channel", ""),
            "description": (v.get("description") or "")[:3000 if is_article else 300],
        }
        if is_article:
            item["content_type"] = "article"
        if v.get("transcript"):
            item["transcript"] = v["transcript"]
        slim.append(item)
    return _PROMPT_TEMPLATE.format(
        categories="、".join(categories),
        videos=json.dumps(slim, ensure_ascii=False, indent=1),
    )


def parse_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("AI 回傳的不是 JSON 陣列")
    return data


def classify_batch(api_key, model, videos, categories):
    url = GEMINI_URL.format(model=model)
    body = {
        "contents": [{"parts": [{"text": build_prompt(videos, categories)}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    # 金鑰放 header 而非網址參數，避免錯誤訊息把金鑰寫進 log
    resp = requests.post(url, headers={"x-goog-api-key": api_key}, json=body, timeout=120)
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return parse_response(text)


def classify_pending(conn, api_key, model, categories, batch_size=10,
                     pause_seconds=6, transcript_fn=None):
    """分類所有 pending 與 failed 影片。回傳 (上架數, 排除數, 失敗數)。

    transcript_fn 若提供，會在分類前對每部影片取字幕併入 prompt，
    讓 AI 依實際內容寫出更深入的摘要。
    """
    queue = db.get_videos_by_status(conn, "pending") + db.get_videos_by_status(conn, "failed")
    ok = skip = fail = 0

    for i in range(0, len(queue), batch_size):
        if i > 0 and pause_seconds:
            time.sleep(pause_seconds)  # 批次間隔，避免超過 Gemini 免費層每分鐘請求上限
        batch = queue[i:i + batch_size]
        if transcript_fn:
            for v in batch:
                if v.get("content_type") != "article":
                    v["transcript"] = transcript_fn(v["video_id"])
        try:
            results = classify_batch(api_key, model, batch, categories)
            by_id = {r["video_id"]: r for r in results if isinstance(r, dict) and "video_id" in r}
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            log.warning("批次分類失敗，整批標記待重試：%s", e)
            for v in batch:
                db.mark_failed(conn, v["video_id"])
            fail += len(batch)
            continue

        for v in batch:
            r = by_id.get(v["video_id"])
            if r is None:
                db.mark_failed(conn, v["video_id"])
                fail += 1
                continue
            relevant = bool(r.get("is_relevant"))
            category = r.get("category")
            if relevant and category not in categories:
                # AI 自創分類：標記失敗，下次重試
                db.mark_failed(conn, v["video_id"])
                fail += 1
                continue
            if relevant:
                db.update_classification(
                    conn, v["video_id"], True, category,
                    str(r.get("summary") or "")[:300],
                    [str(t) for t in (r.get("tags") or [])][:4],
                    search_terms=[str(s) for s in (r.get("search_terms") or [])][:10],
                    difficulty=r.get("difficulty"),
                )
                ok += 1
            else:
                db.update_classification(conn, v["video_id"], False, None, "", [])
                skip += 1
    return ok, skip, fail
