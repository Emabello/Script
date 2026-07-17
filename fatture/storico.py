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
from .costanti import CATEGORIE_SPESE_PIVA
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured


STATO_CHIP = {
    "bozza":      ("n", "Bozza"),
    "emessa":     ("",  "Emessa"),
    "incassata":  ("g", "Incassata"),
    "annullata":  ("r", "Annullata"),
}


def _fmt_eur(v) -> str:
    try: v = float(v or 0)
    except Exception: v = 0.0
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_date(iso: str | None) -> str:
    if not iso: return ""
    try:
        y, m, d = iso[:10].split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso[:10]


def _cliente_label(f: dict) -> str:
    snap = f.get("cliente_snapshot") or {}
    tipo = snap.get("tipo") or "azienda"
    if tipo == "privato":
        return f'{snap.get("nome","")} {snap.get("cognome","")}'.strip() or "—"
    return snap.get("denominazione") or "—"


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
    tot_imp = sum(float(x.get("imponibile") or 0) for x in rows
                  if x.get("stato") in ("emessa", "incassata"))

    # Toolbar
    stato_opts = "".join(
        f'<option value="{k}"{" selected" if stato==k else ""}>{lbl}</option>'
        for k, (_, lbl) in STATO_CHIP.items()
    )
    toolbar = f'''
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <select onchange="location.href='/fatture/storico?anno='+this.value{("+'&stato={}'".format(stato)) if stato else ""}"
              style="padding:10px 14px;border-radius:999px;
                     background:var(--input-bg);border:1px solid var(--line-strong);
                     color:var(--ink);font-size:14px">
        {"".join(f'<option value="{y}"{" selected" if y==anno else ""}>{y}</option>' for y in range(anno_default, anno_default-6, -1))}
      </select>
      <select onchange="const u=new URL(location.href);if(this.value){{u.searchParams.set('stato',this.value)}}else{{u.searchParams.delete('stato')}};location.href=u"
              style="padding:10px 14px;border-radius:999px;
                     background:var(--input-bg);border:1px solid var(--line-strong);
                     color:var(--ink);font-size:14px">
        <option value="">Tutti gli stati</option>
        {stato_opts}
      </select>
    </div>
    '''

    riepilogo = f'''
    <div class="card">
      <div class="eyebrow" style="margin-bottom:6px">Anno {anno}</div>
      <div class="stat">
        <div class="num tnum">€ {_fmt_eur(tot_imp)}</div>
        <div class="lbl">Imponibile</div>
      </div>
      <div style="color:var(--muted);font-size:13px;margin-top:8px">
        {len(rows)} document{"o" if len(rows)==1 else "i"} totali
      </div>
    </div>
    '''

    if not rows:
        body = f'''{riepilogo}
        {toolbar}
        <div class="empty">
          <svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v4h5"/></svg>
          <div class="t">Nessuna fattura per il {anno}</div>
          <div class="s">Crea la prima con il pulsante in basso.</div>
        </div>'''
    else:
        items = []
        for f in rows:
            items.append(f'''
            <a class="item" href="/fatture/{f["id"]}">
              <div class="info">
                <div class="n">{f.get("numero","—")} · {_cliente_label(f)}</div>
                <div class="m">{_fmt_date(f.get("data"))} · <span class="tnum">€ {_fmt_eur(f.get("totale"))}</span></div>
              </div>
              <div class="end">{_stato_chip(f.get("stato"))}</div>
            </a>''')
        body = f'{riepilogo}{toolbar}<div class="list">{"".join(items)}</div>'

    return _render(body,
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
          <div class="d">×{r.get("qta",1)}{" "+r.get("um") if r.get("um") else ""}</div>
          <div class="t">{(r.get("descrizione") or "").strip() or "—"}</div>
          <div class="a tnum">€ {_fmt_eur((r.get("qta") or 0) * (r.get("prezzo") or 0))}</div>
        </div>''' for r in righe
    )
    if not righe_html:
        righe_html = '<div class="row"><div class="t" style="color:var(--muted)">Nessuna riga</div></div>'

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
        registrata_chip = (
            f'<span class="chip g" style="margin-left:6px">'
            f'Registrata su spese P.IVA</span>'
        )

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

    body = f'''
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <div class="eyebrow" style="margin-bottom:4px">Fattura</div>
          <h2 class="serif" style="margin:0;font-size:24px">{f.get("numero","—")}</h2>
          <div style="color:var(--muted);font-size:13px;margin-top:3px">
            {_fmt_date(f.get("data"))}
          </div>
        </div>
        <div style="text-align:right">
          {_stato_chip(stato_corrente)}
          {registrata_chip}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="eyebrow" style="margin-bottom:6px">Cliente</div>
      <div style="font-size:15px;font-weight:500">{_cliente_label(f)}</div>
      <div style="color:var(--muted);font-size:12.5px;margin-top:4px">
        {(snap.get("piva") or snap.get("cf") or "—")}
        {" · " + snap.get("comune","") if snap.get("comune") else ""}
      </div>
    </div>

    <div class="card">
      <div class="eyebrow" style="margin-bottom:10px">Righe</div>
      <div class="rows">{righe_html}</div>
    </div>

    <div class="card">
      <div style="display:flex;justify-content:space-between;font-size:13.5px;margin:4px 0">
        <span style="color:var(--muted)">Imponibile</span>
        <span class="tnum">€ {_fmt_eur(f.get("imponibile"))}</span>
      </div>
      {f'''<div style="display:flex;justify-content:space-between;font-size:13.5px;margin:4px 0">
        <span style="color:var(--muted)">Cassa {f.get("cassa_perc") or 0}%</span>
        <span class="tnum">€ {_fmt_eur(f.get("cassa_importo"))}</span>
      </div>''' if float(f.get("cassa_importo") or 0) > 0 else ""}
      {f'''<div style="display:flex;justify-content:space-between;font-size:13.5px;margin:4px 0">
        <span style="color:var(--muted)">Bollo</span>
        <span class="tnum">€ {_fmt_eur(f.get("bollo"))}</span>
      </div>''' if float(f.get("bollo") or 0) > 0 else ""}
      <div style="display:flex;justify-content:space-between;margin-top:10px;
                  padding-top:10px;border-top:1px solid var(--line);font-size:16px;font-weight:600">
        <span>Totale</span>
        <span class="tnum" style="color:var(--gold)">€ {_fmt_eur(f.get("totale"))}</span>
      </div>
    </div>

    <div class="actions" style="margin-top:14px;flex-direction:column">
      <button type="button" class="btn" onclick="onRistampa()">
        <svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round">
          <path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>
        Scarica PDF
      </button>
      <button type="button" class="btn ghost" onclick="openStatoModal()">
        Cambia stato
      </button>
      <button type="button" class="btn ghost" id="btnRegistra"
              style="display:{btn_registra_display}" onclick="openEntrataModal()">
        Registra come entrata su spese P.IVA
      </button>
    </div>

    <!-- ===== Modal cambio stato ===== -->
    <div class="modal-ov" id="modalStato" style="display:none">
      <div class="modal-card">
        <h3 class="serif" style="margin:0 0 4px">Cambia stato</h3>
        <p style="color:var(--muted);font-size:13px;margin:0 0 16px">
          Stato attuale: <strong>{stato_corrente}</strong>
        </p>
        <div class="field">
          <label>Nuovo stato</label>
          <select id="statoSel" onchange="onStatoChange()">
            <option value="bozza"      {" selected" if stato_corrente=="bozza" else ""}>Bozza</option>
            <option value="emessa"     {" selected" if stato_corrente=="emessa" else ""}>Emessa</option>
            <option value="incassata"  {" selected" if stato_corrente=="incassata" else ""}>Incassata</option>
            <option value="annullata"  {" selected" if stato_corrente=="annullata" else ""}>Annullata</option>
          </select>
        </div>
        <div class="field" id="fldDataIncasso"
             style="display:{'block' if stato_corrente=='incassata' else 'none'}">
          <label>Data incasso</label>
          <input type="date" id="dataIncasso" value="{data_incasso_default}">
        </div>
        <div class="actions" style="margin-top:8px">
          <button type="button" class="btn ghost" onclick="closeModal('modalStato')">Annulla</button>
          <button type="button" class="btn" onclick="onSalvaStato()">Salva</button>
        </div>
      </div>
    </div>

    <!-- ===== Modal registra entrata ===== -->
    <div class="modal-ov" id="modalEntrata" style="display:none">
      <div class="modal-card">
        <h3 class="serif" style="margin:0 0 4px">Registra come entrata su spese P.IVA</h3>
        <p style="color:var(--muted);font-size:13px;margin:0 0 16px">
          Crea una riga <code>tipo=entrata</code> nella tabella spese P.IVA e collega
          la fattura. Aggiorna anche lo stato a "incassata".
        </p>
        <div class="field">
          <label>Data</label>
          <input type="date" id="e_data" value="{data_incasso_default}">
        </div>
        <div class="field">
          <label>Descrizione</label>
          <input id="e_desc" value="{desc_precompilata}">
        </div>
        <div class="field">
          <label>Importo (€)</label>
          <input type="number" step="0.01" id="e_imp" value="{f.get('totale') or 0}">
        </div>
        <div class="field-group">
          <div class="field"><label>Categoria</label>
            <select id="e_cat">{cat_options}</select></div>
          <div class="field"><label>Sottocategoria (opz.)</label>
            <input id="e_scat"></div>
        </div>
        <div class="actions" style="margin-top:8px">
          <button type="button" class="btn ghost" onclick="closeModal('modalEntrata')">Annulla</button>
          <button type="button" class="btn" onclick="onSalvaEntrata()">Registra</button>
        </div>
      </div>
    </div>

    <style>
      .modal-ov{{position:fixed;inset:0;z-index:500;background:rgba(11,12,16,.75);
        backdrop-filter:blur(6px);display:flex;align-items:flex-end;justify-content:center;
        padding:0}}
      html[data-theme="light"] .modal-ov{{background:rgba(238,240,245,.86)}}
      .modal-card{{width:100%;max-width:560px;background:var(--card-grad);
        border:1px solid var(--line-strong);border-radius:20px 20px 0 0;
        padding:22px 22px calc(22px + env(safe-area-inset-bottom,0px));
        box-shadow:var(--shadow);max-height:88vh;overflow-y:auto}}
      @media (min-width:640px){{
        .modal-ov{{align-items:center;padding:20px}}
        .modal-card{{border-radius:20px}}
      }}
    </style>

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
      function openModal(id) {{ document.getElementById(id).style.display = 'flex'; }}
      function closeModal(id) {{ document.getElementById(id).style.display = 'none'; }}

      // --- cambio stato ---
      function openStatoModal() {{ openModal('modalStato'); }}
      function onStatoChange() {{
        const v = document.getElementById('statoSel').value;
        document.getElementById('fldDataIncasso').style.display = (v==='incassata' ? 'block' : 'none');
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
      function openEntrataModal() {{ openModal('modalEntrata'); }}
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
