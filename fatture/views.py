"""
fatture/views.py — Landing dashboard dell'area /fatture.

Header + 3 CTA (Nuova fattura, Clienti, Storico) con contatori live.
"""
from datetime import date

from flask import Response

from . import fatture_bp
from shared.theme import render_page
from shared.design import icon
from shared.supabase_client import get_client, is_configured

# I sotto-moduli devono essere importati per registrare le rotte sul blueprint
from . import clienti     # noqa: F401
from . import storico     # noqa: F401
from . import editor      # noqa: F401


def _stats():
    """Ritorna KPI per la dashboard: emittente + count clienti + count fatture anno."""
    if not is_configured():
        return None
    sb = get_client()
    out = {}
    try:
        r = (sb.table("b2f_emittente").select("nome,cognome,piva,regime_fisc")
               .eq("id", 1).single().execute())
        out["emittente"] = r.data or {}
    except Exception:
        out["emittente"] = {}
    try:
        r = (sb.table("b2f_clienti").select("*", count="exact", head=True)
               .eq("attivo", True).execute())
        out["n_clienti"] = r.count
    except Exception:
        out["n_clienti"] = None
    try:
        anno = date.today().year
        r = (sb.table("b2f_fatture").select("*", count="exact", head=True)
               .eq("anno", anno).execute())
        out["n_fatture_anno"] = r.count
        out["anno"] = anno
    except Exception:
        out["n_fatture_anno"] = None
        out["anno"] = date.today().year
    return out


@fatture_bp.get("/")
def index():
    s = _stats()

    if s is None:
        content = '''<div class="notice warn">
          Supabase non configurato. Aggiungi <code>SUPABASE_URL</code> e
          <code>SUPABASE_KEY</code> alle env vars di Render.
        </div>'''
        return _wrap(content)

    em = s["emittente"] or {}
    em_line = (f'{em.get("nome","") or ""} {em.get("cognome","") or ""}'.strip()
               or "— da impostare —")
    em_sub = " · ".join(x for x in [em.get("piva"), em.get("regime_fisc")] if x) or "P.IVA da impostare"

    n_cli = s["n_clienti"] if s["n_clienti"] is not None else "—"
    n_fat = s["n_fatture_anno"] if s["n_fatture_anno"] is not None else "—"
    anno = s["anno"]

    def voce(href, ic, label, count_id="", count=""):
        cnt = (f'<span class="chip" id="{count_id}">{count}</span>'
               if count_id or count != "" else "")
        return f'''<a class="item" href="{href}">
          <span class="ico">{icon(ic)}</span>
          <span class="body"><span class="n">{label}</span></span>
          <span class="end">{cnt}</span>
          <span class="chev">{icon("chevron")}</span>
        </a>'''

    content = f'''
    <div class="grid split">
      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Sezioni</div></div>
          <div class="list">
            {voce("/fatture/nuova", "plus", "Nuova fattura")}
            {voce("/fatture/storico", "fatture", f"Storico {anno}", count=n_fat)}
            {voce("/fatture/clienti", "clienti", "Clienti", count=n_cli)}
            {voce("/fatture/situazione", "fiscale", "Situazione fiscale", count_id="kpi-fiscale", count="—")}
            {voce("/fatture/spese-piva", "wallet", "Movimenti P.IVA")}
          </div>
        </div>
      </div>

      <div class="stack">
        <a href="/fatture/emittente" class="card card-link">
          <div class="card-head">
            <div class="eyebrow">Emittente</div>
            <span class="small accent">Modifica ›</span>
          </div>
          <div class="h3">{em_line}</div>
          <div class="small muted mt-2">{em_sub}</div>
        </a>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Da accantonare</div></div>
          <div class="stat">
            <div class="val tnum accent" id="kpi-acc">—</div>
            <div class="lbl">sull'incassato del {anno}</div>
          </div>
          <a class="btn ghost block mt-4" href="/fatture/situazione">Vedi il dettaglio</a>
        </div>
      </div>
    </div>

    <script>
    (function() {{
      fetch('/fatture/api/situazione', {{cache:'no-store'}})
        .then(r => r.ok ? r.json() : null)
        .then(d => {{
          if (!d || !d.totali) return;
          const fmt = v => '€ ' + new Intl.NumberFormat('it-IT',
            {{minimumFractionDigits:0, maximumFractionDigits:0}}).format(v);
          const netto = document.getElementById('kpi-fiscale');
          if (netto) netto.textContent = fmt(d.totali.netto_competenza);
          const acc = document.getElementById('kpi-acc');
          if (acc && d.accantonamento) acc.textContent = fmt(d.accantonamento.consigliato);
        }})
        .catch(() => {{}});
    }})();
    </script>
    '''

    return _wrap(content)


def _wrap(content: str) -> Response:
    html = render_page(
        section="fatture",
        eyebrow="Fatturazione",
        title_html='Le mie <em>fatture</em>',
        content=content,
    )
    return Response(html, mimetype="text/html")
