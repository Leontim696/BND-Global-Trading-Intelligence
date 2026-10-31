"""Raport Markdown -> HTML simplu, pentru încărcare în Google Drive ca document.

Suportă ce folosesc rapoartele: titluri (#, ##), liste cu «- », tabele cu «|»,
**aldin** și _cursiv_. Textul este escapat.

    python -m src.bnd.report_html rapoarte/2026-10-31_0821.md > raport.html
    python -m src.bnd.report_html a.md b.md c.md > lot.html     # mai multe, separate prin linie
"""

import html
import re
import sys
from pathlib import Path


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def body(markdown: str) -> str:
    out, bullets, table = [], False, []

    def close():
        nonlocal bullets, table
        if bullets:
            out.append("</ul>")
            bullets = False
        if table:
            head, *rows = [r for r in table if not re.fullmatch(r"[\s|:\-]+", r)]
            out.append("<table border='1' cellpadding='4'><tr>"
                       + "".join(f"<th>{_inline(c)}</th>" for c in _cells(head)) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in _cells(r))
                                 + "</tr>" for r in rows) + "</table>")
            table = []

    for line in markdown.splitlines():
        if line.startswith("|"):
            if bullets:
                close()
            table.append(line)
            continue
        if table:
            close()
        if line.startswith("- "):
            if not bullets:
                out.append("<ul>")
                bullets = True
            out.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if bullets:
            close()
        if line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
    close()
    return "".join(out)


def to_html(markdown: str) -> str:
    return "<html><body>" + body(markdown) + "</body></html>"


def to_html_many(markdowns: list[str]) -> str:
    """Mai multe rapoarte într-un singur document, în ordinea dată, separate prin linie."""
    return "<html><body>" + "<hr>".join(body(m) for m in markdowns) + "</body></html>"


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or not all(Path(a).is_file() for a in args):
        print("Folosire: python -m src.bnd.report_html raport.md [alt_raport.md ...]",
              file=sys.stderr)
        return 2
    sys.stdout.write(to_html_many([Path(a).read_text(encoding="utf-8") for a in args]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
