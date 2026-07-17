"""
fatture/fiscale.py — Blocco C: gestione fiscale (dashboard, spese P.IVA,
parametri, export Excel).

Rotte HTML:
  GET /fatture/situazione            -> dashboard fiscale (riepilogo + scadenze)
  GET /fatture/spese-piva            -> lista movimenti P.IVA
  GET /fatture/spese-piva/nuova      -> form nuovo movimento
  GET /fatture/spese-piva/<int:id>   -> form edit movimento
  GET /fatture/parametri             -> editor parametri fiscali

Rotte JSON:
  GET    /fatture/api/situazione?anno=YYYY
  GET    /fatture/api/export/xlsx?anno=YYYY
  GET    /fatture/api/parametri
  PATCH  /fatture/api/parametri
  GET    /fatture/api/spese-piva
  POST   /fatture/api/spese-piva
  PATCH  /fatture/api/spese-piva/<int:id>
  DELETE /fatture/api/spese-piva/<int:id>

Logica di calcolo verificata sul file di riferimento fornito dall'utente
(Situazione_forfait_Bertoli_Andrea.xlsx, fogli "2026" e "Template"):
  - l'acconto all'80% ("metodo storico") si applica SOLO all'INPS gestione
    separata. L'acconto dell'imposta sostitutiva e' pari al 100% del saldo
    (nessuna riduzione).
  - Scadenza 30/06/anno+1: saldo imposta + saldo INPS + commercialista
    dell'anno + bollo dell'anno.
  - Scadenza 30/11/anno+1: acconto imposta (=saldo, 100%) + acconto INPS
    (=saldo INPS * 80%).
"""
import io
from datetime import date

from flask import Response, request, jsonify, send_file

from . import fatture_bp
from .costanti import CATEGORIE_SPESE_PIVA, MESI_NOMI
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured


PARAMETRI_DEFAULT = {
    "id": 1, "regime": "RF19", "ateco": "622010",
    "ateco_descrizione": "Attività di consulenza informatica",
    "coeff_ateco": 0.67, "aliquota_imposta": 0.05, "aliquota_inps": 0.2607,
    "aliquota_acconto": 0.80, "bollo_soglia": 77.47, "bollo_importo": 2.00,
    "limite_fatturato_anno": 85000, "data_apertura_piva": "2026-05-28",
    "anno_fine_regime_agevolato": 2031,
}

PARAMETRI_CAMPI = (
    "regime", "coeff_ateco", "aliquota_imposta", "aliquota_inps",
    "aliquota_acconto", "bollo_soglia", "bollo_importo",
    "limite_fatturato_anno", "data_apertura_piva", "anno_fine_regime_agevolato",
)

MOVIMENTO_CAMPI = (
    "data", "importo", "tipo", "descrizione", "categoria",
    "sottocategoria", "fattura_id", "ricorrente", "note",
)


def _supabase_or_error():
    if not is_configured():
        return None, ('<div class="notice warn">Supabase non configurato.</div>')
    return get_client(), None


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


# ---------------------------------------------------------------------------
# Calcolo situazione fiscale
# ---------------------------------------------------------------------------

def _get_parametri(sb) -> dict:
    try:
        r = sb.table("b2f_parametri_fiscali").select("*").eq("id", 1).single().execute()
        if r.data:
            return {**PARAMETRI_DEFAULT, **r.data}
    except Exception:
        pass
    return dict(PARAMETRI_DEFAULT)


def _mesi_attivita(anno: int, data_apertura_iso: str) -> int:
    """Mesi ragguagliati di attivita' nell'anno indicato.

    Regola: se il giorno di apertura e' successivo al 15, il mese di
    apertura non conta ai fini del ragguaglio (coerente con la regola
    Agenzia Entrate per il calcolo del limite forfettario).
    """
    try:
        y, m, d = (int(x) for x in data_apertura_iso[:10].split("-"))
    except Exception:
        return 12
    if anno < y:
        return 0
    if anno > y:
        return 12
    mese_apertura = m + 1 if d > 15 else m
    return max(12 - mese_apertura + 1, 0)


def _situazione_data(sb, anno: int) -> dict:
    param = _get_parametri(sb)
    coeff = float(param["coeff_ateco"])
    aliq_imp = float(param["aliquota_imposta"])
    aliq_inps = float(param["aliquota_inps"])
    aliq_acc = float(param["aliquota_acconto"])
    limite_anno = float(param["limite_fatturato_anno"])

    fatturato_mese = {m: 0.0 for m in range(1, 13)}
    bollo_mese = {m: 0.0 for m in range(1, 13)}
    incasso_mese = {m: 0.0 for m in range(1, 13)}
    commercialista_mese = {m: 0.0 for m in range(1, 13)}
    spese_piva_uscite_tot = 0.0

    try:
        r = (sb.table("b2f_fatture")
               .select("data,data_incasso,totale,bollo,bollo_addebitato,stato")
               .gte("data", f"{anno}-01-01").lte("data", f"{anno}-12-31")
               .in_("stato", ["emessa", "incassata"]).execute())
        for f in (r.data or []):
            mese = int(f["data"][5:7])
            fatturato_mese[mese] += float(f.get("totale") or 0)
            if f.get("bollo_addebitato"):
                bollo_mese[mese] += float(f.get("bollo") or 0)
    except Exception:
        pass

    try:
        r = (sb.table("b2f_fatture").select("data_incasso,totale")
               .eq("stato", "incassata")
               .gte("data_incasso", f"{anno}-01-01").lte("data_incasso", f"{anno}-12-31")
               .execute())
        for f in (r.data or []):
            if not f.get("data_incasso"):
                continue
            mese = int(f["data_incasso"][5:7])
            incasso_mese[mese] += float(f.get("totale") or 0)
    except Exception:
        pass

    try:
        r = (sb.table("b2f_spese_piva").select("data,importo,categoria,tipo")
               .eq("tipo", "uscita")
               .gte("data", f"{anno}-01-01").lte("data", f"{anno}-12-31")
               .execute())
        for s in (r.data or []):
            spese_piva_uscite_tot += float(s.get("importo") or 0)
            if s.get("categoria") == "commercialista":
                mese = int(s["data"][5:7])
                commercialista_mese[mese] += float(s.get("importo") or 0)
    except Exception:
        pass

    mensile = []
    tot = {k: 0.0 for k in ("fatturato", "imponibile", "incasso", "imposta",
                             "inps_saldo", "inps_acconto", "bollo", "commercialista")}
    for m in range(1, 13):
        fatt = fatturato_mese[m]
        imponibile = round(fatt * coeff, 2)
        imposta = round(imponibile * aliq_imp, 2)
        inps_saldo = round(imponibile * aliq_inps, 2)
        inps_acconto = round(inps_saldo * aliq_acc, 2)
        incasso = incasso_mese[m]
        bollo = bollo_mese[m]
        comm = commercialista_mese[m]
        netto = round(incasso - imposta - inps_saldo - inps_acconto - bollo - comm, 2)
        mensile.append({
            "mese": m, "nome": MESI_NOMI[m - 1],
            "fatturato": fatt, "imponibile": imponibile, "incasso": incasso,
            "imposta": imposta, "inps_saldo": inps_saldo, "inps_acconto": inps_acconto,
            "bollo": bollo, "commercialista": comm, "netto": netto,
        })
        tot["fatturato"] += fatt
        tot["imponibile"] += imponibile
        tot["incasso"] += incasso
        tot["imposta"] += imposta
        tot["inps_saldo"] += inps_saldo
        tot["inps_acconto"] += inps_acconto
        tot["bollo"] += bollo
        tot["commercialista"] += comm

    for k in tot:
        tot[k] = round(tot[k], 2)

    totale_da_versare = round(tot["imposta"] + tot["inps_saldo"] + tot["inps_acconto"], 2)
    netto_stimato = round(tot["incasso"] - tot["imposta"] - tot["inps_saldo"]
                          - tot["inps_acconto"] - tot["bollo"] - tot["commercialista"], 2)

    mesi_attivita = _mesi_attivita(anno, param["data_apertura_piva"])
    limite_ragguagliato = round(limite_anno / 12 * mesi_attivita, 2)

    scadenza_giugno = round(tot["imposta"] + tot["inps_saldo"]
                            + tot["commercialista"] + tot["bollo"], 2)
    scadenza_novembre = round(tot["imposta"] + tot["inps_acconto"], 2)

    return {
        "anno": anno,
        "parametri": param,
        "limite_ragguagliato": limite_ragguagliato,
        "mesi_attivita": mesi_attivita,
        "totali": {
            "fatturato": tot["fatturato"],
            "imponibile": tot["imponibile"],
            "incasso": tot["incasso"],
            "imposta_accantonata": tot["imposta"],
            "inps_saldo_accantonato": tot["inps_saldo"],
            "inps_acconto_accantonato": tot["inps_acconto"],
            "bollo_totale": tot["bollo"],
            "commercialista_totale": tot["commercialista"],
            "totale_da_versare": totale_da_versare,
            "spese_piva_totali": round(spese_piva_uscite_tot, 2),
            "netto_stimato": netto_stimato,
        },
        "mensile": mensile,
        "scadenze": [
            {"data": f"{anno + 1}-06-30",
             "descrizione": "Saldo imposta + saldo INPS + commercialista + bollo",
             "importo": scadenza_giugno},
            {"data": f"{anno + 1}-11-30",
             "descrizione": "Acconto imposta + acconto INPS",
             "importo": scadenza_novembre},
        ],
    }


# ---------------------------------------------------------------------------
# Dashboard /fatture/situazione
# ---------------------------------------------------------------------------

@fatture_bp.get("/situazione")
def situazione_dashboard():
    sb, err = _supabase_or_error()
    breadcrumb = [("Fatture", "/fatture"), ("Situazione fiscale", "")]
    if err:
        return _render(err, breadcrumb=breadcrumb)

    anno_default = date.today().year
    anno = request.args.get("anno", type=int) or anno_default

    try:
        s = _situazione_data(sb, anno)
    except Exception as e:
        return _render(f'<div class="notice err">Errore: {str(e)[:200]}</div>',
                       breadcrumb=breadcrumb)

    t = s["totali"]
    pct_limite = 0.0
    if s["limite_ragguagliato"] > 0:
        pct_limite = min(t["fatturato"] / s["limite_ragguagliato"] * 100, 100)

    anno_opts = "".join(
        f'<option value="{y}"{" selected" if y == anno else ""}>{y}</option>'
        for y in range(anno_default + 1, anno_default - 5, -1)
    )

    scadenze_html = "".join(f'''
    <div class="row">
      <div class="d">{_fmt_date(sc["data"])}</div>
      <div class="t">{sc["descrizione"]}</div>
      <div class="a tnum">€ {_fmt_eur(sc["importo"])}</div>
    </div>''' for sc in s["scadenze"])

    mensile_rows = "".join(f'''
    <div class="row">
      <div class="d">{m["nome"][:3]}</div>
      <div class="t">Fatt. € {_fmt_eur(m["fatturato"])}</div>
      <div class="a tnum {'pos' if m['netto'] > 0 else ''}">€ {_fmt_eur(m["netto"])}</div>
    </div>''' for m in s["mensile"])

    body = f'''
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div class="eyebrow">Anno</div>
        <select onchange="location.href='/fatture/situazione?anno='+this.value"
                style="padding:8px 14px;border-radius:999px;
                       background:var(--input-bg);border:1px solid var(--line-strong);
                       color:var(--ink);font-size:14px">
          {anno_opts}
        </select>
      </div>
      <div class="grid2">
        <div class="card"><div class="num tnum">€ {_fmt_eur(t["fatturato"])}</div>
          <div class="lbl">Fatturato</div></div>
        <div class="card"><div class="num tnum">€ {_fmt_eur(t["imponibile"])}</div>
          <div class="lbl">Imponibile</div></div>
      </div>
      <div class="card" style="margin-top:10px">
        <div class="num tnum">€ {_fmt_eur(t["totale_da_versare"])}</div>
        <div class="lbl">Da versare (imposta + INPS)</div>
      </div>
      <div style="margin-top:14px">
        <div style="height:8px;border-radius:999px;background:var(--input-bg);overflow:hidden">
          <div style="height:100%;width:{pct_limite:.1f}%;background:var(--gold);border-radius:999px"></div>
        </div>
        <div style="color:var(--muted);font-size:12.5px;margin-top:6px">
          {pct_limite:.1f}% del limite ragguagliato (€ {_fmt_eur(s["limite_ragguagliato"])}
          · {s["mesi_attivita"]} mesi di attività)
        </div>
      </div>
    </div>

    <div class="card">
      <div class="eyebrow" style="margin-bottom:10px">Scadenze</div>
      <div class="rows">{scadenze_html}</div>
    </div>

    <div class="card">
      <div class="eyebrow" style="margin-bottom:10px">Riepilogo mensile</div>
      <div class="rows">{mensile_rows}</div>
    </div>

    <div class="actions" style="flex-direction:column">
      <a class="btn" href="/fatture/api/export/xlsx?anno={anno}">
        <svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round">
          <path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>
        Esporta Excel
      </a>
      <div class="actions" style="margin-top:0">
        <a class="btn ghost" href="/fatture/parametri">Parametri</a>
        <a class="btn ghost" href="/fatture/spese-piva">Spese P.IVA</a>
      </div>
    </div>
    '''

    return _render(body, eyebrow="Situazione fiscale",
                   title_html='Situazione <em>fiscale</em>', breadcrumb=breadcrumb)


@fatture_bp.get("/api/situazione")
def api_situazione():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    anno = request.args.get("anno", type=int) or date.today().year
    try:
        return jsonify(_situazione_data(sb, anno))
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# ---------------------------------------------------------------------------
# Export Excel
# ---------------------------------------------------------------------------

def _build_workbook(sb, anno: int):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

    s = _situazione_data(sb, anno)
    param = s["parametri"]

    try:
        r = sb.table("b2f_emittente").select("*").eq("id", 1).single().execute()
        em = r.data or {}
    except Exception:
        em = {}
    nome = f'{em.get("nome","") or ""} {em.get("cognome","") or ""}'.strip() or "—"

    FONT = "Georgia"
    money_fmt = '#,##0.00" €"'
    pct_fmt = "0.00%"
    thin = Side(style="thin")
    input_fill = PatternFill("solid", fgColor="FFFFF2CC")

    wb = Workbook()
    ws = wb.active
    ws.title = str(anno)
    ws.sheet_view.showGridLines = False

    def cell(coord, value, bold=False, fmt=None, fill=None, border=None, size=11):
        c = ws[coord]
        c.value = value
        c.font = Font(name=FONT, bold=bold, size=size)
        if fmt: c.number_format = fmt
        if fill: c.fill = fill
        if border: c.border = border
        return c

    # --- Header (righe 1-5) ---
    cell("A1", nome, bold=True)
    cell("A2", param.get("ateco_descrizione") or "")
    cell("A3", f'CODICE ATECO {param.get("ateco","")}')

    cell("E1", "Commercialista", bold=True)
    cell("F1", anno, bold=True)
    cell("G1", round(s["totali"]["commercialista_totale"], 2), fmt=money_fmt)
    cell("H1", "Regime", bold=True)
    cell("I1", float(param["limite_fatturato_anno"]), fmt=money_fmt)
    cell("J1", 12)

    cell("E2", "Bollo Fatture >", bold=True)
    cell("F2", float(param["bollo_soglia"]), fmt=money_fmt)
    cell("G2", float(param["bollo_importo"]), fmt=money_fmt)
    cell("H2", "Attività", bold=True)
    cell("I2", "=I1/J1*J2", fmt=money_fmt)
    cell("J2", s["mesi_attivita"])

    cell("H3", "Residuo limite", bold=True)
    cell("I3", "=I2-SUM(B7:B18)", fmt=money_fmt)

    cell("D4", "COEFFICIENTE", bold=True)
    cell("E4", "Aliquota", bold=True)
    cell("F4", "INPS", bold=True)
    cell("G4", "Acconto", bold=True)

    ws.merge_cells("A5:C5")
    aliq_imp_pct = int(round(float(param["aliquota_imposta"]) * 100))
    cell("A5", f"ALIQUOTA {aliq_imp_pct}% PER I PRIMI 5 ANNI", bold=True)
    cell("D5", float(param["coeff_ateco"]), fmt="0%")
    cell("E5", float(param["aliquota_imposta"]), fmt="0%")
    cell("F5", float(param["aliquota_inps"]), fmt=pct_fmt)
    cell("G5", float(param["aliquota_acconto"]), fmt="0%")

    # --- Riga 6: intestazioni tabella ---
    headers = ["Mese", "Fatturato", "Imponibile", "Incasso", "Imposta",
               "INPS Saldo", "INPS Acconto", "Bollo Fattura", "Commercialista", "Stipendio"]
    header_border = Border(bottom=thin)
    for i, h in enumerate(headers):
        col = chr(ord("A") + i)
        cell(f"{col}6", h, bold=True, border=header_border)

    # --- Righe 7-18: 12 mesi ---
    for i, m in enumerate(s["mensile"]):
        r = 7 + i
        cell(f"A{r}", m["nome"])
        cell(f"B{r}", m["fatturato"], fmt=money_fmt, fill=input_fill)
        cell(f"C{r}", f"=B{r}*$D$5", fmt=money_fmt)
        cell(f"D{r}", m["incasso"], fmt=money_fmt, fill=input_fill)
        cell(f"E{r}", f"=C{r}*$E$5", fmt=money_fmt)
        cell(f"F{r}", f"=C{r}*$F$5", fmt=money_fmt)
        cell(f"G{r}", f"=F{r}*$G$5", fmt=money_fmt)
        cell(f"H{r}", m["bollo"], fmt=money_fmt, fill=input_fill)
        cell(f"I{r}", m["commercialista"], fmt=money_fmt, fill=input_fill)
        cell(f"J{r}", f"=D{r}-E{r}-F{r}-G{r}-H{r}-I{r}", fmt=money_fmt)

    # --- Riga 19: Totale ---
    top_border = Border(top=thin, bottom=Side(style="double"))
    for col in "BCDEFGHIJ":
        cell(f"{col}19", f"=SUM({col}7:{col}18)", bold=True, fmt=money_fmt, border=top_border)
    cell("A19", "Totale", bold=True, border=top_border)

    # --- Righe 21-26: Scadenze ---
    box = Border(top=thin, bottom=thin, left=thin, right=thin)
    cell("A21", "Scadenze", bold=True)
    cell("B21", f"Giugno {anno + 1}", bold=True)
    cell("C21", f"Novembre {anno + 1}", bold=True)
    cell("D21", "Totale", bold=True)

    cell("A22", "Imposta")
    cell("B22", "=E19", fmt=money_fmt)
    cell("C22", "=E19", fmt=money_fmt)

    cell("A23", "INPS")
    cell("B23", "=F19", fmt=money_fmt)
    cell("C23", "=G19", fmt=money_fmt)

    cell("A24", "Commercialista")
    cell("B24", "=I19", fmt=money_fmt)

    cell("A25", "Bollo fatture")
    cell("B25", "=H19", fmt=money_fmt)

    cell("A26", "Totale", bold=True)
    cell("B26", "=SUM(B22:B25)", bold=True, fmt=money_fmt)
    cell("C26", "=SUM(C22:C25)", bold=True, fmt=money_fmt)
    cell("D26", "=B26+C26", bold=True, fmt=money_fmt)

    for row in ws["A21:D26"]:
        for c in row:
            c.border = box

    # Larghezza colonne
    widths = {"A": 22, "B": 13, "C": 13, "D": 13, "E": 12, "F": 12,
              "G": 13, "H": 14, "I": 15, "J": 13}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@fatture_bp.get("/api/export/xlsx")
def api_export_xlsx():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    anno = request.args.get("anno", type=int) or date.today().year
    try:
        buf = _build_workbook(sb, anno)
    except Exception as e:
        return jsonify({"error": str(e)[:250]}), 500
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Situazione_forfait_{anno}.xlsx",
    )


# ---------------------------------------------------------------------------
# Parametri fiscali
# ---------------------------------------------------------------------------

@fatture_bp.get("/parametri")
def parametri_editor():
    sb, err = _supabase_or_error()
    breadcrumb = [("Fatture", "/fatture"), ("Situazione fiscale", "/fatture/situazione"),
                  ("Parametri", "")]
    if err:
        return _render(err, breadcrumb=breadcrumb)
    p = _get_parametri(sb)

    body = f'''
    <div class="card">
      <div class="field"><label>Regime</label>
        <select id="f_regime">
          <option value="RF19"{" selected" if p["regime"]=="RF19" else ""}>RF19 — Forfettario</option>
        </select></div>
      <div class="field"><label>ATECO (readonly)</label>
        <input value="{p['ateco']} — {p.get('ateco_descrizione') or ''}" disabled></div>
      <div class="field-group">
        <div class="field"><label>Coefficiente redditività</label>
          <input type="number" step="0.0001" id="f_coeff" value="{p['coeff_ateco']}"></div>
        <div class="field"><label>Aliquota imposta sostitutiva</label>
          <input type="number" step="0.0001" id="f_aliq_imp" value="{p['aliquota_imposta']}"></div>
      </div>
      <div class="field-group">
        <div class="field"><label>Aliquota INPS Gestione Separata</label>
          <input type="number" step="0.0001" id="f_aliq_inps" value="{p['aliquota_inps']}"></div>
        <div class="field"><label>Aliquota acconto (solo INPS)</label>
          <input type="number" step="0.0001" id="f_aliq_acc" value="{p['aliquota_acconto']}"></div>
      </div>
      <div class="field-group">
        <div class="field"><label>Bollo soglia (€)</label>
          <input type="number" step="0.01" id="f_bollo_soglia" value="{p['bollo_soglia']}"></div>
        <div class="field"><label>Bollo importo (€)</label>
          <input type="number" step="0.01" id="f_bollo_importo" value="{p['bollo_importo']}"></div>
      </div>
      <div class="field"><label>Limite fatturato annuo (€)</label>
        <input type="number" step="0.01" id="f_limite" value="{p['limite_fatturato_anno']}"></div>
      <div class="field-group">
        <div class="field"><label>Data apertura P.IVA</label>
          <input type="date" id="f_data_apertura" value="{p['data_apertura_piva']}"></div>
        <div class="field"><label>Anno fine regime agevolato</label>
          <input type="number" id="f_anno_fine" value="{p.get('anno_fine_regime_agevolato') or ''}"></div>
      </div>
      <div class="actions">
        <button type="button" class="btn" onclick="onSalva()">Salva</button>
      </div>
    </div>
    <div id="toast" class="toast"></div>
    <script>
    function toast(msg, cls) {{
      const t = document.getElementById('toast');
      t.textContent = msg; t.className = 'toast show ' + (cls || '');
      setTimeout(()=>{{t.className='toast '+(cls||'')}}, 2200);
    }}
    async function onSalva() {{
      const g = id => Number(document.getElementById(id).value);
      const body = {{
        regime: document.getElementById('f_regime').value,
        coeff_ateco: g('f_coeff'),
        aliquota_imposta: g('f_aliq_imp'),
        aliquota_inps: g('f_aliq_inps'),
        aliquota_acconto: g('f_aliq_acc'),
        bollo_soglia: g('f_bollo_soglia'),
        bollo_importo: g('f_bollo_importo'),
        limite_fatturato_anno: g('f_limite'),
        data_apertura_piva: document.getElementById('f_data_apertura').value,
        anno_fine_regime_agevolato: g('f_anno_fine'),
      }};
      try {{
        const r = await fetch('/fatture/api/parametri', {{
          method: 'PATCH', headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(body),
        }});
        const j = await r.json();
        if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
        toast('Parametri aggiornati', 'ok');
      }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
    }}
    </script>
    '''
    return _render(body, eyebrow="Parametri fiscali",
                   title_html='Parametri <em>fiscali</em>', breadcrumb=breadcrumb)


@fatture_bp.get("/api/parametri")
def api_parametri_get():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    return jsonify(_get_parametri(sb))


@fatture_bp.patch("/api/parametri")
def api_parametri_update():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    payload = {k: data[k] for k in PARAMETRI_CAMPI if k in data}
    try:
        r = sb.table("b2f_parametri_fiscali").update(payload).eq("id", 1).execute()
        return jsonify(r.data[0] if r.data else {"id": 1})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# ---------------------------------------------------------------------------
# CRUD spese P.IVA
# ---------------------------------------------------------------------------

def _movimento_label(m: dict) -> str:
    tipo = m.get("tipo") or "uscita"
    segno = {"entrata": "+", "uscita": "−", "giroconto": "⇄"}.get(tipo, "")
    cls = {"entrata": "pos", "uscita": "neg", "giroconto": ""}.get(tipo, "")
    return segno, cls


@fatture_bp.get("/spese-piva")
def spese_piva_list():
    sb, err = _supabase_or_error()
    breadcrumb = [("Fatture", "/fatture"), ("Situazione fiscale", "/fatture/situazione"),
                  ("Spese P.IVA", "")]
    if err:
        return _render(err, breadcrumb=breadcrumb, fab=("Nuovo movimento", "/fatture/spese-piva/nuova"))

    anno_default = date.today().year
    anno = request.args.get("anno", type=int) or anno_default
    categoria = request.args.get("categoria") or ""
    tipo = request.args.get("tipo") or ""

    try:
        q = (sb.table("b2f_spese_piva").select("*")
               .gte("data", f"{anno}-01-01").lte("data", f"{anno}-12-31")
               .order("data", desc=True))
        if categoria:
            q = q.eq("categoria", categoria)
        if tipo:
            q = q.eq("tipo", tipo)
        rows = (q.execute()).data or []
    except Exception as e:
        return _render(f'<div class="notice err">Errore: {str(e)[:200]}</div>', breadcrumb=breadcrumb)

    cat_opts = "".join(
        f'<option value="{k}"{" selected" if categoria==k else ""}>{lbl}</option>'
        for k, lbl in CATEGORIE_SPESE_PIVA
    )
    tipo_opts = "".join(
        f'<option value="{k}"{" selected" if tipo==k else ""}>{lbl}</option>'
        for k, lbl in (("entrata", "Entrata"), ("uscita", "Uscita"), ("giroconto", "Giroconto"))
    )

    toolbar = f'''
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <select onchange="const u=new URL(location.href);u.searchParams.set('anno',this.value);location.href=u"
              style="padding:10px 14px;border-radius:999px;background:var(--input-bg);
                     border:1px solid var(--line-strong);color:var(--ink);font-size:14px">
        {"".join(f'<option value="{y}"{" selected" if y==anno else ""}>{y}</option>' for y in range(anno_default, anno_default-6, -1))}
      </select>
      <select onchange="const u=new URL(location.href);if(this.value){{u.searchParams.set('categoria',this.value)}}else{{u.searchParams.delete('categoria')}};location.href=u"
              style="padding:10px 14px;border-radius:999px;background:var(--input-bg);
                     border:1px solid var(--line-strong);color:var(--ink);font-size:14px">
        <option value="">Tutte le categorie</option>{cat_opts}
      </select>
      <select onchange="const u=new URL(location.href);if(this.value){{u.searchParams.set('tipo',this.value)}}else{{u.searchParams.delete('tipo')}};location.href=u"
              style="padding:10px 14px;border-radius:999px;background:var(--input-bg);
                     border:1px solid var(--line-strong);color:var(--ink);font-size:14px">
        <option value="">Tutti i tipi</option>{tipo_opts}
      </select>
    </div>
    '''

    tot = sum(float(r.get("importo") or 0) * (1 if r.get("tipo") == "entrata" else -1)
              for r in rows if r.get("tipo") in ("entrata", "uscita"))
    riepilogo = f'''
    <div class="card">
      <div class="eyebrow" style="margin-bottom:6px">Anno {anno}</div>
      <div class="stat">
        <div class="num tnum">€ {_fmt_eur(tot)}</div>
        <div class="lbl">Saldo movimenti</div>
      </div>
    </div>
    '''

    if not rows:
        body = f'''{riepilogo}{toolbar}
        <div class="empty">
          <svg viewBox="0 0 24 24"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h13A2.5 2.5 0 0 1 21 6.5V8H3z"/>
          <path d="M3 8v9.5A2.5 2.5 0 0 0 5.5 20h13a2.5 2.5 0 0 0 2.5-2.5V8"/></svg>
          <div class="t">Nessun movimento per il {anno}</div>
          <div class="s">Aggiungi il primo con il pulsante in basso.</div>
        </div>'''
    else:
        cat_lbl = dict(CATEGORIE_SPESE_PIVA)
        items = []
        for m in rows:
            segno, cls = _movimento_label(m)
            items.append(f'''
            <a class="item" href="/fatture/spese-piva/{m["id"]}">
              <div class="info">
                <div class="n">{(m.get("descrizione") or "—")[:40]}</div>
                <div class="m">{_fmt_date(m.get("data"))} · {cat_lbl.get(m.get("categoria"), m.get("categoria") or "—")}</div>
              </div>
              <div class="end"><span class="tnum a {cls}">{segno} € {_fmt_eur(m.get("importo"))}</span></div>
            </a>''')
        body = f'{riepilogo}{toolbar}<div class="list">{"".join(items)}</div>'

    return _render(body, eyebrow="Spese P.IVA", title_html='Spese <em>P.IVA</em>',
                   breadcrumb=breadcrumb, fab=("Nuovo movimento", "/fatture/spese-piva/nuova"))


def _movimento_form_html(m: dict | None = None) -> str:
    m = m or {}
    v = lambda k, d="": (m.get(k) if m.get(k) is not None else d)
    tipo_current = m.get("tipo") or "uscita"
    cat_current = m.get("categoria") or ""
    cat_opts = "".join(
        f'<option value="{k}"{" selected" if k==cat_current else ""}>{lbl}</option>'
        for k, lbl in CATEGORIE_SPESE_PIVA
    )
    mid = m.get("id") or ""
    is_edit = bool(mid)
    submit_lbl = "Aggiorna" if is_edit else "Registra movimento"
    delete_btn = (f'<button type="button" class="btn ghost" onclick="onElimina({mid})">Elimina</button>'
                  if is_edit else "")

    return f'''
    <div class="card">
      <div class="field"><label>Data</label>
        <input type="date" id="f_data" value="{v('data', date.today().isoformat())}"></div>
      <div class="field"><label>Tipo</label>
        <select id="f_tipo">
          <option value="entrata"{" selected" if tipo_current=="entrata" else ""}>Entrata</option>
          <option value="uscita"{" selected" if tipo_current=="uscita" else ""}>Uscita</option>
          <option value="giroconto"{" selected" if tipo_current=="giroconto" else ""}>Giroconto</option>
        </select></div>
      <div class="field"><label>Importo (€)</label>
        <input type="number" step="0.01" id="f_importo" value="{v('importo', 0)}"></div>
      <div class="field"><label>Descrizione</label>
        <input id="f_descrizione" value="{(v('descrizione') or '').replace(chr(34), '&quot;')}"></div>
      <div class="field-group">
        <div class="field"><label>Categoria</label>
          <select id="f_categoria"><option value="">—</option>{cat_opts}</select></div>
        <div class="field"><label>Sottocategoria</label>
          <input id="f_sottocategoria" value="{v('sottocategoria') or ''}"></div>
      </div>
      <div class="field" style="flex-direction:row;align-items:center;gap:8px">
        <input type="checkbox" id="f_ricorrente" style="width:auto;min-height:auto"
               {"checked" if m.get("ricorrente") else ""}>
        <label style="margin:0">Movimento ricorrente</label>
      </div>
      <div class="field"><label>Note</label>
        <textarea id="f_note">{m.get('note') or ''}</textarea></div>
      <div class="actions">
        <button type="button" class="btn" onclick="onSubmit({mid or 'null'})">{submit_lbl}</button>
        {delete_btn}
      </div>
    </div>
    <div id="toast" class="toast"></div>
    <script>
    function toast(msg, cls) {{
      const t = document.getElementById('toast');
      t.textContent = msg; t.className = 'toast show ' + (cls || '');
      setTimeout(()=>{{t.className='toast '+(cls||'')}}, 2200);
    }}
    function readForm() {{
      return {{
        data: document.getElementById('f_data').value,
        tipo: document.getElementById('f_tipo').value,
        importo: Number(document.getElementById('f_importo').value || 0),
        descrizione: document.getElementById('f_descrizione').value.trim(),
        categoria: document.getElementById('f_categoria').value || null,
        sottocategoria: document.getElementById('f_sottocategoria').value.trim() || null,
        ricorrente: document.getElementById('f_ricorrente').checked,
        note: document.getElementById('f_note').value.trim() || null,
      }};
    }}
    async function onSubmit(mid) {{
      const body = readForm();
      const isNew = !mid;
      const url = isNew ? '/fatture/api/spese-piva' : '/fatture/api/spese-piva/'+mid;
      const method = isNew ? 'POST' : 'PATCH';
      try {{
        const r = await fetch(url, {{
          method, headers: {{'Content-Type':'application/json'}}, body: JSON.stringify(body),
        }});
        const j = await r.json();
        if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
        toast(isNew ? 'Movimento registrato' : 'Aggiornato', 'ok');
        setTimeout(()=>{{ location.href = '/fatture/spese-piva'; }}, 500);
      }} catch (e) {{ toast('Errore: '+e.message, 'err'); }}
    }}
    async function onElimina(mid) {{
      if (!confirm('Eliminare questo movimento?')) return;
      try {{
        const r = await fetch('/fatture/api/spese-piva/'+mid, {{method:'DELETE'}});
        if (!r.ok) {{ toast('Errore', 'err'); return; }}
        toast('Eliminato', 'ok');
        setTimeout(()=>{{ location.href = '/fatture/spese-piva'; }}, 500);
      }} catch (e) {{ toast('Errore: '+e.message, 'err'); }}
    }}
    </script>
    '''


@fatture_bp.get("/spese-piva/nuova")
def spesa_piva_new():
    breadcrumb = [("Fatture", "/fatture"), ("Situazione fiscale", "/fatture/situazione"),
                  ("Spese P.IVA", "/fatture/spese-piva"), ("Nuovo", "")]
    return _render(_movimento_form_html(None), eyebrow="Nuovo movimento",
                   title_html='<em>Nuovo</em> movimento', breadcrumb=breadcrumb)


@fatture_bp.get("/spese-piva/<int:mid>")
def spesa_piva_edit(mid):
    sb, err = _supabase_or_error()
    breadcrumb = [("Fatture", "/fatture"), ("Situazione fiscale", "/fatture/situazione"),
                  ("Spese P.IVA", "/fatture/spese-piva"), (str(mid), "")]
    if err:
        return _render(err, breadcrumb=breadcrumb)
    try:
        r = sb.table("b2f_spese_piva").select("*").eq("id", mid).single().execute()
        m = r.data
    except Exception as e:
        return _render(f'<div class="notice err">{str(e)[:200]}</div>', breadcrumb=breadcrumb)

    return _render(_movimento_form_html(m), eyebrow="Movimento",
                   title_html=f'<em>{(m.get("descrizione") or "Movimento")[:20]}</em>',
                   breadcrumb=breadcrumb)


@fatture_bp.get("/api/spese-piva")
def api_spese_piva_list():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    anno = request.args.get("anno", type=int)
    categoria = request.args.get("categoria")
    tipo = request.args.get("tipo")
    try:
        q = sb.table("b2f_spese_piva").select("*").order("data", desc=True)
        if anno:
            q = q.gte("data", f"{anno}-01-01").lte("data", f"{anno}-12-31")
        if categoria:
            q = q.eq("categoria", categoria)
        if tipo:
            q = q.eq("tipo", tipo)
        r = q.execute()
        return jsonify(r.data or [])
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


def _movimento_payload(data: dict) -> dict:
    out = {}
    for k in MOVIMENTO_CAMPI:
        if k in data:
            v = data[k]
            if isinstance(v, str):
                v = v.strip() or None
            out[k] = v
    return out


@fatture_bp.post("/api/spese-piva")
def api_spesa_piva_create():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    for k in ("data", "importo", "tipo", "descrizione"):
        if not data.get(k) and data.get(k) != 0:
            return jsonify({"error": f"campo mancante: {k}"}), 400
    if data.get("tipo") not in ("entrata", "uscita", "giroconto"):
        return jsonify({"error": "tipo non valido"}), 400
    payload = _movimento_payload(data)
    try:
        r = sb.table("b2f_spese_piva").insert(payload).execute()
        return jsonify(r.data[0] if r.data else {})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.patch("/api/spese-piva/<int:mid>")
def api_spesa_piva_update(mid):
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    payload = _movimento_payload(data)
    try:
        r = sb.table("b2f_spese_piva").update(payload).eq("id", mid).execute()
        return jsonify(r.data[0] if r.data else {"id": mid})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.delete("/api/spese-piva/<int:mid>")
def api_spesa_piva_delete(mid):
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    try:
        sb.table("b2f_spese_piva").delete().eq("id", mid).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _render(content: str, eyebrow: str = "Situazione fiscale",
            title_html: str = 'Situazione <em>fiscale</em>',
            breadcrumb=None, fab=None) -> Response:
    html = render_page(
        section="fatture", eyebrow=eyebrow, title_html=title_html,
        content=content, breadcrumb=breadcrumb, fab=fab,
    )
    return Response(html, mimetype="text/html")
