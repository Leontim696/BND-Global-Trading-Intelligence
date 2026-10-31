"""Raport Markdown -> HTML simplu, pentru încărcare în Google Drive ca document.

Suportă ce folosesc rapoartele: titluri (#, ##), liste cu «- », tabele cu «|»,
**aldin** și _cursiv_. Textul este escapat.

    python -m src.bnd.report_html rapoarte/2026-10-31_0821.md > raport.html
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


def to_html(markdown: str) -> str:
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
    return "<html><body>" + "".join(out) + "</body></html>"


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not Path(args[0]).is_file():
        print("Folosire: python -m src.bnd.report_html raport.md", file=sys.stderr)
        return 2
    sys.stdout.write(to_html(Path(args[0]).read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
