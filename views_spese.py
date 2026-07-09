"""
spese/views.py — Rotte area /spese.

Step 1: landing placeholder.
Step 2 (attuale): mostra conteggio + saldo mese da tabella `spese`.
Step 7: lista + filtri + inserimento rapido.
"""
from datetime import date

from flask import Response

from . import spese_bp
from shared.nav import render_nav
from shared.supabase_client import get_client, is_configured


def _diag_spese():
    if not is_configured():
        return None
    sb = get_client()
    out = {}
    try:
        r = sb.table("spese").select("*", count="exact", head=True).execute()
        out["count"] = r.count
    except Exception as e:
        out["err"] = str(e)[:200]
        return out

    # ultime 5 righe per anteprima
    try:
        r2 = sb.table("spese").select("data,importo,descrizione,tipo") \
                .order("data", desc=True).limit(5).execute()
        out["ultime"] = r2.data or []
    except Exception as e:
        out["err_ultime"] = str(e)[:120]
        out["ultime"] = []

    return out


@spese_bp.get("/")
def index():
    nav = render_nav("spese")
    d = _diag_spese()

    if d is None:
        stato_html = (
            '<p class="warn">Supabase non configurato. '
            "Aggiungi <code>SUPABASE_URL</code> e <code>SUPABASE_KEY</code> "
            "alle env vars di Render.</p>"
        )
    elif "err" in d:
        stato_html = f"<p class='err'>Errore tabella <code>spese</code>: {d['err']}</p>"
    else:
        rows = []
        for r in d.get("ultime", []):
            data = r.get("data", "")
            imp  = r.get("importo", 0) or 0
            desc = (r.get("descrizione") or "").strip() or "—"
            tipo = r.get("tipo", "")
            sign = "-" if tipo == "uscita" else "+" if tipo == "entrata" else ""
            rows.append(
                f"<tr><td class='mono'>{data}</td>"
                f"<td>{desc}</td>"
                f"<td class='mono num'>{sign}{imp:.2f}</td></tr>"
            )
        ultime_html = (
            f"<table class='ult'><thead><tr><th>Data</th><th>Descrizione</th>"
            f"<th class='num'>€</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
            if rows else "<p class='muted'>Nessuna riga ancora inserita.</p>"
        )
        stato_html = f"""
        <p>Righe totali in <code>spese</code>: <strong>{d['count']}</strong></p>
        <h2>Ultime 5</h2>
        {ultime_html}
        """

    body = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spese — B2F</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{ --paper:#FAFAF7; --ink:#14171C; --muted:#6A7078; --accent:#16624F; --amber:#9A6712; }}
    body {{ margin:0; background:var(--paper); color:var(--ink);
            font-family:'Inter',system-ui,sans-serif; }}
    .wrap {{ max-width:820px; margin:0 auto; padding:36px 22px 80px; }}
    h1 {{ font-size:28px; letter-spacing:-.01em; margin:0 0 4px; }}
    h2 {{ font-size:14px; letter-spacing:.08em; text-transform:uppercase;
          color:var(--muted); margin:26px 0 8px; }}
    .eyebrow {{ font-family:'IBM Plex Mono',monospace; font-size:11px;
                letter-spacing:.22em; text-transform:uppercase; color:var(--accent); }}
    p {{ font-size:15px; line-height:1.5; }}
    p.warn {{ background:#FFF6E5; border-left:3px solid var(--amber);
              padding:12px 14px; border-radius:4px; color:#5A3E00; }}
    .muted {{ color:var(--muted); font-size:14px; }}
    .err {{ color:#B23A3A; }}
    code {{ font-family:'IBM Plex Mono',monospace; background:#EFEEE9;
            padding:2px 6px; border-radius:4px; font-size:13px; }}
    .mono {{ font-family:'IBM Plex Mono',monospace; font-size:13px; }}
    table.ult {{ width:100%; border-collapse:collapse; }}
    table.ult th, table.ult td {{ padding:8px 10px; border-bottom:1px solid #E7E6DF;
                                    text-align:left; font-size:14px; }}
    table.ult th {{ font-weight:500; font-size:11px; letter-spacing:.06em;
                    text-transform:uppercase; color:var(--muted); }}
    .num {{ text-align:right; }}
  </style>
</head>
<body>
  {nav}
  <main class="wrap">
    <div class="eyebrow">Gestione spese</div>
    <h1>Spese</h1>
    {stato_html}
  </main>
</body>
</html>"""
    return Response(body, mimetype="text/html")
