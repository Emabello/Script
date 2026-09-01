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
import json as _json
from datetime import date

from flask import Response, request, jsonify

from . import spese_bp
from . import dati as D
from . import revolut
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_it, mese_anno, pct
# Una sola domanda, una sola risposta: "i soldi sono arrivati?" la sa
# il modulo fatture, e la risposta e' la data di incasso (non lo stato).
from fatture.costanti import ha_incassato


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _fatture_da_girocontare(client) -> list[dict]:
    """
    Le fatture gia' incassate il cui denaro sta ancora sul conto P.IVA.

    Legge `b2f_fatture` da qui, che e' l'area Spese, e lo fa apposta: il
    passo 1 della procedura non ha senso senza sapere se c'e' qualcosa da
    spostare. La query e' in sola lettura e sotto `try` — se l'area
    Fatture non e' raggiungibile la procedura perde un riquadro, non la
    pagina.

    Il filtro su `data_giroconto` e' in Python e non nella query: il
    "non ancora fatto" e' un NULL, e PostgREST vuole `is.null` mentre
    l'harness di anteprima non lo implementa. Le fatture incassate sono
    poche decine l'anno: filtrarle qui non costa niente. Per lo stesso
    motivo ci sta anche il filtro sull'incasso: `ha_incassato` guarda
    `data_incasso`, non lo stato, perche' dopo l'incasso la fattura
    prosegue verso lo studio e lo SDI e resta pagata.
    """
    try:
        r = (client.table("b2f_fatture")
             .select("id,numero,totale,data_incasso,data_giroconto,stato")
             .neq("stato", "annullata")
             .order("data_incasso", desc=True).execute())
        righe = getattr(r, "data", None) or []
    except Exception:
        return []
    return [f for f in righe
            if ha_incassato(f) and not f.get("data_giroconto")]


def _card_procedura(client, periodo_label: str, consigliato: float,
                    gia_messo: float, anteprima: str, dal: str = "") -> str:
    """
    La procedura di fine periodo: dall'incasso ai salvadanai, un passo
    alla volta e con la conferma di chi la esegue.

    Sostituisce il campo "Risparmio effettivo" che stava qui prima. Non
    e' un cambio di interfaccia: quel campo scriveva un numero su
    `risparmi_periodo` **al posto** del movimento bancario, ed e' la
    seconda strada che la migrazione §8.11 ha chiuso — dopo di lei
    nessuno legge piu' quella colonna. Qui invece si registra l'uscita
    vera dal conto, con la sua data, come la vede la banca.

    Il denaro non lo muove l'app: il bonifico lo fai tu. Questa pagina
    dice **quanto** (la percentuale di `impostazioni` su quel che resta),
    **come si divide** fra i cinque salvadanai, e tiene il conto che e'
    stato fatto.
    """
    oggi = date.today().isoformat()

    if gia_messo > 0:
        return f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Procedura — {periodo_label or "periodo corrente"}</div>
            <span class="chip pos">fatta</span>
          </div>
          <div class="stat">
            <div class="val tnum pos">€ {eur(gia_messo)}</div>
            <div class="lbl">già messi via in questo periodo</div>
          </div>
          <p class="small muted mt-3">
            Sono le uscite di categoria "Risparmi" registrate
            {"dal " + data_it(dal) if dal else "in questo periodo"} a oggi,
            meno gli eventuali rientri. Il consigliato era € {eur(consigliato)}.
          </p>
          <a class="btn ghost block mt-4"
             href="/spese/movimenti?categoria=Risparmi">Vedi i movimenti</a>
        </div>'''

    da_girocontare = _fatture_da_girocontare(client)
    passo1 = ""
    if da_girocontare:
        righe = "".join(
            f'<div class="row"><span class="t">'
            f'<a href="/fatture/{f.get("id")}">{f.get("numero") or ("#" + str(f.get("id")))}</a>'
            f'<span class="sub">incassata il {data_it(f.get("data_incasso"))}</span></span>'
            f'<span class="v tnum">€ {eur(f.get("totale"))}</span></div>'
            for f in da_girocontare[:5])
        passo1 = f'''
          <div class="notice warn">
            <strong>Prima:</strong> {len(da_girocontare)} fattur{"a" if len(da_girocontare) == 1 else "e"}
            incassat{"a" if len(da_girocontare) == 1 else "e"} con il denaro ancora
            sul conto P.IVA. Ripartiscil{"a" if len(da_girocontare) == 1 else "e"}
            prima di calcolare il risparmio: la quota si applica a quel che
            resta sul conto personale, e finché l'incasso non è arrivato lì
            quel numero è più basso del vero.
          </div>
          <div class="rows detail mb-4">{righe}</div>'''

    return f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">Procedura — {periodo_label or "periodo corrente"}</div>
        <span class="chip warn">da fare</span>
      </div>
      {passo1}
      <p class="small muted">Il bonifico ai salvadanai lo fai tu dalla banca:
        qui si registra che è successo, come uscita vera dal conto. È quello
        che tiene il saldo dell'app uguale a quello di WeBank.</p>
      <div class="field-group mt-4">
        <div class="field">
          <label>Quanto metti via (€)</label>
          <input type="number" step="0.01" min="0" inputmode="decimal" id="f_imp"
                 value="{consigliato:.2f}" oninput="aggiornaQuote()">
        </div>
        <div class="field">
          <label>Data del bonifico</label>
          <input type="date" id="f_data" value="{oggi}">
        </div>
      </div>
      <div class="rows detail mt-3">{anteprima}</div>
      <div class="actions mt-4">
        <button type="button" class="btn block" id="btnEsegui"
                onclick="onEsegui()">Registra il bonifico ai salvadanai</button>
      </div>
      <p class="hint mt-2">Il consigliato è € {eur(consigliato)}. Cambialo se
        hai spostato una cifra diversa: quello che conta è che qui ci sia il
        numero che è uscito davvero dal conto.</p>
    </div>'''


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

    # --- La procedura di fine periodo -----------------------------------
    # Due passi, nell'ordine in cui il denaro si muove davvero:
    #   1. l'incasso della fattura sta ancora sul conto P.IVA -> spostalo
    #      sul conto personale (lo fa fatture/giroconto.py: qui si dice
    #      solo che c'e' da farlo, con il link per andarci);
    #   2. la quota di risparmio esce dal personale verso i salvadanai.
    # Il passo 2 senza il passo 1 non e' sbagliato, e' prematuro: si
    # risparmierebbe su un conto dove quei soldi non sono ancora arrivati.
    dal = str(corrente.get("data_bonifico") or "")[:10]
    gia_messo = D.risparmio_del_periodo(client, dal) if dal else 0.0
    quote_js = _json.dumps(
        [{"chiave": k, "perc": n(p)} for k, _nome, _col, p in quote if n(p) > 0],
        ensure_ascii=False)
    anteprima = "".join(
        f'<div class="row"><span class="t">{nome}'
        f'<span class="sub">{pct(n(p))}</span></span>'
        f'<span class="v tnum" id="q_{k}">€ {eur(consigliato * n(p))}</span></div>'
        for k, nome, _col, p in quote if n(p) > 0)
    procedura_html = _card_procedura(
        client, mese_anno(corrente.get("data_bonifico")),
        consigliato=consigliato, gia_messo=gia_messo, anteprima=anteprima,
        dal=dal)

    periodo_label = mese_anno(corrente.get("data_bonifico"))
    fine_label = (data_it(corrente.get("prossimo_bonifico"))
                 if corrente.get("prossimo_bonifico") else "oggi, ancora aperto")

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
        {procedura_html}

        {f"""<div class="card">
          <div class="card-head"><div class="eyebrow">Come si divide</div></div>
          <div class="rows detail">{quote_html}</div>
        </div>""" if quote_html else ""}

        {blocco_salvadanai}
      </div>
    </div>

    <div id="toast" class="toast"></div>
    <script>
      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 2600);
      }}
      const QUOTE = {quote_js};

      // L'anteprima si aggiorna mentre scrivi: la domanda vera non e'
      // "quanto metto via" ma "quanto finisce in ciascun secchiello", e
      // vederla dopo aver confermato e' troppo tardi.
      function aggiornaQuote() {{
        const v = Number(document.getElementById('f_imp').value || 0);
        QUOTE.forEach(q => {{
          const el = document.getElementById('q_' + q.chiave);
          if (el) el.textContent = '€ ' + (v * q.perc).toLocaleString('it-IT',
            {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
        }});
      }}

      async function onEsegui() {{
        const v = Number(document.getElementById('f_imp').value || 0);
        const quando = document.getElementById('f_data').value;
        if (!(v > 0)) {{ toast('Importo non valido', 'err'); return; }}
        if (!confirm('Registro un\'uscita di € ' + v.toLocaleString('it-IT',
            {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) +
            ' dal conto personale verso i salvadanai, con data ' + quando +
            '.\n\nIl bonifico vero lo fai tu dalla banca: qui si registra che '
            + 'e\' successo.')) return;
        const btn = document.getElementById('btnEsegui');
        btn.disabled = true;
        try {{
          const r = await fetch('/spese/api/risparmi/esegui', {{
            method: 'POST', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{importo: v, data: quando}}),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); btn.disabled = false; return; }}
          toast('Bonifico registrato', 'ok');
          setTimeout(()=>location.reload(), 800);
        }} catch (e) {{
          toast('Errore rete: ' + e.message, 'err'); btn.disabled = false;
        }}
      }}
    </script>'''

    return _render(body, breadcrumb=breadcrumb)


@spese_bp.get("/api/risparmi")
def api_risparmi():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    return jsonify(D.periodi_risparmio(client))


@spese_bp.post("/api/risparmi/esegui")
def api_risparmi_esegui():
    """
    Il passo 2 della procedura: registra il bonifico ai salvadanai.

    Body: {"importo": 812.40, "data": "2026-08-31"}

    Scrive **un'uscita vera** sul conto personale, categoria "Risparmi",
    passando da `spese/dati.py` come ogni altra scrittura. Non divide il
    movimento in cinque righe: la banca vede un bonifico, e la
    ripartizione fra i secchielli la ricalcola `v_risparmi_mese` dalle
    percentuali di `impostazioni`.
    """
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    body = request.get_json(silent=True) or {}
    quando = (body.get("data") or "").strip() or None
    esito = D.registra_bonifico_risparmio(
        client, body.get("importo"), quando,
        descrizione="Bonifico ai salvadanai (Revolut)")
    if esito.get("error"):
        return jsonify(esito), 400
    return jsonify({"ok": True, **esito})


@spese_bp.patch("/api/risparmi")
def api_risparmi_aggiorna():
    """
    Chiuso: scriveva su una colonna che non legge piu' nessuno.

    Fino alla migrazione README §8.11 questo endpoint dichiarava il
    risparmio del periodo su `risparmi_periodo.effettivo_risparmio`, e
    quel numero *sostituiva* il movimento bancario nel calcolo del
    saldo. Da quando il risparmio e' un'uscita vera di `spese`,
    `v_risparmi_mese` calcola l'effettivo dai movimenti e quella colonna
    non entra piu' in nessun conto: continuare ad accettarlo vorrebbe
    dire scrivere in un posto dove nessuno guarda, che e' peggio di un
    errore — sembra funzionare.

    Risponde 409 invece di sparire perche' una scheda rimasta aperta da
    prima del deploy lo chiamerebbe comunque, e deve sapere perche' non
    ha funzionato.
    """
    return jsonify({
        "error": "Il risparmio non si dichiara più: si registra come "
                 "movimento vero. Usa la procedura di fine periodo su "
                 "/spese/risparmi (o POST /spese/api/risparmi/esegui).",
        "sostituito_da": "/spese/api/risparmi/esegui",
    }), 409


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="spese", eyebrow="Risparmi",
                                title_html='I miei <em>risparmi</em>',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
