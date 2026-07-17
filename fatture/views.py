"""
fatture/views.py — Landing dashboard dell'area /fatture.

Header + 3 CTA (Nuova fattura, Clienti, Storico) con contatori live.
"""
from datetime import date

from flask import Response

from . import fatture_bp
from shared.theme import render_page
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
    em_sub = " · ".join(x for x in [em.get("piva"), em.get("regime_fisc")] if x) or "PIVA da impostare"

    n_cli = s["n_clienti"] if s["n_clienti"] is not None else "—"
    n_fat = s["n_fatture_anno"] if s["n_fatture_anno"] is not None else "—"
    anno = s["anno"]

    content = f'''
    <div class="card">
      <div class="eyebrow" style="margin-bottom:6px">Emittente</div>
      <h2 class="serif" style="margin:0 0 3px">{em_line}</h2>
      <div style="color:var(--muted);font-size:13px">{em_sub}</div>
    </div>

    <div class="cta-list">
      <a href="/fatture/nuova">
        <div class="ico">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
        </div>
        <div class="lbl">Nuova fattura</div>
        <div class="arw"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      </a>

      <a href="/fatture/clienti">
        <div class="ico">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>
        </div>
        <div class="lbl">Clienti</div>
        <div class="cnt">{n_cli}</div>
        <div class="arw"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      </a>

      <a href="/fatture/storico">
        <div class="ico">
          <svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v4h5"/><path d="M9 12h6M9 15h6M9 18h4"/></svg>
        </div>
        <div class="lbl">Storico {anno}</div>
        <div class="cnt">{n_fat}</div>
        <div class="arw"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      </a>

      <a href="/fatture/situazione">
        <div class="ico">
          <svg viewBox="0 0 24 24"><path d="M9 3v2M15 3v2M9 19v2M15 19v2M3 9h2M3 15h2M19 9h2M19 15h2"/>
          <rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 10h6M9 13h4M9 16h2"/></svg>
        </div>
        <div class="lbl">Situazione fiscale</div>
        <div class="cnt" id="kpi-fiscale">—</div>
        <div class="arw"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      </a>
    </div>

    <script>
    (function() {{
      fetch('/fatture/api/situazione', {{cache:'no-store'}})
        .then(r => r.ok ? r.json() : null)
        .then(d => {{
          const el = document.getElementById('kpi-fiscale');
          if (!el || !d || !d.totali) return;
          const fmt = v => new Intl.NumberFormat('it-IT',
            {{minimumFractionDigits:0, maximumFractionDigits:0}}).format(v);
          el.textContent = '€ ' + fmt(d.totali.netto_stimato);
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
