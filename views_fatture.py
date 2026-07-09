"""
fatture/views.py — Rotte area /fatture.

Step 1: landing placeholder.
Step 2 (attuale): landing arricchita che mostra stato Supabase e
                  conteggi clienti/fatture.
Step 3-6: CRUD clienti, CRUD fatture, PDF, integrazione -> spese.
"""
from flask import Response

from . import fatture_bp
from shared.nav import render_nav
from shared.supabase_client import get_client, is_configured


def _stato_supabase():
    """Ritorna dict con info diagnostiche o None se non configurato."""
    if not is_configured():
        return None
    sb = get_client()
    out = {}
    for table in ("b2f_emittente", "b2f_clienti", "b2f_fatture"):
        try:
            r = sb.table(table).select("*", count="exact", head=True).execute()
            out[table] = {"ok": True, "count": r.count}
        except Exception as e:
            out[table] = {"ok": False, "err": str(e)[:120]}
    try:
        em = sb.table("b2f_emittente").select("nome,cognome,piva,cf,regime_fisc").eq("id", 1).single().execute()
        out["emittente"] = em.data
    except Exception:
        out["emittente"] = None
    return out


@fatture_bp.get("/")
def index():
    nav = render_nav("fatture")
    st = _stato_supabase()

    if st is None:
        stato_html = (
            '<p class="warn">Supabase non configurato. '
            "Aggiungi <code>SUPABASE_URL</code> e <code>SUPABASE_KEY</code> "
            "alle env vars di Render.</p>"
        )
    else:
        em = st.get("emittente") or {}
        em_line = (
            f'{em.get("nome","")} {em.get("cognome","")} — {em.get("regime_fisc","")}'
            if em else "non impostato"
        )
        rows = []
        for tbl in ("b2f_emittente", "b2f_clienti", "b2f_fatture"):
            r = st[tbl]
            if r["ok"]:
                rows.append(f"<tr><td><code>{tbl}</code></td><td>{r['count']} righe</td></tr>")
            else:
                rows.append(f"<tr><td><code>{tbl}</code></td><td class='err'>{r['err']}</td></tr>")
        stato_html = f"""
        <p>Emittente: <strong>{em_line}</strong></p>
        <table class="diag"><tbody>{''.join(rows)}</tbody></table>
        """

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
    :root {{ --paper:#FAFAF7; --ink:#14171C; --muted:#6A7078; --accent:#16624F; --amber:#9A6712; }}
    body {{ margin:0; background:var(--paper); color:var(--ink);
            font-family:'Inter',system-ui,sans-serif; }}
    .wrap {{ max-width:820px; margin:0 auto; padding:36px 22px 80px; }}
    h1 {{ font-size:28px; letter-spacing:-.01em; margin:0 0 4px; }}
    .eyebrow {{ font-family:'IBM Plex Mono',monospace; font-size:11px;
                letter-spacing:.22em; text-transform:uppercase; color:var(--accent); }}
    p {{ color:var(--ink); font-size:15px; line-height:1.5; }}
    p.warn {{ background:#FFF6E5; border-left:3px solid var(--amber);
              padding:12px 14px; border-radius:4px; color:#5A3E00; }}
    code {{ font-family:'IBM Plex Mono',monospace;
            background:#EFEEE9; padding:2px 6px; border-radius:4px;
            font-size:13px; }}
    table.diag {{ border-collapse:collapse; margin-top:16px; font-size:14px; }}
    table.diag td {{ padding:6px 14px 6px 0; }}
    table.diag td:first-child {{ padding-right:24px; }}
    .err {{ color:#B23A3A; font-family:'IBM Plex Mono',monospace; font-size:12px; }}
    .cta {{ display:inline-block; margin-top:24px; padding:9px 16px;
            background:var(--accent); color:#fff; text-decoration:none;
            border-radius:6px; font-weight:600; font-size:14px; opacity:.5;
            pointer-events:none; }}
    .cta small {{ display:block; font-weight:400; font-size:11px;
                  opacity:.85; letter-spacing:.04em; margin-top:2px; }}
  </style>
</head>
<body>
  {nav}
  <main class="wrap">
    <div class="eyebrow">Fatturazione forfettario</div>
    <h1>Fatture</h1>
    {stato_html}
    <a class="cta" href="#">Nuova fattura<small>disponibile allo step 4</small></a>
  </main>
</body>
</html>"""
    return Response(body, mimetype="text/html")
