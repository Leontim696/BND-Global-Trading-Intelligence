"""Reguli „point-in-time”: se folosește doar ce era public la data analizei (idei din TradingAgents v0.7.1, reimplementate).

- ``as_of_date``: o dată cerută de un model sau de un utilizator nu poate trece de data analizei și are mereu forma AAAA-LL-ZZ;
- ``in_window``: un articol/eveniment aparține ferestrei [start, end + 1 zi); un element fără dată se acceptă doar dacă
  fereastra ajunge în prezent (altfel nu se poate demonstra că nu e din viitor);
- ``filed_as_of``: dintr-un tabel de fapte cu data depunerii, ce era cunoscut la ``as_of``, cu versiunea (restatarea) care era
  în vigoare atunci.
"""

from datetime import date, datetime, timedelta, timezone


def to_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def as_of_date(requested, as_of) -> str:
    """Data cerută, tăiată la `as_of`; formatul nepadat ('2024-7-5') e înțeles corect, o dată invalidă dă ValueError."""
    def parse(text):
        if isinstance(text, datetime):
            return text.date()
        if isinstance(text, date):
            return text
        parts = str(text).strip().split("-")
        if len(parts) != 3:
            raise ValueError(f"dată invalidă: {text!r} (format AAAA-LL-ZZ)")
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError as exc:
            raise ValueError(f"dată invalidă: {text!r}") from exc
    return min(parse(requested), parse(as_of)).isoformat()


def window(start, end, as_of) -> tuple[str, str]:
    """(start, end) tăiate la `as_of`; o fereastră care se termină înainte să înceapă e o eroare, nu o listă goală."""
    s, e = as_of_date(start, as_of), as_of_date(end, as_of)
    if e < s:
        raise ValueError(f"fereastra se termină înainte să înceapă: {end} < {start}")
    return s, e


def in_window(published: datetime | None, start: datetime, end: datetime, now: datetime | None = None) -> bool:
    end_exclusive = to_utc(end) + timedelta(days=1)
    if published is None:
        reaches_present = to_utc(end_exclusive) > to_utc(now or datetime.now(timezone.utc))
        return reaches_present
    return to_utc(start) <= to_utc(published) < end_exclusive


def filed_as_of(rows, as_of, key=("ticker", "tag", "end"), filed_field="filed") -> list[dict]:
    """Pentru fiecare cheie (de exemplu ticker+tag+perioadă), versiunea depusă cel mai recent la data `as_of` sau înainte."""
    cutoff = as_of_date(as_of, as_of)
    best: dict = {}
    for row in rows:
        filed = str(row.get(filed_field, ""))[:10]
        if not filed or filed > cutoff:
            continue
        ident = tuple(row[k] for k in key)
        if ident not in best or filed >= str(best[ident][filed_field])[:10]:
            best[ident] = row
    return list(best.values())
