"""
spese/views.py — Rotte area /spese.

Step 1: landing minima con navbar.
Step 7: lista + filtri + inserimento rapido (scope "media") sulla
        tabella `spese` di Supabase.
"""
from flask import Response

from . import spese_bp
from shared.nav import render_nav
from shared.supabase_client import is_configured


@spese_bp.get("/")
def index():
    nav = render_nav("spese")
    stato_sb = "connesso" if is_configured() else "non configurato"
    body = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spese — B2F</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{ --paper:#FAFAF7; --ink:#14171C; --muted:#6A7078; }}
    body {{ margin:0; background:var(--paper); color:var(--ink);
            font-family:'Inter',system-ui,sans-serif; }}
    .wrap {{ max-width:820px; margin:0 auto; padding:48px 22px 80px; }}
    h1 {{ font-size:28px; letter-spacing:-.01em; margin:0 0 8px; }}
    p  {{ color:var(--muted); font-size:15px; line-height:1.5; }}
    .pill {{ display:inline-block; font-size:12px; padding:3px 9px;
             border-radius:999px; background:#EAF3F0; color:#0E4638; }}
  </style>
</head>
<body>
  {nav}
  <main class="wrap">
    <h1>Spese</h1>
    <p>Supabase: <span class="pill">{stato_sb}</span></p>
    <p>Area in costruzione. Qui arriveranno lista, filtri, e inserimento
    rapido sulla tabella <code>spese</code>.</p>
  </main>
</body>
</html>"""
    return Response(body, mimetype="text/html")
