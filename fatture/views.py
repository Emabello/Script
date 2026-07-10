"""
fatture/views.py — Area /fatture, in stile launchpad B2F.

Header: logo B2F cliccabile (back to /) + toggle tema.
Contenuto: card emittente, KPI clienti/fatture, CTA (disabilitate
fino allo step 4).
"""
from flask import Response

from . import fatture_bp
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured


def _stato():
    if not is_configured():
        return None
    sb = get_client()
    out = {}
    for tbl in ("b2f_emittente", "b2f_clienti", "b2f_fatture"):
        try:
            r = sb.table(tbl).select("*", count="exact", head=True).execute()
            out[tbl] = {"ok": True, "count": r.count}
        except Exception as e:
            out[tbl] = {"ok": False, "err": str(e)[:120]}
    try:
        r = (sb.table("b2f_emittente")
               .select("nome,cognome,piva,regime_fisc")
               .eq("id", 1).single().execute())
        out["emittente"] = r.data
    except Exception:
        out["emittente"] = None
    return out


@fatture_bp.get("/")
def index():
    st = _stato()

    if st is None:
        content = """
        <div class="notice warn">
          Supabase non configurato. Aggiungi <code>SUPABASE_URL</code> e
          <code>SUPABASE_KEY</code> alle env vars di Render, poi ricarica.
        </div>
        """
    else:
        em = st.get("emittente") or {}
        em_line = (f'{em.get("nome","") or ""} {em.get("cognome","") or ""}'.strip()
                   or "— da impostare —")
        piva = em.get("piva") or "PIVA da impostare"
        regime = em.get("regime_fisc") or "RF19"

        n_cli = st["b2f_clienti"]["count"] if st["b2f_clienti"]["ok"] else "—"
        n_fat = st["b2f_fatture"]["count"] if st["b2f_fatture"]["ok"] else "—"

        content = f"""
        <div class="card">
          <div class="eyebrow" style="margin-bottom:6px">Emittente</div>
          <h2 class="serif" style="margin:0 0 4px">{em_line}</h2>
          <div style="color:var(--muted);font-size:13px">
            {piva} · regime {regime}
          </div>
        </div>

        <div class="grid2">
          <div class="card">
            <div class="stat"><div class="num tnum">{n_cli}</div><div class="lbl">Clienti</div></div>
          </div>
          <div class="card">
            <div class="stat"><div class="num tnum">{n_fat}</div><div class="lbl">Fatture</div></div>
          </div>
        </div>

        <div style="display:flex;gap:10px;margin-top:18px;flex-wrap:wrap">
          <a class="btn is-disabled" href="#" aria-disabled="true">Nuova fattura</a>
          <a class="btn ghost is-disabled" href="#" aria-disabled="true">Clienti</a>
        </div>
        <div style="color:var(--faint);font-size:11px;margin-top:10px;
                    letter-spacing:.05em;text-transform:uppercase">
          Disponibili dallo step 4
        </div>
        """

    return Response(
        render_page(section="fatture",
                    eyebrow="Fatturazione",
                    title_html='Le mie <em>fatture</em>',
                    content=content),
        mimetype="text/html")
