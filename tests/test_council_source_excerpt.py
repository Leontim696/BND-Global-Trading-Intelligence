"""The code-review input must disclose incomplete source excerpts."""
from scripts.overnight_five_agent_council import source_excerpt


def test_short_source_is_not_truncated(tmp_path):
    path = tmp_path / "short.py"
    path.write_text("x = 1", encoding="utf-8")
    result = source_excerpt(path, limit=10)
    assert result["excerpt"] == "x = 1"
    assert result["truncated"] is False
    assert result["total_chars"] == 5


def test_long_source_discloses_truncation(tmp_path):
    path = tmp_path / "long.py"
    path.write_text("x" * 30, encoding="utf-8")
    result = source_excerpt(path, limit=10)
    assert result["excerpt"] == "x" * 10
    assert result["truncated"] is True
    assert result["total_chars"] == 30
