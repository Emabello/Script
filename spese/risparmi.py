"""
spese/risparmi.py — I periodi di stipendio e quanto metti da parte.

COME RAGIONA QUESTA PAGINA
--------------------------
Il conto personale non ragiona per mesi solari ma per periodi che vanno
da un bonifico dello stipendio al successivo: e' v_periodi_stipendio a
delimitarli, prendendo le entrate di categoria "Stipendio" **o**
"Giroconto P.IVA" — il giroconto dalla P.IVA e' il tuo stipendio di
fatto da quando hai aperto la partita IVA, quindi apre un periodo
esattamente come faceva prima lo stipendio da dipendente. Richiede la
migrazione README §8.7; prima di applicarla il giroconto restava
"altre entrate" dentro un periodo che non si chiudeva mai.

Per ogni periodo v_risparmi_mese calcola quanto e' entrato, quanto e'
uscito, cosa resta e quale sarebbe il risparmio consigliato — la
percentuale scelta in `impostazioni` applicata a quel che resta. Tu
registri quanto hai messo via davvero, e la differenza fra consigliato
ed effettivo e' l'unica cosa che conta davvero guardare — per questo
la mostriamo esplicitamente sia sul periodo corrente sia sullo storico
(richiede anch'essa la §8.7: prima la vista calcolava l'effettivo ma
non lo esponeva mai come colonna propria).

Rotte HTML:
  GET /spese/risparmi

Rotte JSON:
  GET   /spese/api/risparmi
  PATCH /spese/api/risparmi        {data_bonifico, effettivo_risparmio}
"""
from flask import Response, request, jsonify

from . import spese_bp
from . import dati as D
from . import revolut
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_it, mese_anno, pct


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


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
            "Stipendio" o "Giroconto P.IVA": registrane una e questa
            pagina si popola.</div></div>'''
        return _render(corpo, breadcrumb=breadcrumb)

    corrente = periodi[0]
    perc = float(imp.get("percentuale_risparmio") or 0)

    n = _n

    # Quote di destinazione del risparmio, dalle impostazioni in vigore.
    # La corrispondenza fra il secchiello, la sua percentuale e la colonna
    # della vista sta in `revolut.SALVADANAI`, una volta sola: e' la stessa
    # che serve per confrontarli con i saldi Revolut, e due elenchi
    # paralleli prima o poi divergono.
    quote = [(chiave_rev, nome_app, colonna, imp.get(campo_perc))
             for chiave_rev, _, nome_app, campo_perc, colonna, _
             in revolut.SALVADANAI]
    quote_html = "".join(f'''
      <div class="row">
        <span class="t">{nome}<span class="sub">{pct(n(p))} del risparmio</span></span>
        <span class="v tnum">€ {eur(n(corrente.get(colonna)))}</span>
      </div>''' for _, nome, colonna, p in quote if n(p) > 0)

    # --- Quanto dovrebbe esserci in ogni salvadanaio, e quanto c'è ------
    # La quota per periodo dice poco da sola: quello che serve sapere e'
    # se il secchiello, sommato da sempre, contiene quello che dovrebbe.
    # Il "dovrebbe" e' la somma delle quote di tutti i periodi; il "c'e'"
    # arriva dai saldi Revolut, che sono l'unica misura indipendente.
    rev = revolut.saldo_revolut(client)
    reali = rev.get("salvadanai") or {}
    blocco_salvadanai = ""
    if reali:
        righe_sv = ""
        for chiave_rev, nome, colonna, _p in quote:
            atteso = round(sum(n(x.get(colonna)) for x in periodi), 2)
            reale = n(reali.get(chiave_rev))
            if not atteso and not reale:
                continue
            scarto = round(reale - atteso, 2)
            cls = "pos" if scarto >= -1 else "neg"
            verso = "in più" if scarto >= 0 else "in meno"
            righe_sv += f'''
          <div class="row">
            <span class="t">{nome}
              <span class="sub">dovrebbe averne € {eur(atteso)} ·
                € {eur(abs(scarto))} {verso}</span></span>
            <span class="v tnum {cls}">€ {eur(reale)}</span>
          </div>'''
        if righe_sv:
            tot_reale = round(sum(n(v) for v in reali.values()), 2)
            blocco_salvadanai = f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Nei salvadanai, davvero</div>
            <span class="chip">€ {eur(tot_reale, 0)}</span>
          </div>
          <div class="rows detail">{righe_sv}</div>
          <p class="small muted mt-3">
            A destra quanto c'è oggi su Revolut (saldi al
            {data_it(rev.get("data"))}); sotto la riga, quanto dovrebbe
            esserci sommando le quote di tutti i periodi registrati. Uno
            scarto non è di per sé un errore — dai salvadanai si preleva —
            ma è l'unico posto in cui si vede.
          </p>
        </div>'''
    elif rev.get("disponibile"):
        blocco_salvadanai = f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">Nei salvadanai, davvero</div></div>
          <p class="small muted">
            Su Revolut ci sono € {eur(rev.get("risparmi"), 0)} di risparmi, ma
            non è registrato come sono divisi fra i cinque secchielli:
            l'estratto ne dà solo il totale. Scrivilo una volta e questa
            scheda mostrerà, secchiello per secchiello, quanto c'è contro
            quanto dovrebbe esserci.
          </p>
          <a class="btn ghost block mt-4" href="/spese/revolut">Vai a Revolut</a>
        </div>'''

    consigliato = n(corrente.get("risparmio_consigliato"))
    rimanente = n(corrente.get("rimanente"))
    speso = n(corrente.get("speso"))
    bonifico = n(corrente.get("bonifico"))
    altre = n(corrente.get("altre_entrate"))
    # La vista espone sempre un numero (mai vuoto: coalesce a 0 quando il
    # periodo non e' ancora stato registrato). Non potendo distinguere
    # "registrato a zero" da "mai registrato", trattiamo lo zero come "non
    # ancora fatto" — nella pratica nessuno registra zero di proposito.
    effettivo_reg = n(corrente.get("risparmio_effettivo"))
    gia_registrato = effettivo_reg > 0
    valore_default = effettivo_reg if gia_registrato else consigliato

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

    def _riga_storico(p):
        # ".v" e' pensato per UN numero, riga singola, mai per contenuto
        # annidato (vedi shared/design.py: white-space:nowrap): il
        # confronto consigliato/effettivo va nella riga ".sub", che invece
        # va a capo normalmente dentro ".rows.detail".
        cons = n(p.get("risparmio_consigliato"))
        eff = n(p.get("risparmio_effettivo"))
        registrato = eff > 0
        if registrato:
            cls_v = "pos" if eff >= cons else "neg"
            valore = eff
            extra = f' · effettivo € {eur(eff, 0)} ({eur_segno(eff - cons, 0)})'
        else:
            cls_v = ""
            valore = cons
            extra = " · effettivo non ancora registrato"
        return f'''
      <div class="row">
        <span class="k">{data_it(p.get("data_bonifico"))}</span>
        <span class="t">{mese_anno(p.get("data_bonifico")) or (p.get("mese") or "—").capitalize()}
          <span class="sub">consigliato € {eur(cons, 0)}{extra}</span></span>
        <span class="v tnum {cls_v}">€ {eur(valore, 0)}</span>
      </div>'''

    storico = "".join(_riga_storico(p) for p in periodi[:12])

    periodo_label = mese_anno(corrente.get("data_bonifico"))
    fine_label = (data_it(corrente.get("prossimo_bonifico"))
                 if corrente.get("prossimo_bonifico") else "oggi, ancora aperto")

    registrazione_hint = (
        f'Già registrato per questo periodo: <strong>€ {eur(effettivo_reg)}</strong>. '
        f'Modifica e registra di nuovo per correggerlo.'
        if gia_registrato else
        f'Non ancora registrato: il campo qui sotto parte dal consigliato '
        f'(€ {eur(consigliato)}), cambialo con quanto hai messo via davvero.'
    )

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
            {'<span class="chip pos">registrato</span>' if gia_registrato else '<span class="chip warn">da registrare</span>'}
          </div>
          <div class="h2" style="margin:0 0 2px">{periodo_label or "—"}</div>
          <div class="small muted mb-4">
            dal {data_it(corrente.get("data_bonifico"))} al {fine_label}
          </div>
          <div class="rows detail">{dettaglio}</div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Periodi precedenti</div></div>
          <div class="rows detail">{storico}</div>
          <p class="small muted mt-2">A destra il consigliato (o l'effettivo, se
            già registrato); sotto la riga, il confronto fra i due.</p>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Quanto hai messo via — {periodo_label or "periodo corrente"}</div></div>
          <p class="small muted">{registrazione_hint}</p>
          <div class="field mt-4">
            <label>Risparmio effettivo (€)</label>
            <input type="number" step="0.01" min="0" inputmode="decimal" id="f_eff"
                   value="{valore_default:.2f}">
          </div>
          <div class="actions">
            <button type="button" class="btn block" onclick="onSalva()">Registra</button>
          </div>
        </div>

        {f"""<div class="card">
          <div class="card-head"><div class="eyebrow">Come si divide</div></div>
          <div class="rows detail">{quote_html}</div>
        </div>""" if quote_html else ""}

        {blocco_salvadanai}
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
