"""
fatture/views.py — Rotte area /fatture.

Step 1 (attuale): landing minima con navbar, per verificare che il
blueprint si monta e il PIN gate funziona anche qui.

Step 3-6: CRUD clienti, CRUD fatture, PDF, integrazione → spese.
"""
from flask import Response

from . import fatture_bp
from shared.nav import render_nav


@fatture_bp.get("/")
def index():
    nav = render_nav("fatture")
    body = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fatture — B2F</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{ --paper:#FAFAF7; --ink:#14171C; --muted:#6A7078; --accent:#16624F; }}
    body {{ margin:0; background:var(--paper); color:var(--ink);
            font-family:'Inter',system-ui,sans-serif; }}
    .wrap {{ max-width:820px; margin:0 auto; padding:48px 22px 80px; }}
    h1 {{ font-size:28px; letter-spacing:-.01em; margin:0 0 8px; }}
    p  {{ color:var(--muted); font-size:15px; line-height:1.5; }}
    code {{ font-family:'IBM Plex Mono',ui-monospace,monospace;
            background:#EFEEE9; padding:2px 6px; border-radius:4px;
            font-size:13px; }}
  </style>
</head>
<body>
  {nav}
  <main class="wrap">
    <h1>Fatture</h1>
    <p>Area in costruzione. Qui arriveranno l'anagrafica clienti e lo
    storico fatture, con persistenza su <code>b2f_clienti</code> e
    <code>b2f_fatture</code> su Supabase.</p>
  </main>
</body>
</html>"""
    return Response(body, mimetype="text/html")
