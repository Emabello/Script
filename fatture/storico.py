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

    body = f'''
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <div>
          <div class="eyebrow" style="margin-bottom:4px">Fattura</div>
          <h2 class="serif" style="margin:0;font-size:24px">{f.get("numero","—")}</h2>
          <div style="color:var(--muted);font-size:13px;margin-top:3px">
            {_fmt_date(f.get("data"))}
          </div>
        </div>
        {_stato_chip(f.get("stato"))}
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

    <div class="actions" style="margin-top:14px">
      <button type="button" class="btn" onclick="onRistampa()">
        <svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round">
          <path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>
        Scarica PDF
      </button>
    </div>

    {pdf_js}
    <script>
      const FATTURA_PAYLOAD = {payload_js};
      function onRistampa() {{
        if (!window.b2fRenderInvoicePDF) {{
          alert('Rendering PDF non pronto'); return;
        }}
        window.b2fRenderInvoicePDF(FATTURA_PAYLOAD);
      }}
    </script>

    <div class="notice" style="margin-top:14px">
      Altre azioni (cambia stato, registra incasso su spese) arriveranno nel Blocco B.
    </div>
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
