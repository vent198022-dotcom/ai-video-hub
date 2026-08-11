"""更新失敗告警：檢查上次成功完成的時間，過久沒成功就寄 Email。

刻意設計成獨立於主管線執行——管線被中止時，寫在管線裡的通知也不會被執行。
本模組只做幾秒的檢查與寄信，被中斷的機率極低。
"""
import logging
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import yaml

import db

ROOT = Path(__file__).parent
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
LOG_TAIL_LINES = 15

log = logging.getLogger("notify")


def _mask(text, secret):
    """把訊息中的密碼換掉，避免寄信失敗時把密碼寫進 log。"""
    s = str(text)
    return s.replace(secret, "***") if secret else s


def hours_since_success(conn, now=None):
    """距離上次成功完成幾小時；從未成功或時間戳異常回傳 None。"""
    raw = db.get_meta(conn, "last_success_at")
    if not raw:
        return None
    try:
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        log.warning("last_success_at 格式異常：%s", raw)
        return None
    now = now or datetime.now(timezone.utc)
    return (now - last).total_seconds() / 3600


def build_message(hours, last_success, log_tail):
    """組出告警信的主旨與內文。"""
    if hours is None:
        when = "從未成功完成過"
        elapsed = "未知"
    else:
        when = last_success or "未知"
        elapsed = f"{hours:.0f} 小時"
    subject = f"[AI 知識平台] 網站已 {elapsed} 未更新"
    body = (
        "AI 教學影片知識平台偵測到更新異常。\n\n"
        f"上次成功完成：{when}\n"
        f"距今：{elapsed}\n\n"
        "可能原因：電腦當時關機、排程被中止、或 API 配額用罄。\n\n"
        "建議處理：\n"
        "1. 手動執行專案資料夾裡的 run.bat，看是否能正常跑完\n"
        "2. 查看 logs\\run.log 最後的錯誤訊息\n"
        "3. 用 Get-ScheduledTaskInfo -TaskName \"AIVideoHub\" 確認排程狀態\n\n"
        f"--- logs\\run.log 最後 {LOG_TAIL_LINES} 行 ---\n{log_tail}\n"
    )
    return subject, body


def send_email(host, port, user, password, to, subject, body):
    """寄出告警信；成功回 True，失敗記錄並回 False（絕不擲出例外）。"""
    try:
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        log.warning("告警信寄送失敗：%s", _mask(e, password))
        return False


def _read_log_tail(log_path):
    if not log_path:
        return "(無)"
    try:
        lines = Path(log_path).read_text(encoding="utf-8",
                                         errors="replace").splitlines()
        return "\n".join(lines[-LOG_TAIL_LINES:]) or "(空)"
    except OSError:
        return "(讀不到 log)"


def check(conn, env, threshold_hours, log_path, now=None):
    """檢查並在必要時告警。回傳 ok / alerted / alert_failed / no_config。"""
    user = env.get("ALERT_SMTP_USER")
    password = env.get("ALERT_SMTP_PASS")
    to = env.get("ALERT_TO") or user
    if not user or not password:
        log.info("未設定 ALERT_SMTP_USER／ALERT_SMTP_PASS，略過告警")
        return "no_config"

    hours = hours_since_success(conn, now=now)
    if hours is not None and hours < threshold_hours:
        log.info("上次成功在 %.1f 小時前，未逾門檻 %d 小時", hours, threshold_hours)
        return "ok"

    subject, body = build_message(hours, db.get_meta(conn, "last_success_at"),
                                  _read_log_tail(log_path))
    ok = send_email(SMTP_HOST, SMTP_PORT, user, password, to, subject, body)
    if ok:
        log.info("已寄出告警信給 %s", to)
        return "alerted"
    return "alert_failed"


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    threshold = (cfg.get("watchdog") or {}).get("threshold_hours", 48)
    conn = db.connect(ROOT / "videos.db")
    result = check(conn, os.environ, threshold, ROOT / "logs" / "run.log")
    log.info("看門狗結果：%s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
