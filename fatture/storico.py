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
from .costanti import CATEGORIE_SPESE_PIVA
from shared.theme import render_page
from shared.design import icon as _icon
from shared.supabase_client import get_client, is_configured
from shared.fmt import eur as _fmt_eur, data_it as _fmt_date


STATO_CHIP = {
    "bozza":      ("",       "Bozza"),
    "emessa":     ("accent", "Emessa"),
    "incassata":  ("pos",    "Incassata"),
    "annullata":  ("neg",    "Annullata"),
}


def cliente_label(f: dict) -> str:
    """Nome leggibile del cliente a partire dallo snapshot della fattura."""
    snap = f.get("cliente_snapshot") or {}
    tipo = snap.get("tipo") or "azienda"
    if tipo == "privato":
        return f'{snap.get("nome","")} {snap.get("cognome","")}'.strip() or "—"
    return snap.get("denominazione") or "—"


# Alias interno storico
_cliente_label = cliente_label


def _stato_chip(stato: str) -> str:
    cls, lbl = STATO_CHIP.get(stato, ("n", stato or "—"))
    return f'<span class="chip {cls}">{lbl}</span>'


def _supabase_or_error():
    if not is_configured():
        return None, ('<div class="notice warn">Supabase non configurato.</div>')
    return get_client(), None


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
    valide = [x for x in rows if x.get("stato") in ("emessa", "incassata")]
    tot_fatturato = sum(float(x.get("totale") or 0) for x in valide)
    tot_incassato = sum(float(x.get("totale") or 0) for x in rows
                        if x.get("stato") == "incassata")
    da_incassare = round(tot_fatturato - tot_incassato, 2)

    # Toolbar
    stato_opts = "".join(
        f'<option value="{k}"{" selected" if stato == k else ""}>{lbl}</option>'
        for k, (_, lbl) in STATO_CHIP.items()
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
            stato = f.get("stato")
            incasso = (f' · incassata il {_fmt_date(f.get("data_incasso"))}'
                       if stato == "incassata" and f.get("data_incasso") else "")
            items.append(f'''
            <a class="item" href="/fatture/{f["id"]}">
              <span class="body">
                <span class="n">{f.get("numero", "—")} · {cliente_label(f)}</span>
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
          <span class="k">{r.get("qta", 1)}{" " + r.get("um") if r.get("um") else ""}</span>
          <span class="t">{(r.get("descrizione") or "").strip() or "—"}
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
        "imponibile":     float(f.get("imponibile") or 0),
        "cassa_perc":     float(f.get("cassa_perc") or 0),
        "cassa_importo":  float(f.get("cassa_importo") or 0),
        "bollo_add":      bool(f.get("bollo_addebitato")),
        "bollo_dovuto":   float(f.get("imponibile") or 0) > 77.47,
        "totale":         float(f.get("totale") or 0),
        "pagamento_mod":  f.get("pagamento_mod") or "Bonifico bancario",
        "scadenza":       f.get("scadenza"),
    }, ensure_ascii=False)

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

    # Descrizione precompilata per la riga spese
    desc_precompilata = f"Fattura {f.get('numero','')} — {_cliente_label(f)}"

    stato_corrente = f.get("stato") or "emessa"

    cat_options = "".join(
        f'<option value="{k}"{" selected" if k=="fatturato" else ""}>{lbl}</option>'
        for k, lbl in CATEGORIE_SPESE_PIVA
    )

    # --- Accantonamento -----------------------------------------------------
    # Il momento in cui questo numero serve e' l'incasso: fino ad allora e'
    # una previsione, e va detto.
    acc_card = ""
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

        if stato_corrente in ("emessa", "incassata"):
            scomposizione = acc.scomponi(f.get("totale"), param,
                                         fatturato_riferimento=incassato_anno)
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

    cassa_riga = ""
    if float(f.get("cassa_importo") or 0) > 0:
        perc = f'{float(f.get("cassa_perc") or 0):g}'.replace(".", ",")
        cassa_riga = (f'<div class="row"><span class="t">Cassa previdenziale '
                      f'{perc} %</span>'
                      f'<span class="v tnum">€ {_fmt_eur(f.get("cassa_importo"))}</span></div>')
    bollo_riga = ""
    if float(f.get("bollo") or 0) > 0:
        addeb = "addebitato" if f.get("bollo_addebitato") else "a tuo carico"
        bollo_riga = (f'<div class="row"><span class="t">Bollo <span class="sub">{addeb}</span></span>'
                      f'<span class="v tnum">€ {_fmt_eur(f.get("bollo"))}</span></div>')

    pagamento = " · ".join(x for x in [
        f.get("pagamento_mod"), f.get("pagamento_cond"),
        f'scadenza {_fmt_date(f.get("scadenza"))}' if f.get("scadenza") else None,
    ] if x)

    body = f'''
    <div class="grid split">
      <div class="stack">

        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Riepilogo</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              {_stato_chip(stato_corrente)}{registrata_chip}
            </div>
          </div>
          <div class="stat">
            <div class="val tnum accent">€ {_fmt_eur(f.get("totale"))}</div>
            <div class="lbl">{f.get("numero", "—")} · {_fmt_date(f.get("data"))}</div>
          </div>
          <div class="rows detail mt-4">
            <div class="row"><span class="t">Imponibile</span>
              <span class="v tnum">€ {_fmt_eur(f.get("imponibile"))}</span></div>
            {cassa_riga}{bollo_riga}
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Righe</div></div>
          <div class="rows detail">{righe_html}</div>
        </div>

        {acc_card}
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Cliente</div></div>
          <div class="h3">{cliente_label(f)}</div>
          <div class="small muted mt-2">
            {(snap.get("piva") or snap.get("cf") or "—")}
            {" · " + snap.get("comune", "") if snap.get("comune") else ""}
          </div>
          {f'<div class="small muted mt-2">{pagamento}</div>' if pagamento else ""}
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Azioni</div></div>
          <div class="actions col mt-0">
            <button type="button" class="btn" onclick="onRistampa()">
              {_icon("download")}Scarica PDF
            </button>
            <button type="button" class="btn ghost" onclick="openModal('modalStato')">
              Cambia stato
            </button>
            <button type="button" class="btn ghost" id="btnRegistra"
                    style="display:{btn_registra_display}" onclick="openModal('modalEntrata')">
              Registra entrata su P.IVA
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== Foglio cambio stato ===== -->
    <div class="sheet-ov" id="modalStato" role="dialog" aria-modal="true">
      <div class="sheet">
        <h3>Cambia stato</h3>
        <div class="sheet-sub">Stato attuale: <strong>{STATO_CHIP.get(stato_corrente, ("", stato_corrente))[1]}</strong></div>
        <div class="field">
          <label>Nuovo stato</label>
          <select id="statoSel" onchange="onStatoChange()">
            <option value="bozza"     {" selected" if stato_corrente == "bozza" else ""}>Bozza</option>
            <option value="emessa"    {" selected" if stato_corrente == "emessa" else ""}>Emessa</option>
            <option value="incassata" {" selected" if stato_corrente == "incassata" else ""}>Incassata</option>
            <option value="annullata" {" selected" if stato_corrente == "annullata" else ""}>Annullata</option>
          </select>
        </div>
        <div class="field" id="fldDataIncasso"
             style="display:{'flex' if stato_corrente == 'incassata' else 'none'}">
          <label>Data incasso</label>
          <input type="date" id="dataIncasso" value="{data_incasso_default}">
        </div>
        <div class="notice info small" id="statoAccHint"
             style="display:{'block' if stato_corrente == 'incassata' else 'none'}">
          Segnandola incassata, l'importo entra nel calcolo dell'accantonamento
          del mese.
        </div>
        <div class="actions">
          <button type="button" class="btn ghost" data-close="modalStato">Annulla</button>
          <button type="button" class="btn" onclick="onSalvaStato()">Salva</button>
        </div>
      </div>
    </div>

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

      // --- cambio stato ---
      function onStatoChange() {{
        const v = document.getElementById('statoSel').value;
        const incassata = (v === 'incassata');
        document.getElementById('fldDataIncasso').style.display = incassata ? 'flex' : 'none';
        document.getElementById('statoAccHint').style.display = incassata ? 'block' : 'none';
      }}
      async function onSalvaStato() {{
        const nuovo = document.getElementById('statoSel').value;
        const body = {{stato: nuovo}};
        if (nuovo === 'incassata') {{
          body.data_incasso = document.getElementById('dataIncasso').value;
        }}
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
    """Cambia stato fattura. Se stato=incassata richiede/genera data_incasso."""
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    stato = data.get("stato")
    if stato not in ("bozza", "emessa", "incassata", "annullata"):
        return jsonify({"error": "stato non valido"}), 400
    payload = {"stato": stato}
    if stato == "incassata":
        payload["data_incasso"] = data.get("data_incasso") or date.today().isoformat()
    else:
        payload["data_incasso"] = None
    try:
        r = sb.table("b2f_fatture").update(payload).eq("id", fid).execute()
        return jsonify(r.data[0] if r.data else {"id": fid})
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
        "stato":             data.get("stato") or "emessa",
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
