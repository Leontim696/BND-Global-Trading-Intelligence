"""Offline tests for the overnight review script; never contact OpenRouter."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "overnight_ai_review.py"
spec = importlib.util.spec_from_file_location("overnight_ai_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_paid_ai_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BND_ALLOW_PAID_AI", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("BND_DEV_MODEL", "vendor/model")
    monkeypatch.setattr(review, "urlopen", lambda *a, **k: 1 / 0)

    assert review.main() == 0
    assert "paid AI disabled" in (
        tmp_path / "overnight-reports" / "ai-review-status.txt"
    ).read_text()


def test_failed_call_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    monkeypatch.setenv("BND_ALLOW_PAID_AI", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("BND_DEV_MODEL", "vendor/model")

    def fail(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(review, "urlopen", fail)

    assert review.main() == 1


def test_sources_cover_all_files_within_budget(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    for i in range(15):
        (tmp_path / "src" / f"m{i:02}.py").write_text("y = 2\n")

    source, omitted = review.collect_sources()

    assert len(source) == 15 and omitted == []
