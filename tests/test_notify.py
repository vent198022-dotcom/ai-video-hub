"""告警模組測試（絕不寄出真實郵件）。"""
from datetime import datetime, timedelta, timezone

from conftest import make_video

import db
import notify

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
ENV = {"ALERT_SMTP_USER": "me@gmail.com", "ALERT_SMTP_PASS": "pw",
       "ALERT_TO": "me@gmail.com"}


def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_hours_since_success_never_run(tmp_path):
    assert notify.hours_since_success(_conn(tmp_path), now=NOW) is None


def test_hours_since_success_computes(tmp_path):
    conn = _conn(tmp_path)
    db.set_meta(conn, "last_success_at", "2026-08-10T12:00:00Z")
    assert notify.hours_since_success(conn, now=NOW) == 24.0


def test_hours_since_success_bad_timestamp(tmp_path):
    """時間戳壞掉時視為未知，不得擲出例外。"""
    conn = _conn(tmp_path)
    db.set_meta(conn, "last_success_at", "不是時間")
    assert notify.hours_since_success(conn, now=NOW) is None


def test_build_message_contains_key_facts():
    subject, body = notify.build_message(52.5, "2026-08-09T07:30:00Z", "最後幾行 log")
    assert "未更新" in subject
    assert "52" in body
    assert "2026-08-09" in body
    assert "最後幾行 log" in body


def test_send_email_success(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            sent["login"] = (u, p)

        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    assert notify.send_email("smtp.gmail.com", 465, "u", "p", "to@x.com",
                             "主旨", "內容") is True
    assert sent["login"] == ("u", "p")
    assert sent["to"] == "to@x.com"


def test_send_email_failure_returns_false(monkeypatch):
    def boom(*a, **k):
        raise OSError("連線失敗")
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", boom)
    assert notify.send_email("h", 465, "u", "p", "t", "s", "b") is False


def test_send_email_never_leaks_password(monkeypatch, caplog):
    def boom(*a, **k):
        raise OSError("認證失敗 密碼=super-secret-pw")
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", boom)
    notify.send_email("h", 465, "u", "super-secret-pw", "t", "s", "b")
    assert "super-secret-pw" not in caplog.text


def test_check_ok_when_recent(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    db.set_meta(conn, "last_success_at", "2026-08-11T06:00:00Z")

    def boom(*a, **k):
        raise AssertionError("不該寄信")
    monkeypatch.setattr(notify, "send_email", boom)
    assert notify.check(conn, ENV, 48, None, now=NOW) == "ok"


def test_check_alerts_when_stale(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    db.set_meta(conn, "last_success_at", "2026-08-08T06:00:00Z")   # 78 小時前
    calls = []
    monkeypatch.setattr(notify, "send_email",
                        lambda *a, **k: calls.append(a) or True)
    assert notify.check(conn, ENV, 48, None, now=NOW) == "alerted"
    assert len(calls) == 1


def test_check_alerts_when_never_succeeded(tmp_path, monkeypatch):
    """從未成功過也要告警——例如剛裝好就一直失敗。"""
    conn = _conn(tmp_path)
    calls = []
    monkeypatch.setattr(notify, "send_email",
                        lambda *a, **k: calls.append(a) or True)
    assert notify.check(conn, ENV, 48, None, now=NOW) == "alerted"
    assert len(calls) == 1


def test_check_no_config_skips(tmp_path, monkeypatch):
    conn = _conn(tmp_path)

    def boom(*a, **k):
        raise AssertionError("沒設定就不該寄")
    monkeypatch.setattr(notify, "send_email", boom)
    assert notify.check(conn, {}, 48, None, now=NOW) == "no_config"


def test_check_send_failure_reported(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: False)
    assert notify.check(conn, ENV, 48, None, now=NOW) == "alert_failed"
