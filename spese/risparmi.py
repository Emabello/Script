"""
spese/risparmi.py — I periodi di stipendio e quanto metti da parte.

COME RAGIONA QUESTA PAGINA
--------------------------
Il conto personale non ragiona per mesi solari ma per periodi che vanno
da un bonifico dello stipendio al successivo: e' v_periodi_stipendio a
delimitarli, prendendo le entrate di categoria "Stipendio".

Per ogni periodo v_risparmi_mese calcola quanto e' entrato, quanto e'
uscito, cosa resta e quale sarebbe il risparmio consigliato — la
percentuale scelta in `impostazioni` applicata a quel che resta. Tu
registri quanto hai messo via davvero, e la differenza fra consigliato
ed effettivo e' l'unica cosa che conta davvero guardare.

I giroconti dalla P.IVA entrano qui come "altre entrate": sono soldi
arrivati sul conto, e alzano la base su cui si calcola il risparmio.

Rotte HTML:
  GET /spese/risparmi

Rotte JSON:
  GET   /spese/api/risparmi
  PATCH /spese/api/risparmi        {data_bonifico, effettivo_risparmio}
"""
from flask import Response, request, jsonify

from . import spese_bp
from . import dati as D
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_it, pct


@spese_bp.get("/risparmi")
def risparmi_pagina():
    breadcrumb = [("Spese", "/spese"), ("Risparmi", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb=breadcrumb)

    periodi = D.periodi_risparmio(client)
    imp = D.impostazioni(client)

    if not periodi:
        corpo = f'''<div class="empty">{icon("spese")}
          <div class="t">Nessun periodo</div>
          <div class="s">I periodi nascono dalle entrate di categoria
            "Stipendio": registrane una e questa pagina si popola.</div></div>'''
        return _render(corpo, breadcrumb=breadcrumb)

    corrente = periodi[0]
    perc = float(imp.get("percentuale_risparmio") or 0)

    def n(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    # Quote di destinazione del risparmio, dalle impostazioni in vigore.
    quote = [
        ("Fondo emergenze", "quota_emergenze", imp.get("perc_fondo_emergenze")),
        ("Viaggi",          "quota_viaggi",    imp.get("perc_viaggi")),
        ("Fondo casa",      "quota_casa",      imp.get("perc_fondo_casa")),
        ("Regali",          "quota_regali",    imp.get("perc_regali")),
        ("Altro",           "quota_altro",     imp.get("perc_altro")),
    ]
    quote_html = "".join(f'''
      <div class="row">
        <span class="t">{nome}<span class="sub">{pct(n(p))} del risparmio</span></span>
        <span class="v tnum">€ {eur(n(corrente.get(chiave)))}</span>
      </div>''' for nome, chiave, p in quote if n(p) > 0)

    consigliato = n(corrente.get("risparmio_consigliato"))
    rimanente = n(corrente.get("rimanente"))
    speso = n(corrente.get("speso"))
    bonifico = n(corrente.get("bonifico"))
    altre = n(corrente.get("altre_entrate"))

    voci = [
        ("Stipendio",             bonifico,                              "pos"),
        ("Altre entrate",         altre,                                 "pos"),
        ("Spese del periodo",     -speso,                                "neg"),
        ("Spese fisse",           -n(corrente.get("fisso")),             ""),
        ("Spese personali",       -n(corrente.get("personale")),         ""),
        ("Benzina",               -n(corrente.get("benzina")),           ""),
        ("Viaggi",                -n(corrente.get("viaggi")),            ""),
    ]
    dettaglio = "".join(f'''
      <div class="row">
        <span class="t">{nome}</span>
        <span class="v tnum {cls}">{eur_segno(val)}</span>
      </div>''' for nome, val, cls in voci if abs(val) > 0)

    storico = "".join(f'''
      <div class="row">
        <span class="k">{data_it(p.get("data_bonifico"))}</span>
        <span class="t">{(p.get("mese") or "—").capitalize()}
          <span class="sub">entrate € {eur(n(p.get("bonifico")) + n(p.get("altre_entrate")), 0)}
            · uscite € {eur(n(p.get("speso")), 0)}</span></span>
        <span class="v tnum">€ {eur(n(p.get("risparmio_consigliato")), 0)}</span>
      </div>''' for p in periodi[:12])

    body = f'''
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat">
        <div class="val tnum accent">€ {eur(consigliato)}</div>
        <div class="lbl">Risparmio consigliato</div>
        <div class="hint">{pct(perc)} di quel che resta</div>
      </div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum {"pos" if rimanente >= 0 else "neg"}">€ {eur(rimanente, 0)}</div>
        <div class="lbl">Resta nel periodo</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum neg">€ {eur(speso, 0)}</div>
        <div class="lbl">Speso</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum">€ {eur(n(corrente.get("rimanente_finale")), 0)}</div>
        <div class="lbl">Dopo il risparmio</div></div></div>
    </div>

    <div class="grid split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Periodo corrente</div>
            <span class="chip">{data_it(corrente.get("data_bonifico"))}
              → {data_it(corrente.get("prossimo_bonifico")) or "oggi"}</span>
          </div>
          <div class="rows detail">{dettaglio}</div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Periodi precedenti</div></div>
          <div class="rows detail">{storico}</div>
          <div class="hint mt-2">L'importo a destra è il risparmio consigliato del periodo.</div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Quanto hai messo via</div></div>
          <p class="small muted">
            Registra il risparmio effettivo del periodo corrente: è quello che
            l'app confronta col consigliato per dirti se sei in linea.
          </p>
          <div class="field mt-4">
            <label>Risparmio effettivo (€)</label>
            <input type="number" step="0.01" min="0" inputmode="decimal" id="f_eff"
                   placeholder="{eur(consigliato)}">
          </div>
          <div class="actions">
            <button type="button" class="btn block" onclick="onSalva()">Registra</button>
          </div>
        </div>

        {f"""<div class="card">
          <div class="card-head"><div class="eyebrow">Come si divide</div></div>
          <div class="rows detail">{quote_html}</div>
        </div>""" if quote_html else ""}
      </div>
    </div>

    <div id="toast" class="toast"></div>
    <script>
      const DATA_BONIFICO = {corrente.get("data_bonifico")!r};
      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 2600);
      }}
      async function onSalva() {{
        const v = Number(document.getElementById('f_eff').value || 0);
        if (!(v >= 0)) {{ toast('Importo non valido', 'err'); return; }}
        try {{
          const r = await fetch('/spese/api/risparmi', {{
            method: 'PATCH', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{data_bonifico: DATA_BONIFICO, effettivo_risparmio: v}}),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Risparmio registrato', 'ok');
          setTimeout(()=>location.reload(), 700);
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}
    </script>'''

    return _render(body, breadcrumb=breadcrumb)


@spese_bp.get("/api/risparmi")
def api_risparmi():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    return jsonify(D.periodi_risparmio(client))


@spese_bp.patch("/api/risparmi")
def api_risparmi_aggiorna():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    body = request.get_json(silent=True) or {}
    quando = body.get("data_bonifico")
    if not quando:
        return jsonify({"error": "data_bonifico mancante"}), 400
    esito = D.risparmio_effettivo(client, quando, body.get("effettivo_risparmio"))
    return (jsonify(esito), 400) if esito.get("error") else jsonify(esito)


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="spese", eyebrow="Risparmi",
                                title_html='I miei <em>risparmi</em>',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
