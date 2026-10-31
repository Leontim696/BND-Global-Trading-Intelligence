"""Convertorul de raport Markdown -> HTML."""

from src.bnd.report_html import main, to_html

SAMPLE = """# Raport, 08:21

**Ziua 1 din 16** de test.

## Pe scurt
- Valoarea: **10 000 EUR** (+0,00%)
- Poziții: 2 <script>

| Piață | Valoare |
|---|---:|
| SP500 | 1 200 EUR |

_Bani virtuali._
"""


def test_headings_lists_tables_and_emphasis():
    out = to_html(SAMPLE)

    assert "<h1>Raport, 08:21</h1>" in out and "<h2>Pe scurt</h2>" in out
    assert "<p><b>Ziua 1 din 16</b> de test.</p>" in out
    assert out.count("<li>") == 2 and "<ul>" in out and "</ul>" in out
    assert "<th>Piață</th><th>Valoare</th>" in out and "<td>1 200 EUR</td>" in out
    assert "---" not in out                       # linia de separare nu apare
    assert "<p><i>Bani virtuali.</i></p>" in out


def test_text_is_escaped():
    out = to_html(SAMPLE)

    assert "<script>" not in out and "&lt;script&gt;" in out


def test_snake_case_names_are_not_italicised():
    out = to_html("- buy BROAD_COMMODITIES, 23 bucăți, apoi SP_500_X")

    assert "<i>" not in out and "BROAD_COMMODITIES" in out


def test_cli(tmp_path, capsys):
    path = tmp_path / "r.md"
    path.write_text(SAMPLE, encoding="utf-8")

    assert main([str(path)]) == 0 and "<h1>" in capsys.readouterr().out
    assert main([]) == 2
