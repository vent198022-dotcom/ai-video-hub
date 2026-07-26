"""main 管線測試：只驗證金鑰檢查與階段串接，不打真實 API。"""
import main as main_mod


def test_main_fails_without_keys(monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert main_mod.main() == 1


def test_main_runs_all_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)

    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: gemini-2.5-flash, batch_size: 10}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )

    stages = []
    monkeypatch.setattr(main_mod.collector, "collect",
                        lambda *a, **k: stages.append("collect") or 3)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (2, 1, 0))
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 2)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or True)

    assert main_mod.main() == 0
    assert stages == ["collect", "classify", "generate", "publish"]


def test_main_collect_failure_still_continues(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: gemini-2.5-flash, batch_size: 10}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )

    def boom(*a, **k):
        raise RuntimeError("收集掛了")
    stages = []
    monkeypatch.setattr(main_mod.collector, "collect", boom)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (0, 0, 0))
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["classify", "generate", "publish"]


def test_main_runs_cleanup_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )
    stages = []
    monkeypatch.setattr(main_mod.collector, "collect",
                        lambda *a, **k: stages.append("collect") or 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (0, 0, 0))
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos",
                        lambda *a, **k: stages.append("cleanup") or 0)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["collect", "classify", "cleanup", "generate", "publish"]


def test_main_cleanup_failure_does_not_stop_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )
    stages = []
    monkeypatch.setattr(main_mod.collector, "collect", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: (0, 0, 0))

    def boom(*a, **k):
        raise RuntimeError("清理掛了")
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos", boom)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["generate", "publish"]
