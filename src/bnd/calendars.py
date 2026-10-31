"""Programul burselor: ce piețe sunt deschise acum.

Ore locale, cu ora de vară/iarnă din fusurile orare standard. Sărbătorile sunt
doar cele ale bursei americane pentru 2026-2027 (de verificat anual); celelalte
burse au doar programul de zi, deci în zilele lor libere afișează „deschis” din
greșeală. Crypto e deschis mereu; forex de duminică 22:00 la vineri 22:00 UTC,
aproximativ (în realitate 17:00 New York).
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

NYSE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}

# nume: (fus orar, deschidere, închidere, sărbători)
SESSIONS = {
    "us": ("America/New_York", time(9, 30), time(16, 0), NYSE_HOLIDAYS),
    "xetra": ("Europe/Berlin", time(9, 0), time(17, 30), set()),
    "lse": ("Europe/London", time(8, 0), time(16, 30), set()),
    "tse": ("Asia/Tokyo", time(9, 0), time(15, 0), set()),
}
LABELS = {"us": "bursa americană", "xetra": "bursa din Frankfurt", "lse": "bursa din Londra",
          "tse": "bursa din Tokyo", "forex": "forex", "crypto": "crypto"}
SPECIAL = {"DAX": "xetra", "GERMANY_INDEX": "xetra", "FTSE100": "lse", "NIKKEI": "tse"}


def session_of(name: str, asset_class: str) -> str:
    """Sesiunea unei piețe: crypto, forex, o bursă; ETF-urile se tranzacționează în SUA."""
    if asset_class == "crypto":
        return "crypto"
    if asset_class == "forex":
        return "forex"
    return SPECIAL.get(name, "us")


def is_open(session: str, when: datetime) -> bool:
    if when.tzinfo is None:
        raise ValueError("Timp cu fus orar necesar")
    when = when.astimezone(timezone.utc)
    if session == "crypto":
        return True
    if session == "forex":
        weekday, minutes = when.weekday(), when.hour * 60 + when.minute
        if weekday == 5:                         # sâmbătă
            return False
        if weekday == 4:                         # vineri: până la 22:00
            return minutes < 22 * 60
        if weekday == 6:                         # duminică: de la 22:00
            return minutes >= 22 * 60
        return True
    zone, opens, closes, holidays = SESSIONS[session]
    local = when.astimezone(ZoneInfo(zone))
    if local.weekday() >= 5 or local.date() in holidays:
        return False
    return opens <= local.time() < closes


def open_sessions(when: datetime) -> list[str]:
    names = ["us", "xetra", "lse", "tse", "forex", "crypto"]
    return [LABELS[n] for n in names if is_open(n, when)]
