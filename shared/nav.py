"""
shared/nav.py — Subnav tra le 3 aree (Ore, Fatture, Spese).

Restituisce un blocco autocontenuto <style>+<nav> che va iniettato
subito dentro `.wrap` (per il timesheet lo fa apply_patch.py; per le
altre aree lo include già `theme.render_page()`).

Il CSS qui riprodotto è un sottoinsieme di quello in shared/theme.py:
è necessario duplicarlo per il timesheet (che non importa theme.py).
Le variabili --gold/--line/--card-grad sono già definite dentro il
tema di xs_server.
"""

_STYLE = """<style>
.subnav{display:flex;gap:6px;padding:5px;background:var(--card-grad);
  border:1px solid var(--line);border-radius:999px;
  box-shadow:0 30px 70px -34px rgba(0,0,0,.75),0 4px 14px -6px rgba(0,0,0,.5);
  margin:0 0 22px}
.subnav a{flex:1;text-align:center;text-decoration:none;color:var(--ink-dim);
  font-size:13px;font-weight:500;padding:9px 6px;border-radius:999px;
  transition:.18s;letter-spacing:.01em}
.subnav a:hover{color:var(--ink)}
.subnav a.is-active{background:var(--gold);color:var(--on-gold);
  box-shadow:0 6px 18px -8px rgba(124,108,255,.6)}
html[data-theme="light"] .subnav a.is-active{
  box-shadow:0 6px 18px -8px rgba(91,73,209,.55)}
</style>"""

_LINKS = [
    ("ore",     "Ore",     "/"),
    ("fatture", "Fatture", "/fatture"),
    ("spese",   "Spese",   "/spese"),
]


def render_nav(active: str) -> str:
    """Ritorna <style>+<nav> della subnav con la voce `active` selezionata."""
    items = []
    for key, label, href in _LINKS:
        cls = ' class="is-active"' if key == active else ''
        items.append(f'<a href="{href}"{cls}>{label}</a>')
    return f'{_STYLE}\n<nav class="subnav" aria-label="Sezioni">{"".join(items)}</nav>'
