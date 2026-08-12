"""
spese/views.py — Area /spese: il conto personale.

I movimenti della P.IVA (fatturato incassato, commercialista, licenze)
vivono sotto /fatture/spese-piva, perche' entrano nel calcolo fiscale.
Qui c'e' il conto personale — dove finiscono i soldi una volta tolta la
quota da accantonare, tramite il giroconto della ripartizione.
"""
from datetime import date

from flask import Response

from . import spese_bp
from . import dati as D
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_breve

# I sotto-moduli registrano le loro rotte sul blueprint quando importati.
from . import movimenti   # noqa: E402,F401
from . import risparmi    # noqa: E402,F401
from . import importa     # noqa: E402,F401


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@spese_bp.get("/")
def index():
    client = D.sb()
    if client is None:
        return _wrap('''<div class="notice warn">
          Supabase non configurato. Aggiungi <code>SUPABASE_URL</code> e
          <code>SUPABASE_KEY</code> alle env vars di Render.
        </div>''')

    oggi = date.today()
    righe_anno = D.movimenti(client, anno=oggi.year)
    righe_mese = [r for r in righe_anno if int(r.get("mese") or 0) == oggi.month]
    t_mese = D.totali(righe_mese)
    t_anno = D.totali(righe_anno)

    ultimi = "".join(f'''
      <div class="row">
        <span class="k">{data_breve(r.get("data"))}</span>
        <span class="t">{_esc((r.get("descrizione") or "—")[:44])}
          <span class="sub">{_esc(r.get("categoria") or "senza categoria")}</span></span>
        <span class="v tnum {"pos" if D.TIPI_SEGNO.get(r.get("tipo"), 0) > 0 else "neg"}">
          {eur_segno(abs(float(r.get("importo") or 0)) * (D.TIPI_SEGNO.get(r.get("tipo"), 1)))}</span>
      </div>''' for r in righe_anno[:8])

    blocco_ultimi = (f'''
      <div class="card">
        <div class="card-head">
          <div class="eyebrow">Ultimi movimenti</div>
          <a class="small accent" href="/spese/movimenti">Vedi tutti ›</a>
        </div>
        <div class="rows detail">{ultimi}</div>
      </div>''' if ultimi else f'''
      <div class="empty">{icon("spese")}
        <div class="t">Nessun movimento nel {oggi.year}</div>
        <div class="s">Registra il primo dal pulsante in basso.</div>
      </div>''')

    # Quanto e' arrivato dalla P.IVA: e' la domanda che ci si fa dopo aver
    # premuto "ripartisci" su una fattura, e merita un posto suo.
    girati = t_anno["giroconti"]
    blocco_giroconti = f'''
      <div class="card">
        <div class="card-head"><div class="eyebrow">Arrivato dalla P.IVA</div></div>
        <div class="stat">
          <div class="val tnum accent">€ {eur(girati, 0)}</div>
          <div class="lbl">girati sul personale nel {oggi.year}</div>
        </div>
        <p class="small muted mt-4">
          Sono i giroconti creati quando ripartisci una fattura incassata: la
          quota da accantonare resta sul conto P.IVA, il resto arriva qui.
        </p>
        <a class="btn ghost block mt-4" href="/spese/movimenti?tipo=giroconto">
          {icon("wallet")}Vedi i giroconti
        </a>
      </div>'''

    body = f'''
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat">
        <div class="val tnum {"pos" if t_mese["saldo"] >= 0 else "neg"}">€ {eur_segno(t_mese["saldo"], 0)}</div>
        <div class="lbl">Saldo del mese</div>
        <div class="hint">{t_mese["n"]} moviment{"o" if t_mese["n"] == 1 else "i"}</div>
      </div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum pos">€ {eur(t_mese["entrate"], 0)}</div>
        <div class="lbl">Entrate</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum neg">€ {eur(t_mese["uscite"], 0)}</div>
        <div class="lbl">Uscite</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum">€ {eur(t_anno["saldo"], 0)}</div>
        <div class="lbl">Saldo {oggi.year}</div></div></div>
    </div>

    <div class="grid split">
      <div class="stack">{blocco_ultimi}</div>
      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Sezioni</div></div>
          <div class="list">
            <a class="item" href="/spese/movimenti">
              <span class="ico">{icon("wallet")}</span>
              <span class="body"><span class="n">Movimenti</span></span>
              <span class="chev">{icon("chevron")}</span>
            </a>
            <a class="item" href="/spese/risparmi">
              <span class="ico">{icon("fiscale")}</span>
              <span class="body"><span class="n">Risparmi</span></span>
              <span class="chev">{icon("chevron")}</span>
            </a>
            <a class="item" href="/fatture/spese-piva">
              <span class="ico">{icon("fatture")}</span>
              <span class="body"><span class="n">Movimenti P.IVA</span></span>
              <span class="chev">{icon("chevron")}</span>
            </a>
          </div>
        </div>
        {blocco_giroconti}
      </div>
    </div>'''

    return _wrap(body, fab=("Nuovo movimento", "/spese/movimenti/nuovo"))


def _wrap(content: str, fab=None) -> Response:
    return Response(
        render_page(section="spese", eyebrow="Conto personale",
                    title_html='Le mie <em>spese</em>', content=content, fab=fab),
        mimetype="text/html")
