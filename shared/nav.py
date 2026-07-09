"""
shared/nav.py — Navbar comune montata sopra tutte le pagine della hub.

Ritorna un frammento HTML+CSS+JS *autocontenuto* da iniettare all'inizio
di `<body>`. Funziona sia su superfici scure (timesheet) sia chiare
(fatturatore, spese): usa `backdrop-filter: blur()`, sfondo semi-
trasparente e `currentColor` per l'inchiostro.

Uso:
    from shared.nav import render_nav
    body = "<body>" + render_nav("ore") + resto_body
"""

_LINKS = [
    ("ore",     "Ore",     "/"),
    ("fatture", "Fatture", "/fatture"),
    ("spese",   "Spese",   "/spese"),
]


def render_nav(active: str) -> str:
    """Ritorna il markup della navbar con il link `active` evidenziato."""
    items = []
    for key, label, href in _LINKS:
        cls = "hubnav__link" + (" is-active" if key == active else "")
        items.append(f'<a class="{cls}" href="{href}">{label}</a>')

    return f"""
<style>
  .hubnav {{
    position: sticky; top: 0; z-index: 900;
    display: flex; align-items: center; gap: 4px;
    padding: 8px 14px;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 13px; font-weight: 500; letter-spacing: .01em;
    background: rgba(20, 22, 28, .55);
    backdrop-filter: blur(14px) saturate(1.3);
    -webkit-backdrop-filter: blur(14px) saturate(1.3);
    border-bottom: 1px solid rgba(255,255,255,.06);
  }}
  @media (prefers-color-scheme: light) {{
    .hubnav {{ background: rgba(255,255,255,.72); border-bottom-color: rgba(0,0,0,.06); }}
  }}
  html[data-theme="light"] .hubnav {{
    background: rgba(255,255,255,.72); border-bottom-color: rgba(0,0,0,.06);
  }}
  .hubnav__brand {{
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px; font-weight: 600; letter-spacing: .16em;
    padding: 4px 8px; border-radius: 4px;
    background: #16624F; color: #fff;
    margin-right: 12px;
  }}
  .hubnav__link {{
    color: inherit; opacity: .58; text-decoration: none;
    padding: 6px 12px; border-radius: 999px;
    transition: opacity .15s, background .15s;
  }}
  .hubnav__link:hover {{ opacity: .95; }}
  .hubnav__link.is-active {{
    opacity: 1;
    background: rgba(127,127,127,.14);
    font-weight: 600;
  }}
  .hubnav__spacer {{ flex: 1; }}
</style>
<nav class="hubnav" role="navigation" aria-label="Sezioni">
  <span class="hubnav__brand">B2F</span>
  {' '.join(items)}
  <span class="hubnav__spacer"></span>
</nav>
"""
