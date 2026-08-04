"""
shared/fmt.py — Formattatori italiani condivisi.

Erano duplicati in fatture/storico.py, fatture/fiscale.py e spese/views.py
con tre implementazioni leggermente diverse. Una sola, qui.
"""


def eur(v, decimali: int = 2) -> str:
    """1234.5 -> '1.234,50'. Non include il simbolo: lo mette il markup."""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        v = 0.0
    s = f"{v:,.{decimali}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def eur_segno(v, decimali: int = 2) -> str:
    """Come eur() ma con segno esplicito: '+1.234,50' / '−1.234,50'."""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        v = 0.0
    segno = "+" if v >= 0 else "−"
    return segno + eur(abs(v), decimali)


def pct(v, decimali: int = 1) -> str:
    """0.2607 -> '26,1%'."""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        v = 0.0
    s = f"{v * 100:.{decimali}f}".replace(".", ",")
    return f"{s}%"


def data_it(iso: str | None) -> str:
    """'2026-03-07' -> '07/03/2026'."""
    if not iso:
        return ""
    try:
        y, m, d = iso[:10].split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return iso[:10]


def data_breve(iso: str | None) -> str:
    """'2026-03-07' -> '7 mar'."""
    if not iso:
        return ""
    mesi = ("gen", "feb", "mar", "apr", "mag", "giu",
            "lug", "ago", "set", "ott", "nov", "dic")
    try:
        y, m, d = iso[:10].split("-")
        return f"{int(d)} {mesi[int(m) - 1]}"
    except (ValueError, IndexError):
        return iso[:10]
