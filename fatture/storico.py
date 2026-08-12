"""
fatture/storico.py — Lista fatture emesse + dettaglio.

Rotte HTML:
  GET /fatture/storico          -> lista fatture
  GET /fatture/<int:fid>        -> dettaglio fattura (solo lettura in questo blocco)

Rotte JSON:
  GET /fatture/api/fatture              -> elenco
  GET /fatture/api/fatture/<int:fid>    -> singola
  POST /fatture/api/fatture             -> crea (usato dall'editor)
  GET /fatture/api/next_progressivo?anno=YYYY -> prossimo numero
"""
from datetime import date

from flask import Response, request, jsonify

from . import fatture_bp
from . import accantonamento as acc
from .costanti import (
    CATEGORIE_SPESE_PIVA, STATI, STATI_CHIAVI, STATI_LABEL, STATI_CLASSE,
    STATI_DESCR, STATI_PERCORSO, STATI_EMESSE, DATE_STATO,
    normalizza_stato, prossimo_stato, modificabile, motivo_blocco,
    scorpora_rivalsa, RIVALSA_PERC,
)
from shared.theme import render_page
from shared.design import icon as _icon
from shared.supabase_client import get_client, is_configured
from shared.fmt import eur as _fmt_eur, data_it as _fmt_date, pct


def cliente_label(f: dict) -> str:
    """Nome leggibile del cliente a partire dallo snapshot della fattura.

    Testo grezzo, non escapato: nome/cognome/denominazione sono testo
    libero copiato dall'anagrafica al momento dell'emissione, quindi chi
    lo stampa in HTML deve passarlo da _esc()."""
    snap = f.get("cliente_snapshot") or {}
    tipo = snap.get("tipo") or "azienda"
    if tipo == "privato":
        return f'{snap.get("nome","")} {snap.get("cognome","")}'.strip() or "—"
    return snap.get("denominazione") or "—"


# Alias interno storico
_cliente_label = cliente_label


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _stato_chip(stato: str) -> str:
    s = normalizza_stato(stato)
    cls = STATI_CLASSE.get(s, "")
    lbl = STATI_LABEL.get(s, s or "—")
    return f'<span class="chip {cls}">{lbl}</span>'


def _supabase_or_error():
    if not is_configured():
        return None, ('<div class="notice warn">Supabase non configurato.</div>')
    return get_client(), None


def _timeline(f: dict, stato: str) -> str:
    """
    Il percorso della fattura, con le date dei passaggi gia' avvenuti.

    Serve a rendere visibile una cosa che altrimenti resta implicita: dopo
    "inviata allo studio" il documento non e' piu' in mano tua, ed e' per
    questo che smette di essere modificabile.
    """
    if stato == "annullata":
        return ('<div class="notice neg small">Fattura annullata: '
                'non concorre ai calcoli fiscali.</div>')

    campo_data = {k: v[0] for k, v in DATE_STATO.items()}
    idx_corrente = (STATI_PERCORSO.index(stato)
                    if stato in STATI_PERCORSO else -1)

    passi = []
    for i, chiave in enumerate(STATI_PERCORSO):
        fatto = i <= idx_corrente
        attuale = i == idx_corrente
        data = f.get(campo_data.get(chiave, "")) if chiave in campo_data else f.get("data")
        data_txt = _fmt_date(data) if (fatto and data) else ""
        cls = "fatto" if fatto else ""
        if attuale:
            cls += " ora"
        passi.append(f'''<li class="{cls.strip()}">
          <span class="tl-lbl">{STATI_LABEL[chiave]}</span>
          <span class="tl-data tnum">{data_txt}</span>
          <span class="tl-descr">{STATI_DESCR[chiave]}</span>
        </li>''')

    return f'''
    <style>
      .tl{{list-style:none;margin:0;padding:0;position:relative}}
      .tl li{{position:relative;padding:0 0 var(--sp-4) 26px;color:var(--ink-4)}}
      .tl li:last-child{{padding-bottom:0}}
      /* Il filo che collega i passi: si ferma prima dell'ultimo pallino. */
      .tl li:not(:last-child)::after{{content:"";position:absolute;left:7px;top:16px;
        bottom:2px;width:2px;background:var(--line-strong)}}
      .tl li.fatto:not(:last-child)::after{{background:var(--accent)}}
      .tl li::before{{content:"";position:absolute;left:2px;top:5px;
        width:12px;height:12px;border-radius:50%;
        border:2px solid var(--line-strong);background:var(--surface)}}
      .tl li.fatto::before{{border-color:var(--accent);background:var(--accent)}}
      .tl li.ora::before{{box-shadow:0 0 0 4px var(--accent-soft)}}
      .tl .tl-lbl{{font-size:14px;font-weight:500;color:var(--ink-3)}}
      .tl li.fatto .tl-lbl{{color:var(--ink)}}
      .tl li.ora .tl-lbl{{color:var(--accent-text)}}
      .tl .tl-data{{float:right;font-size:12.5px;color:var(--ink-3)}}
      .tl .tl-descr{{display:block;font-size:12px;color:var(--ink-3);
        margin-top:2px;line-height:1.4}}
    </style>
    <ol class="tl">{"".join(passi)}</ol>'''


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------

@fatture_bp.get("/storico")
def storico_list():
    sb, err = _supabase_or_error()
    if err:
        return _render(err, breadcrumb=[("Fatture", "/fatture"), ("Storico", "")])

    anno_default = date.today().year
    anno = request.args.get("anno", type=int) or anno_default
    stato = request.args.get("stato") or ""

    try:
        q = (sb.table("b2f_fatture").select("*")
               .eq("anno", anno).order("data", desc=True))
        if stato:
            q = q.eq("stato", stato)
        r = q.execute()
        rows = r.data or []
    except Exception as e:
        return _render(f'<div class="notice err">Errore: {str(e)[:200]}</div>',
                       breadcrumb=[("Fatture", "/fatture"), ("Storico", "")])

    # Riepilogo anno
    valide = [x for x in rows if normalizza_stato(x.get("stato")) in STATI_EMESSE]
    tot_fatturato = sum(float(x.get("totale") or 0) for x in valide)
    tot_incassato = sum(float(x.get("totale") or 0) for x in rows
                        if normalizza_stato(x.get("stato")) == "incassata")
    da_incassare = round(tot_fatturato - tot_incassato, 2)

    # Toolbar
    stato_opts = "".join(
        f'<option value="{k}"{" selected" if stato == k else ""}>{lbl}</option>'
        for k, lbl, _, _ in STATI
    )
    anno_opts = "".join(f'<option value="{y}"{" selected" if y == anno else ""}>{y}</option>'
                        for y in range(anno_default, anno_default - 6, -1))
    toolbar = f'''
    <div class="toolbar">
      <select class="select-pill" aria-label="Anno"
        onchange="const u=new URL(location.href);u.searchParams.set('anno',this.value);location.href=u">
        {anno_opts}
      </select>
      <select class="select-pill" aria-label="Stato"
        onchange="const u=new URL(location.href);if(this.value){{u.searchParams.set('stato',this.value)}}else{{u.searchParams.delete('stato')}};location.href=u">
        <option value="">Tutti gli stati</option>
        {stato_opts}
      </select>
    </div>
    '''

    riepilogo = f'''
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat">
        <div class="val tnum">€ {_fmt_eur(tot_fatturato, 0)}</div>
        <div class="lbl">Fatturato {anno}</div>
        <div class="hint">{len(valide)} document{"o" if len(valide) == 1 else "i"}</div>
      </div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum pos">€ {_fmt_eur(tot_incassato, 0)}</div>
        <div class="lbl">Incassato</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum {"warn" if da_incassare > 0 else ""}">€ {_fmt_eur(da_incassare, 0)}</div>
        <div class="lbl">Da incassare</div></div></div>
    </div>
    '''

    if not rows:
        body = f'''{riepilogo}{toolbar}
        <div class="empty">
          {_icon("empty-doc")}
          <div class="t">Nessuna fattura per il {anno}</div>
          <div class="s">Crea la prima con il pulsante in basso.</div>
        </div>'''
    else:
        items = []
        for f in rows:
            stato = normalizza_stato(f.get("stato"))
            incasso = (f' · incassata il {_fmt_date(f.get("data_incasso"))}'
                       if stato == "incassata" and f.get("data_incasso") else "")
            items.append(f'''
            <a class="item" href="/fatture/{f["id"]}">
              <span class="body">
                <span class="n">{_esc(f.get("numero", "—"))} · {_esc(cliente_label(f))}</span>
                <span class="m">{_fmt_date(f.get("data"))}{incasso}</span>
              </span>
              <span class="end">
                <span class="amt tnum">€ {_fmt_eur(f.get("totale"))}</span>
                {_stato_chip(stato)}
              </span>
            </a>''')
        body = f'{riepilogo}{toolbar}<div class="list">{"".join(items)}</div>'

    return _render(body, eyebrow=f"Storico {anno}",
                   breadcrumb=[("Fatture", "/fatture"), ("Storico", "")],
                   fab=("Nuova fattura", "/fatture/nuova"))


# ---------------------------------------------------------------------------
# Dettaglio
# ---------------------------------------------------------------------------

@fatture_bp.get("/<int:fid>")
def fattura_dettaglio(fid):
    sb, err = _supabase_or_error()
    if err:
        return _render(err, breadcrumb=[("Fatture", "/fatture"), ("Storico", "/fatture/storico"), (str(fid), "")])
    try:
        r = sb.table("b2f_fatture").select("*").eq("id", fid).single().execute()
        f = r.data
    except Exception as e:
        return _render(f'<div class="notice err">{str(e)[:200]}</div>',
                       breadcrumb=[("Fatture", "/fatture"),
                                   ("Storico", "/fatture/storico"), (str(fid), "")])

    # Preleva emittente per iniezione JS del PDF
    try:
        em = (sb.table("b2f_emittente").select("*").eq("id", 1)
                .single().execute()).data or {}
    except Exception:
        em = {}
    from shared.pdfgen import pdf_script
    pdf_js = pdf_script(em)

    snap = f.get("cliente_snapshot") or {}
    righe = f.get("righe") or []
    righe_html = "".join(
        f'''<div class="row">
          <span class="k">{r.get("qta", 1)}{" " + _esc(r.get("um")) if r.get("um") else ""}</span>
          <span class="t">{_esc((r.get("descrizione") or "").strip()) or "—"}
            <span class="sub">€ {_fmt_eur(r.get("prezzo"))} cad.</span></span>
          <span class="v tnum">€ {_fmt_eur((r.get("qta") or 0) * (r.get("prezzo") or 0))}</span>
        </div>''' for r in righe
    )
    if not righe_html:
        righe_html = '<div class="row"><span class="t muted">Nessuna riga</span></div>'

    # Numero display per il PDF: solo progressivo
    numero_full = f.get("numero") or ""
    if "/" in numero_full:
        _, prog = numero_full.split("/", 1)
        numero_display = str(int(prog))  # rimuove leading zeros
    else:
        numero_display = str(f.get("progressivo") or "")

    # Payload PDF serializzato per JavaScript
    import json
    payload_js = json.dumps({
        "numero_display": numero_display,
        "data_iso":       f.get("data"),
        "tipo_doc":       f.get("tipo_doc") or "TD01",
        "cliente":        snap,
        "righe":          [{"descrizione": r.get("descrizione"), "qta": r.get("qta"),
                            "um": r.get("um"), "prezzo": r.get("prezzo")} for r in righe],
        "corrispettivo":  float(f.get("imponibile") or 0),
        "compenso":       round(float(f.get("imponibile") or 0)
                                - float(f.get("cassa_importo") or 0), 2),
        "imponibile":     float(f.get("imponibile") or 0),
        "cassa_perc":     float(f.get("cassa_perc") or 0),
        "cassa_importo":  float(f.get("cassa_importo") or 0),
        "bollo_add":      bool(f.get("bollo_addebitato")),
        "bollo_dovuto":   float(f.get("imponibile") or 0) > 77.47,
        "totale":         float(f.get("totale") or 0),
        "pagamento_mod":  f.get("pagamento_mod") or "Bonifico bancario",
        "scadenza":       f.get("scadenza"),
    }, ensure_ascii=False).replace("<", "\\u003c")  # niente </script> dentro il blob:
                                                       # un cliente o una riga con quel
                                                       # testo chiuderebbe il tag prima

    # Chip per lo stato "registrata su spese P.IVA"
    spesa_id_val = f.get("spesa_piva_id")
    registrata_chip = ""
    if spesa_id_val:
        registrata_chip = '<span class="chip">Registrata su P.IVA</span>'

    # Bottone registra: nascosto se già registrata
    btn_registra_display = "none" if spesa_id_val else ""

    # Data incasso corrente (default per il form registra)
    data_incasso_default = (f.get("data_incasso") or f.get("data")
                            or date.today().isoformat())

    # Descrizione precompilata per la riga spese (va in un value="..."
    # attribute: va escapata come tutto il resto del testo libero).
    desc_precompilata = _esc(f"Fattura {f.get('numero','')} — {_cliente_label(f)}")

    stato_corrente = normalizza_stato(f.get("stato"))

    cat_options = "".join(
        f'<option value="{k}"{" selected" if k=="fatturato" else ""}>{lbl}</option>'
        for k, lbl in CATEGORIE_SPESE_PIVA
    )

    # --- Accantonamento -----------------------------------------------------
    # Il momento in cui questo numero serve e' l'incasso: fino ad allora e'
    # una previsione, e va detto.
    acc_card = ""
    scomposizione = None
    try:
        from .fiscale import get_parametri
        param = get_parametri(sb)
        anno_f = int((f.get("data") or "")[:4] or date.today().year)
        try:
            r_anno = (sb.table("b2f_fatture").select("totale")
                        .eq("stato", "incassata")
                        .gte("data_incasso", f"{anno_f}-01-01")
                        .lte("data_incasso", f"{anno_f}-12-31").execute())
            incassato_anno = sum(float(x.get("totale") or 0) for x in (r_anno.data or []))
        except Exception:
            incassato_anno = 0.0

        if stato_corrente in STATI_EMESSE:
            scomposizione = acc.scomponi(
                f.get("totale"), param, fatturato_riferimento=incassato_anno,
                rivalsa=f.get("cassa_importo") or 0,
                bollo_addebitato=(f.get("bollo") or 0) if f.get("bollo_addebitato") else 0)
            if stato_corrente == "incassata":
                contesto = (f"Fattura incassata il {_fmt_date(f.get('data_incasso'))}. "
                            f"Metti da parte questa quota prima di considerare "
                            f"il resto disponibile.")
                titolo = "Da accantonare"
            else:
                contesto = ("Fattura non ancora incassata: questa è una previsione. "
                            "Le tasse del forfettario maturano all'incasso, non "
                            "all'emissione.")
                titolo = "Da accantonare all'incasso"
            acc_card = acc.card_html(scomposizione, titolo=titolo,
                                     contesto=contesto, uid="accFatt")
    except Exception:
        acc_card = ""

    # --- Giroconto al conto personale ---------------------------------------
    # La quota che avanza e' tua: sta sul conto P.IVA solo perche' e' li'
    # che il cliente ha pagato. Finche' non la sposti, il saldo P.IVA
    # racconta una disponibilita' che in parte non e' spendibile.
    giroconto_fatto = bool(f.get("data_giroconto"))
    giroconto_card = ""
    scelte_giro_html = ""
    lordo_f = float(f.get("totale") or 0)
    rivalsa_f = round(float(f.get("cassa_importo") or 0), 2)

    # La rivalsa e' incassata insieme al corrispettivo e resta sul conto
    # P.IVA: non e' un tuo ricavo, e' il contributo previdenziale che il
    # cliente ti gira perche' tu lo versi. Dentro l'unico numero
    # "accantonato" e' invisibile, quindi va detta esplicitamente in
    # entrambe le facce della ripartizione — quella da decidere e quella
    # gia' fatta.
    riga_rivalsa_giro = ""
    if rivalsa_f > 0:
        riga_rivalsa_giro = (
            f'<div class="row"><span class="t">di cui rivalsa INPS'
            f'<span class="sub">resta sul conto P.IVA: è già dentro la quota '
            f'accantonata, non va messa da parte una seconda volta</span></span>'
            f'<span class="v tnum">€ {_fmt_eur(rivalsa_f)}</span></div>')

    if giroconto_fatto:
        scen_scelto = f.get("accantonamento_scenario") or ""
        etichetta_scelta = acc.ETICHETTE.get(scen_scelto, (scen_scelto or "—",))[0]
        giroconto_card = f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Ripartizione eseguita</div>
            <span class="chip pos">{etichetta_scelta}</span>
          </div>
          <div class="rows detail">
            <div class="row"><span class="t">Rimasto sul conto P.IVA
              <span class="sub">accantonato per tasse, costi e margine</span></span>
              <span class="v tnum">€ {_fmt_eur(f.get("accantonamento_importo"))}</span></div>
            {riga_rivalsa_giro}
            <div class="row"><span class="t">Spostato sul conto personale
              <span class="sub">giroconto del {_fmt_date(f.get("data_giroconto"))}</span></span>
              <span class="v tnum pos">€ {_fmt_eur(f.get("giroconto_importo"))}</span></div>
          </div>
          <div class="actions mt-4">
            <button type="button" class="btn ghost"
                    onclick="onAnnullaGiroconto()">Annulla la ripartizione</button>
          </div>
        </div>'''
    elif stato_corrente == "incassata" and scomposizione and lordo_f > 0:
        # Le quattro scelte, con i numeri veri di questa fattura: e' piu'
        # onesto di quattro etichette astratte da interpretare.
        righe_scelte = []
        pref = scomposizione["scenario_preferito"]
        for k in acc.SCENARI:
            quota = scomposizione["importi"][k]
            resta = scomposizione["netti"][k]
            titolo_s, spiega = acc.ETICHETTE[k]
            righe_scelte.append(f'''
            <label class="scelta-giro">
              <input type="radio" name="scenGiro" value="{k}"
                     {"checked" if k == pref else ""} onchange="aggiornaGiro()">
              <span class="sg-body">
                <span class="sg-top">
                  <span class="sg-nome">{titolo_s}</span>
                  <span class="sg-pct tnum">{pct(scomposizione["aliquote"][k])}</span>
                </span>
                <span class="sg-descr">{spiega}</span>
                <span class="sg-num">
                  Accantoni <strong class="tnum">€ {_fmt_eur(quota)}</strong>
                  · sposti <strong class="tnum pos">€ {_fmt_eur(resta)}</strong>
                </span>
              </span>
            </label>''')
        scelte_giro_html = "".join(righe_scelte)
        nota_rivalsa_card = (
            f'<div class="rows detail mt-3">{riga_rivalsa_giro}</div>'
            if riga_rivalsa_giro else "")
        giroconto_card = f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">Ripartizione dell'incasso</div></div>
          <p class="small muted">
            L'incasso è tutto sul conto P.IVA, ma non è tutto tuo. Scegli quanto
            lasciare da parte: il resto viene spostato sul conto personale con un
            giroconto registrato su entrambi i conti.
          </p>
          {nota_rivalsa_card}
          <button type="button" class="btn block mt-4" onclick="openModal('modalGiro')">
            {_icon("wallet")}Ripartisci e sposta sul personale
          </button>
        </div>'''

    # --- Scomposizione dello scorporo ---------------------------------------
    # Il corrispettivo concordato non cambia: la rivalsa si estrae da dentro.
    # Chi legge deve vedere entrambe le voci, perche' sono quelle che finiscono
    # nella fattura elettronica preparata dallo studio.
    corrispettivo = float(f.get("imponibile") or 0)
    rivalsa = float(f.get("cassa_importo") or 0)
    # Chip in testa, accanto allo stato: la scomposizione sotto si vede
    # solo scorrendo, e la rivalsa e' la voce che si cerca piu' spesso.
    rivalsa_chip = (f'<span class="chip accent">Rivalsa INPS € {_fmt_eur(rivalsa)}</span>'
                    if rivalsa > 0 else "")
    righe_totali = [
        f'<div class="row"><span class="t">Corrispettivo concordato</span>'
        f'<span class="v tnum">€ {_fmt_eur(corrispettivo)}</span></div>'
    ]
    if rivalsa > 0:
        perc = f'{float(f.get("cassa_perc") or 0):g}'.replace(".", ",")
        righe_totali.append(
            f'<div class="row"><span class="t">di cui compenso</span>'
            f'<span class="v tnum">€ {_fmt_eur(corrispettivo - rivalsa)}</span></div>'
            f'<div class="row"><span class="t">di cui rivalsa INPS {perc} %'
            f'<span class="sub">scorporata dal corrispettivo, non aggiunta</span></span>'
            f'<span class="v tnum">€ {_fmt_eur(rivalsa)}</span></div>'
        )
    if float(f.get("bollo") or 0) > 0:
        addeb = "addebitato al cliente" if f.get("bollo_addebitato") else "a tuo carico"
        righe_totali.append(
            f'<div class="row"><span class="t">Bollo <span class="sub">{addeb}</span></span>'
            f'<span class="v tnum">€ {_fmt_eur(f.get("bollo"))}</span></div>'
        )
    totali_html = "".join(righe_totali)

    pagamento = " · ".join(x for x in [
        _esc(f.get("pagamento_mod")) if f.get("pagamento_mod") else None,
        _esc(f.get("pagamento_cond")) if f.get("pagamento_cond") else None,
        f'scadenza {_fmt_date(f.get("scadenza"))}' if f.get("scadenza") else None,
    ] if x)

    # --- Linea temporale ------------------------------------------------------
    timeline_html = _timeline(f, stato_corrente)

    # --- Azioni contestuali ---------------------------------------------------
    puo_modificare = modificabile(stato_corrente)
    avanti = prossimo_stato(stato_corrente)
    azione_principale = ""
    if avanti:
        etichette_azione = {
            "inviata_studio": "Segna inviata allo studio",
            "trasmessa_sdi":  "Segna trasmessa a SDI",
            "incassata":      "Segna incassata",
        }
        azione_principale = (
            f'<button type="button" class="btn" '
            f'onclick="apriAvanzamento(\'{avanti}\')">'
            f'{_icon("check")}{etichette_azione.get(avanti, "Avanza")}</button>'
        )

    if puo_modificare:
        blocco_modifica = (
            f'<a class="btn ghost" href="/fatture/{fid}/modifica">Modifica</a>'
            f'<button type="button" class="btn danger" onclick="onElimina()">Elimina</button>'
        )
        avviso_blocco = ""
    else:
        blocco_modifica = ""
        avviso_blocco = (
            f'<div class="notice warn small mt-3">{motivo_blocco(stato_corrente)}</div>'
        )

    # Arrivo da un tentativo di modifica respinto: la spiegazione va in
    # cima, dove si guarda, non in fondo alle azioni.
    avviso_redirect = ""
    if request.args.get("bloccata") and not puo_modificare:
        avviso_redirect = (
            f'<div class="notice warn mb-4">'
            f'<strong>Modifica non possibile.</strong><br>{motivo_blocco(stato_corrente)}'
            f'</div>'
        )

    opzioni_stato = "".join(
        f'<option value="{k}"{" selected" if k == stato_corrente else ""}>{lbl}</option>'
        for k, lbl, _, _ in STATI
    )
    # Precalcolati fuori dalla f-string: dentro, le graffe doppie servono
    # a produrre graffe letterali e romperebbero le espressioni Python.
    import json as _json
    stati_label_js = _json.dumps(STATI_LABEL, ensure_ascii=False)
    stati_descr_js = _json.dumps(STATI_DESCR, ensure_ascii=False)
    stati_data_js = _json.dumps(
        {k: [v[0], v[1]] for k, v in DATE_STATO.items()}, ensure_ascii=False)
    oggi_iso = date.today().isoformat()

    # Importi dei quattro scenari per il foglio di ripartizione. Calcolati
    # qui una volta sola: il client li rilegge, non li ricalcola.
    scelte_js = _json.dumps(
        {k: {"accantonamento": scomposizione["importi"][k],
             "giroconto": scomposizione["netti"][k]}
         for k in acc.SCENARI} if scomposizione else {},
        ensure_ascii=False)

    body = f'''
    {avviso_redirect}
    <div class="grid split">
      <div class="stack">

        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Riepilogo</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              {_stato_chip(stato_corrente)}{registrata_chip}{rivalsa_chip}
            </div>
          </div>
          <div class="stat">
            <div class="val tnum accent">€ {_fmt_eur(f.get("totale"))}</div>
            <div class="lbl">{f.get("numero", "—")} · {_fmt_date(f.get("data"))}</div>
          </div>
          <div class="rows detail mt-4">{totali_html}</div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Righe</div></div>
          <div class="rows detail">{righe_html}</div>
        </div>

        {acc_card}
        {giroconto_card}
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Percorso</div></div>
          {timeline_html}
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Cliente</div></div>
          <div class="h3">{_esc(cliente_label(f))}</div>
          <div class="small muted mt-2">
            {_esc(snap.get("piva") or snap.get("cf") or "—")}
            {" · " + _esc(snap.get("comune", "")) if snap.get("comune") else ""}
          </div>
          {f'<div class="small muted mt-2">{pagamento}</div>' if pagamento else ""}
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Azioni</div></div>
          <div class="actions col mt-0">
            {azione_principale}
            <button type="button" class="btn ghost" onclick="onRistampa()">
              {_icon("download")}Scarica facsimile
            </button>
            {blocco_modifica}
            <button type="button" class="btn ghost" id="btnRegistra"
                    style="display:{btn_registra_display}" onclick="openModal('modalEntrata')">
              Registra entrata su P.IVA
            </button>
            <button type="button" class="btn ghost" onclick="openModal('modalStato')">
              Cambia stato manualmente
            </button>
          </div>
          {avviso_blocco}
        </div>
      </div>
    </div>

    <!-- ===== Foglio avanzamento di stato ===== -->
    <div class="sheet-ov" id="modalAvanza" role="dialog" aria-modal="true">
      <div class="sheet">
        <h3 id="avanzaTitolo">Avanza</h3>
        <div class="sheet-sub" id="avanzaSub"></div>
        <div class="field">
          <label id="avanzaDataLbl">Data</label>
          <input type="date" id="avanzaData" value="{date.today().isoformat()}">
        </div>
        <div class="actions">
          <button type="button" class="btn ghost" data-close="modalAvanza">Annulla</button>
          <button type="button" class="btn" onclick="onAvanza()">Conferma</button>
        </div>
      </div>
    </div>

    <!-- ===== Foglio cambio stato manuale ===== -->
    <div class="sheet-ov" id="modalStato" role="dialog" aria-modal="true">
      <div class="sheet">
        <h3>Cambia stato</h3>
        <div class="sheet-sub">
          Stato attuale: <strong>{STATI_LABEL.get(stato_corrente, stato_corrente)}</strong>.
          Usalo per correggere un passaggio sbagliato: il percorso normale è
          il pulsante di avanzamento.
        </div>
        <div class="field">
          <label>Nuovo stato</label>
          <select id="statoSel" onchange="onStatoChange()">{opzioni_stato}</select>
        </div>
        <div class="field" id="fldDataStato" style="display:none">
          <label id="lblDataStato">Data</label>
          <input type="date" id="dataStato" value="{data_incasso_default}">
        </div>
        <div class="notice info small" id="statoDescr"></div>
        <div class="actions">
          <button type="button" class="btn ghost" data-close="modalStato">Annulla</button>
          <button type="button" class="btn" onclick="onSalvaStato()">Salva</button>
        </div>
      </div>
    </div>

    <!-- ===== Foglio ripartizione + giroconto ===== -->
    <div class="sheet-ov" id="modalGiro" role="dialog" aria-modal="true">
      <div class="sheet">
        <h3>Ripartisci l'incasso</h3>
        <div class="sheet-sub">
          Su € {_fmt_eur(f.get("totale"))} incassati, quanto lasci sul conto P.IVA
          per tasse e costi. Il resto si sposta sul personale.
          {f"Di questi, € {_fmt_eur(rivalsa_f)} sono rivalsa INPS e restano "
             f"comunque sul conto P.IVA: ogni scenario la copre." if rivalsa_f > 0 else ""}
        </div>
        <div class="scelte-giro">{scelte_giro_html}</div>
        <div class="field">
          <label>Data del giroconto</label>
          <input type="date" id="g_data" value="{data_incasso_default}">
        </div>
        <div class="notice info small" id="g_riepilogo"></div>
        <div class="actions">
          <button type="button" class="btn ghost" data-close="modalGiro">Annulla</button>
          <button type="button" class="btn" onclick="onGiroconto()">Conferma e sposta</button>
        </div>
      </div>
    </div>

    <style>
      .scelte-giro{{display:flex;flex-direction:column;gap:8px;margin-bottom:var(--sp-4)}}
      .scelta-giro{{display:flex;gap:10px;align-items:flex-start;padding:12px;
        border:1px solid var(--line-strong);border-radius:12px;cursor:pointer;
        background:var(--surface);transition:border-color .15s,background .15s}}
      .scelta-giro:hover{{border-color:var(--accent)}}
      .scelta-giro:has(input:checked){{border-color:var(--accent);
        background:var(--accent-soft)}}
      .scelta-giro input{{margin-top:3px;accent-color:var(--accent);flex:none}}
      .sg-body{{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}}
      .sg-top{{display:flex;justify-content:space-between;gap:8px;align-items:baseline}}
      .sg-nome{{font-weight:600;font-size:14.5px;color:var(--ink)}}
      .sg-pct{{font-size:13px;color:var(--accent-text)}}
      .sg-descr{{font-size:12px;color:var(--ink-3);line-height:1.4}}
      .sg-num{{font-size:12.5px;color:var(--ink-2);margin-top:3px}}
    </style>

    <!-- ===== Foglio registra entrata ===== -->
    <div class="sheet-ov" id="modalEntrata" role="dialog" aria-modal="true">
      <div class="sheet">
        <h3>Registra come entrata</h3>
        <div class="sheet-sub">
          Crea un movimento in entrata fra le spese P.IVA, lo collega a questa
          fattura e porta lo stato a "incassata".
        </div>
        <div class="field-group">
          <div class="field"><label>Data</label>
            <input type="date" id="e_data" value="{data_incasso_default}"></div>
          <div class="field"><label>Importo (€)</label>
            <input type="number" step="0.01" inputmode="decimal" id="e_imp"
                   value="{f.get('totale') or 0}"></div>
        </div>
        <div class="field">
          <label>Descrizione</label>
          <input id="e_desc" value="{desc_precompilata}">
        </div>
        <div class="field-group">
          <div class="field"><label>Categoria</label>
            <select id="e_cat">{cat_options}</select></div>
          <div class="field"><label>Sottocategoria</label>
            <input id="e_scat" placeholder="facoltativa"></div>
        </div>
        <div class="actions">
          <button type="button" class="btn ghost" data-close="modalEntrata">Annulla</button>
          <button type="button" class="btn" onclick="onSalvaEntrata()">Registra</button>
        </div>
      </div>
    </div>

    {pdf_js}
    <div id="toast" class="toast"></div>
    <script>
      const FATTURA_ID = {fid};
      const FATTURA_PAYLOAD = {payload_js};

      function onRistampa() {{
        if (!window.b2fRenderInvoicePDF) {{
          alert('Rendering PDF non pronto'); return;
        }}
        window.b2fRenderInvoicePDF(FATTURA_PAYLOAD);
      }}

      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{t.className='toast '+(cls||'')}}, cls==='err' ? 4500 : 2500);
      }}
      function openModal(id) {{ document.getElementById(id).classList.add('show'); }}
      function closeModal(id) {{ document.getElementById(id).classList.remove('show'); }}

      // Etichette e campi data associati a ciascuno stato, dal server:
      // una sola definizione, in fatture/costanti.py.
      const STATI_LABEL = {stati_label_js};
      const STATI_DESCR = {stati_descr_js};
      const STATI_DATA  = {stati_data_js};
      const OGGI = "{oggi_iso}";

      // --- avanzamento lungo il percorso ---
      let statoTarget = null;
      function apriAvanzamento(target) {{
        statoTarget = target;
        document.getElementById('avanzaTitolo').textContent = STATI_LABEL[target] || target;
        document.getElementById('avanzaSub').textContent = STATI_DESCR[target] || '';
        const meta = STATI_DATA[target];
        document.getElementById('avanzaDataLbl').textContent = meta ? meta[1] : 'Data';
        document.getElementById('avanzaData').value = OGGI;
        openModal('modalAvanza');
      }}
      async function onAvanza() {{
        const body = {{stato: statoTarget}};
        const meta = STATI_DATA[statoTarget];
        if (meta) body[meta[0]] = document.getElementById('avanzaData').value;
        await salvaStato(body);
      }}

      // --- cambio stato manuale ---
      function onStatoChange() {{
        const v = document.getElementById('statoSel').value;
        const meta = STATI_DATA[v];
        document.getElementById('fldDataStato').style.display = meta ? 'flex' : 'none';
        if (meta) document.getElementById('lblDataStato').textContent = meta[1];
        document.getElementById('statoDescr').textContent = STATI_DESCR[v] || '';
      }}
      onStatoChange();

      async function onSalvaStato() {{
        const nuovo = document.getElementById('statoSel').value;
        const body = {{stato: nuovo}};
        const meta = STATI_DATA[nuovo];
        if (meta) body[meta[0]] = document.getElementById('dataStato').value;
        await salvaStato(body);
      }}

      async function salvaStato(body) {{
        try {{
          const r = await fetch(`/fatture/api/fatture/${{FATTURA_ID}}/stato`, {{
            method: 'PATCH', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Stato aggiornato', 'ok');
          setTimeout(()=>location.reload(), 500);
        }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
      }}

      // --- eliminazione (solo in bozza, il server ricontrolla) ---
      async function onElimina() {{
        if (!confirm('Eliminare definitivamente questa bozza?\\n\\n'
                     + 'Se invece la fattura è già uscita, usa "Annullata" '
                     + 'come stato: resta nello storico ma non conta nei calcoli.')) return;
        try {{
          const r = await fetch(`/fatture/api/fatture/${{FATTURA_ID}}`, {{method: 'DELETE'}});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Bozza eliminata', 'ok');
          setTimeout(()=>{{ location.href = '/fatture/storico'; }}, 600);
        }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
      }}

      // --- ripartizione dell'incasso e giroconto ---
      // Gli importi dei quattro scenari arrivano gia' calcolati dal server:
      // il riepilogo si limita a rileggerli, senza rifare i conti a meta'.
      const GIRO_SCELTE = {scelte_js};

      function scenarioGiro() {{
        const el = document.querySelector('input[name="scenGiro"]:checked');
        return el ? el.value : null;
      }}
      function aggiornaGiro() {{
        const box = document.getElementById('g_riepilogo');
        if (!box) return;
        const s = scenarioGiro();
        const d = s && GIRO_SCELTE[s];
        if (!d) {{ box.textContent = ''; return; }}
        const fmt = v => new Intl.NumberFormat('it-IT',
          {{minimumFractionDigits:2, maximumFractionDigits:2}}).format(v);
        box.innerHTML = 'Restano sul conto P.IVA <strong>€ ' + fmt(d.accantonamento)
          + '</strong>, si spostano sul personale <strong>€ ' + fmt(d.giroconto)
          + '</strong>.';
      }}

      async function onGiroconto() {{
        const scenario = scenarioGiro();
        if (!scenario) {{ toast('Scegli quanto accantonare', 'err'); return; }}
        const body = {{
          scenario,
          data: document.getElementById('g_data').value,
        }};
        try {{
          const r = await fetch(`/fatture/api/fatture/${{FATTURA_ID}}/giroconto`, {{
            method: 'POST', headers: {{'Content-Type':'application/json'}},
            body: JSON.stringify(body),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Spostati € ' + j.giroconto.toFixed(2) + ' sul personale', 'ok');
          setTimeout(()=>location.reload(), 700);
        }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
      }}

      async function onAnnullaGiroconto() {{
        if (!confirm('Annullare la ripartizione?\\n\\n'
                     + 'Verranno tolti i due movimenti dai conti P.IVA e personale. '
                     + 'Potrai rifarla con un altro scenario.')) return;
        try {{
          const r = await fetch(`/fatture/api/fatture/${{FATTURA_ID}}/giroconto`,
                                {{method: 'DELETE'}});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Ripartizione annullata', 'ok');
          setTimeout(()=>location.reload(), 600);
        }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
      }}
      aggiornaGiro();

      // --- registra come entrata ---
      async function onSalvaEntrata() {{
        const body = {{
          data:         document.getElementById('e_data').value,
          descrizione:  document.getElementById('e_desc').value,
          importo:      Number(document.getElementById('e_imp').value || 0),
          categoria:    document.getElementById('e_cat').value.trim() || null,
          sottocategoria: document.getElementById('e_scat').value.trim() || null,
        }};
        try {{
          const r = await fetch(`/fatture/api/fatture/${{FATTURA_ID}}/registra-entrata`, {{
            method: 'POST', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
          }});
          const j = await r.json();
          if (!r.ok) {{
            toast(j.error || 'Errore registrazione', 'err');
            return;
          }}
          toast('Registrata su spese P.IVA (id ' + j.spesa_piva_id + ')', 'ok');
          setTimeout(()=>location.reload(), 600);
        }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
      }}
    </script>
    '''

    return _render(body,
                   eyebrow=f'Fattura',
                   title_html=f'<em>{f.get("numero","—")}</em>',
                   breadcrumb=[("Fatture", "/fatture"),
                               ("Storico", "/fatture/storico"),
                               (f.get("numero","—"), "")])


# ---------------------------------------------------------------------------
# API JSON
# ---------------------------------------------------------------------------

@fatture_bp.get("/api/fatture")
def api_fatture_list():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    anno = request.args.get("anno", type=int)
    try:
        q = sb.table("b2f_fatture").select("*").order("data", desc=True)
        if anno:
            q = q.eq("anno", anno)
        r = q.execute()
        return jsonify(r.data or [])
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.get("/api/fatture/<int:fid>")
def api_fattura_get(fid):
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    try:
        r = sb.table("b2f_fatture").select("*").eq("id", fid).single().execute()
        return jsonify(r.data or {})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.get("/api/next_progressivo")
def api_next_progressivo():
    """Chiama la funzione SQL b2f_next_progressivo(anno)."""
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    anno = request.args.get("anno", type=int) or date.today().year
    try:
        r = sb.rpc("b2f_next_progressivo", {"p_anno": anno}).execute()
        val = r.data if isinstance(r.data, int) else (r.data or 1)
        numero = f"{anno}/{int(val):03d}"
        return jsonify({"anno": anno, "progressivo": int(val), "numero": numero})
    except Exception as e:
        # Fallback: calcolo lato client se RPC fallisce
        try:
            r = (sb.table("b2f_fatture").select("progressivo")
                   .eq("anno", anno).order("progressivo", desc=True).limit(1).execute())
            data = r.data or []
            val = (data[0]["progressivo"] + 1) if data else 1
            return jsonify({"anno": anno, "progressivo": val,
                            "numero": f"{anno}/{val:03d}"})
        except Exception as e2:
            return jsonify({"error": f"{str(e)[:100]} | fallback: {str(e2)[:100]}"}), 500


@fatture_bp.patch("/api/fatture/<int:fid>/stato")
def api_fattura_stato(fid):
    """
    Cambia lo stato della fattura, registrando la data del passaggio.

    Le date dei passi gia' percorsi non vengono azzerate tornando indietro:
    se ti accorgi di aver segnato "incassata" per sbaglio e torni a
    "trasmessa", la data di trasmissione resta quella vera. L'unica che si
    cancella e' quella dello stato che stai lasciando.
    """
    sb, err = _supabase_or_error()
    if err:
        return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    stato = normalizza_stato(data.get("stato"))
    if stato not in STATI_CHIAVI:
        return jsonify({"error": "stato non valido"}), 400

    f, errore = _carica_fattura(sb, fid)
    if errore:
        return errore

    # Uscire da "incassata" con la ripartizione gia' fatta lascerebbe i due
    # movimenti sui conti senza piu' un incasso che li giustifichi: il conto
    # P.IVA resterebbe alleggerito e il personale gonfiato, senza che nulla
    # lo segnali. Prima si annulla la ripartizione, poi si cambia stato.
    if (stato != "incassata" and normalizza_stato(f.get("stato")) == "incassata"
            and f.get("data_giroconto")):
        return jsonify({
            "error": ("Questa fattura è già stata ripartita: i soldi sono stati "
                      "spostati sul conto personale. Annulla prima la "
                      "ripartizione, altrimenti resterebbero due movimenti "
                      "senza un incasso che li giustifichi."),
            "data_giroconto": f.get("data_giroconto"),
        }), 409

    payload = {"stato": stato}

    # Data del passo in cui si entra. Se ne arriva una, vince. Altrimenti
    # si mette oggi solo se non ce n'era gia' una: rientrare in uno stato
    # gia' attraversato non deve riscriverne la data con quella di oggi,
    # altrimenti tornare indietro per correggere un errore falsifica la
    # cronologia.
    if stato in DATE_STATO:
        campo, _ = DATE_STATO[stato]
        fornita = data.get(campo)
        if fornita:
            payload[campo] = fornita
        elif not f.get(campo):
            payload[campo] = date.today().isoformat()

    # Tornando indietro nel percorso, ripulisci le date dei passi che non
    # sono piu' stati raggiunti: altrimenti la linea temporale mostrerebbe
    # un incasso su una fattura che risulta non ancora inviata.
    if stato in STATI_PERCORSO:
        i = STATI_PERCORSO.index(stato)
        for chiave in STATI_PERCORSO[i + 1:]:
            if chiave in DATE_STATO:
                payload[DATE_STATO[chiave][0]] = None

    try:
        r = sb.table("b2f_fatture").update(payload).eq("id", fid).execute()
        return jsonify(r.data[0] if r.data else {"id": fid})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


def _carica_fattura(sb, fid):
    """Ritorna (fattura, errore_response). L'errore e' gia' pronto da restituire."""
    try:
        r = sb.table("b2f_fatture").select("*").eq("id", fid).single().execute()
        if not r.data:
            return None, (jsonify({"error": "fattura non trovata"}), 404)
        return r.data, None
    except Exception as e:
        return None, (jsonify({"error": f"fattura non trovata: {str(e)[:120]}"}), 404)


@fatture_bp.patch("/api/fatture/<int:fid>")
def api_fattura_update(fid):
    """
    Aggiorna una fattura in bozza.

    La guardia sta qui e non solo nell'interfaccia: nascondere un pulsante
    non impedisce a nessuno di chiamare l'endpoint, e una fattura gia'
    mandata allo studio non deve poter cambiare da nessuna strada.
    """
    sb, err = _supabase_or_error()
    if err:
        return jsonify({"error": "supabase not configured"}), 503

    f, errore = _carica_fattura(sb, fid)
    if errore:
        return errore

    stato = normalizza_stato(f.get("stato"))
    if not modificabile(stato):
        return jsonify({
            "error": motivo_blocco(stato),
            "stato": stato,
            "modificabile": False,
        }), 409

    data = request.get_json(silent=True) or {}
    campi = ("data", "tipo_doc", "natura_iva", "cliente_id", "cliente_snapshot",
             "righe", "imponibile", "bollo", "bollo_addebitato", "cassa_perc",
             "cassa_importo", "totale", "divisa", "pagamento_mod",
             "pagamento_cond", "scadenza", "iban", "note")
    payload = {k: data[k] for k in campi if k in data}
    if not payload:
        return jsonify({"error": "nessun campo da aggiornare"}), 400

    # L'anno segue la data del documento, ma il numero (es. "2026/007") lo
    # incorpora e il progressivo si assegna per anno: cambiare anno senza
    # rifare numero e progressivo lascerebbe un numero che mente sull'anno,
    # con rischio di doppioni contro un'altra fattura gia' numerata cosi'
    # nell'anno nuovo. Piu' semplice e sicuro rifiutare: e' una bozza,
    # costa poco eliminarla e farne una nuova nell'anno giusto.
    if "data" in payload and payload["data"]:
        try:
            anno_nuovo = int(str(payload["data"])[:4])
        except (TypeError, ValueError):
            anno_nuovo = None
        if anno_nuovo is not None and anno_nuovo != f.get("anno"):
            return jsonify({
                "error": (f'La data proposta è del {anno_nuovo}, ma questa bozza è '
                          f'numerata {f.get("numero") or ""} nell\'anno {f.get("anno")}: '
                          f'cambiare anno qui lascerebbe il numero sbagliato. Elimina '
                          f'la bozza e creane una nuova con la data giusta.'),
            }), 409
        payload["anno"] = anno_nuovo

    try:
        r = sb.table("b2f_fatture").update(payload).eq("id", fid).execute()
        return jsonify(r.data[0] if r.data else {"id": fid})
    except Exception as e:
        return jsonify({"error": str(e)[:250]}), 500


@fatture_bp.delete("/api/fatture/<int:fid>")
def api_fattura_delete(fid):
    """
    Elimina una bozza. Le fatture uscite non si cancellano: si annullano,
    cosi' il numero resta occupato e lo storico resta leggibile.
    """
    sb, err = _supabase_or_error()
    if err:
        return jsonify({"error": "supabase not configured"}), 503

    f, errore = _carica_fattura(sb, fid)
    if errore:
        return errore

    stato = normalizza_stato(f.get("stato"))
    if not modificabile(stato):
        return jsonify({
            "error": ("Solo le bozze si eliminano. Questa fattura è già uscita: "
                      "portala su \"Annullata\", così resta nello storico col suo "
                      "numero ma non conta nei calcoli."),
            "stato": stato,
        }), 409

    if f.get("spesa_piva_id"):
        return jsonify({
            "error": ("Questa fattura è collegata a un movimento P.IVA. "
                      "Elimina prima il movimento, altrimenti resterebbe una "
                      "entrata senza fattura."),
        }), 409

    try:
        sb.table("b2f_fatture").delete().eq("id", fid).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.post("/api/fatture/<int:fid>/registra-entrata")
def api_fattura_registra_entrata(fid):
    """
    Crea riga in tabella `b2f_spese_piva` (tipo=entrata) e collega
    spesa_piva_id sulla fattura. Se stato non era gia' incassata/annullata,
    lo porta a incassata con data_incasso = data della spesa.
    """
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503

    try:
        rf = sb.table("b2f_fatture").select("*").eq("id", fid).single().execute()
        f = rf.data or {}
    except Exception as e:
        return jsonify({"error": f"fattura non trovata: {str(e)[:120]}"}), 404
    if f.get("spesa_piva_id"):
        return jsonify({"error": "fattura gia' registrata su spese P.IVA",
                        "spesa_piva_id": f["spesa_piva_id"]}), 409

    body = request.get_json(silent=True) or {}
    riga = {
        "data":        body.get("data") or f.get("data_incasso") or date.today().isoformat(),
        "tipo":        "entrata",
        "importo":     float(body.get("importo") or f.get("totale") or 0),
        "descrizione": body.get("descrizione")
                       or f"Fattura {f.get('numero','')} — {_cliente_label(f)}",
        "categoria":   body.get("categoria") or "fatturato",
        "fattura_id":  fid,
    }
    if body.get("sottocategoria"): riga["sottocategoria"] = body["sottocategoria"]

    try:
        ins = sb.table("b2f_spese_piva").insert(riga).execute()
        spesa_piva_id = (ins.data or [{}])[0].get("id")
        if not spesa_piva_id:
            return jsonify({"error": "insert spese P.IVA senza id di ritorno"}), 500
    except Exception as e:
        return jsonify({"error": f"errore insert spese P.IVA: {str(e)[:200]}"}), 500

    upd = {"spesa_piva_id": spesa_piva_id}
    if f.get("stato") not in ("incassata", "annullata"):
        upd["stato"] = "incassata"
        upd["data_incasso"] = riga["data"]
    try:
        sb.table("b2f_fatture").update(upd).eq("id", fid).execute()
    except Exception as e:
        # rollback manuale della riga spese P.IVA
        try: sb.table("b2f_spese_piva").delete().eq("id", spesa_piva_id).execute()
        except Exception: pass
        return jsonify({"error": f"aggiornamento fattura fallito: {str(e)[:200]}"}), 500

    return jsonify({"ok": True, "spesa_piva_id": spesa_piva_id})


@fatture_bp.post("/api/fatture")
def api_fattura_create():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}

    # Campi obbligatori
    required = ("anno", "progressivo", "data", "tipo_doc",
                "cliente_snapshot", "righe", "totale")
    for k in required:
        if k not in data:
            return jsonify({"error": f"campo mancante: {k}"}), 400

    payload = {
        "anno":              int(data["anno"]),
        "progressivo":       int(data["progressivo"]),
        "data":              data["data"],
        "tipo_doc":          data.get("tipo_doc", "TD01"),
        "natura_iva":        data.get("natura_iva") or "N2.2",
        "cliente_id":        data.get("cliente_id"),
        "cliente_snapshot":  data["cliente_snapshot"],
        "righe":             data["righe"],
        "imponibile":        float(data.get("imponibile") or 0),
        "bollo":             float(data.get("bollo") or 0),
        "bollo_addebitato":  bool(data.get("bollo_addebitato")),
        "cassa_perc":        float(data.get("cassa_perc") or 0),
        "cassa_importo":     float(data.get("cassa_importo") or 0),
        "totale":            float(data["totale"]),
        "divisa":            data.get("divisa") or "EUR",
        "pagamento_mod":     data.get("pagamento_mod"),
        "pagamento_cond":    data.get("pagamento_cond"),
        "scadenza":          data.get("scadenza"),
        "iban":              data.get("iban"),
        # Si nasce bozza: il documento diventa "inviata allo studio" solo
        # quando lo mandi davvero, non nel momento in cui lo salvi.
        "stato":             normalizza_stato(data.get("stato") or "bozza"),
        "note":              data.get("note"),
    }

    try:
        r = sb.table("b2f_fatture").insert(payload).execute()
        return jsonify(r.data[0] if r.data else {})
    except Exception as e:
        return jsonify({"error": str(e)[:250]}), 500


def _render(content: str, eyebrow: str = "Storico",
            title_html: str = 'Le mie <em>fatture</em>',
            breadcrumb=None, fab=None) -> Response:
    html = render_page(
        section="fatture", eyebrow=eyebrow, title_html=title_html,
        content=content, breadcrumb=breadcrumb, fab=fab,
    )
    return Response(html, mimetype="text/html")
