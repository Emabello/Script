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
from . import accantonamento as acc
from .costanti import CATEGORIE_SPESE_PIVA, MESI_NOMI, STATI_EMESSE
from shared.theme import render_page
from shared.design import icon as _icon
from shared.supabase_client import get_client, is_configured
from shared.fmt import eur as _fmt_eur, data_it as _fmt_date, pct


PARAMETRI_DEFAULT = {
    "id": 1, "regime": "RF19", "ateco": "622010",
    "ateco_descrizione": "Attività di consulenza informatica",
    "coeff_ateco": 0.67, "aliquota_imposta": 0.05, "aliquota_inps": 0.2607,
    "aliquota_acconto": 0.80, "bollo_soglia": 77.47, "bollo_importo": 2.00,
    "limite_fatturato_anno": 85000, "data_apertura_piva": "2026-05-28",
    "anno_fine_regime_agevolato": 2031,
    **acc.PARAMETRI_DEFAULT,
}

PARAMETRI_CAMPI = (
    "regime", "coeff_ateco", "aliquota_imposta", "aliquota_inps",
    "aliquota_acconto", "bollo_soglia", "bollo_importo",
    "limite_fatturato_anno", "data_apertura_piva", "anno_fine_regime_agevolato",
) + acc.PARAMETRI_CAMPI

MOVIMENTO_CAMPI = (
    "data", "importo", "tipo", "descrizione", "categoria",
    "sottocategoria", "fattura_id", "ricorrente", "note",
)


def _supabase_or_error():
    if not is_configured():
        return None, ('<div class="notice warn">Supabase non configurato.</div>')
    return get_client(), None


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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
    rivalsa_mese = {m: 0.0 for m in range(1, 13)}
    incasso_mese = {m: 0.0 for m in range(1, 13)}
    commercialista_mese = {m: 0.0 for m in range(1, 13)}
    spese_piva_uscite_tot = 0.0

    try:
        r = (sb.table("b2f_fatture")
               .select("data,data_incasso,totale,bollo,bollo_addebitato,cassa_importo,stato")
               .gte("data", f"{anno}-01-01").lte("data", f"{anno}-12-31")
               .in_("stato", list(STATI_EMESSE)).execute())
        for f in (r.data or []):
            mese = int(f["data"][5:7])
            fatturato_mese[mese] += float(f.get("totale") or 0)
            if f.get("bollo_addebitato"):
                bollo_mese[mese] += float(f.get("bollo") or 0)
            # Solo per trasparenza nell'export: la rivalsa resta dentro
            # "fatturato"/"totale" (concorre al reddito, vedi accantonamento.py),
            # qui si somma a parte solo per mostrarne la quota.
            rivalsa_mese[mese] += float(f.get("cassa_importo") or 0)
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
                             "inps_saldo", "inps_acconto", "bollo", "commercialista",
                             "rivalsa")}
    for m in range(1, 13):
        fatt = fatturato_mese[m]
        imponibile = round(fatt * coeff, 2)
        inps_saldo = round(imponibile * aliq_inps, 2)
        # L'imposta sostitutiva si calcola sul reddito al netto dei contributi
        # INPS deducibili: (Imponibile - INPS Saldo) * aliquota.
        imposta = round((imponibile - inps_saldo) * aliq_imp, 2)
        inps_acconto = round(inps_saldo * aliq_acc, 2)
        incasso = incasso_mese[m]
        bollo = bollo_mese[m]
        comm = commercialista_mese[m]
        rivalsa = rivalsa_mese[m]
        # "Stipendio" del foglio di riferimento: incasso meno tutto, acconti
        # inclusi. Resta per parita' con l'export Excel.
        netto = round(incasso - imposta - inps_saldo - inps_acconto - bollo - comm, 2)
        # Quanto resta davvero di competenza: gli acconti sono un anticipo
        # sull'anno successivo, non un costo dell'anno.
        netto_comp = round(incasso - imposta - inps_saldo - bollo - comm, 2)
        mensile.append({
            "mese": m, "nome": MESI_NOMI[m - 1],
            "fatturato": fatt, "imponibile": imponibile, "incasso": incasso,
            "imposta": imposta, "inps_saldo": inps_saldo, "inps_acconto": inps_acconto,
            "bollo": bollo, "commercialista": comm, "rivalsa": rivalsa,
            "netto": netto, "netto_competenza": netto_comp,
        })
        tot["fatturato"] += fatt
        tot["imponibile"] += imponibile
        tot["incasso"] += incasso
        tot["imposta"] += imposta
        tot["inps_saldo"] += inps_saldo
        tot["rivalsa"] += rivalsa
        tot["inps_acconto"] += inps_acconto
        tot["bollo"] += bollo
        tot["commercialista"] += comm

    for k in tot:
        tot[k] = round(tot[k], 2)

    mesi_attivita = _mesi_attivita(anno, param["data_apertura_piva"])
    limite_ragguagliato = round(limite_anno / 12 * mesi_attivita, 2)

    # L'acconto dell'imposta sostitutiva e' pari al 100 % del saldo (nessuna
    # riduzione), a differenza dell'INPS che va all'80 % col metodo storico.
    acc_imposta_perc = float(param.get("acconto_imposta_perc") or 1.0)
    imposta_acconto = round(tot["imposta"] * acc_imposta_perc, 2)

    scadenza_giugno = round(tot["imposta"] + tot["inps_saldo"]
                            + tot["commercialista"] + tot["bollo"], 2)
    scadenza_novembre = round(imposta_acconto + tot["inps_acconto"], 2)

    # Due grandezze che prima erano confuse in un unico "netto stimato":
    #  - competenza: quanto dell'anno resta davvero tuo. Gli acconti non
    #    sono un costo, sono un anticipo che si scomputa dal saldo dopo.
    #  - cassa: quanto serve avere da parte per onorare le due scadenze,
    #    che nell'anno di transizione cadono sullo stesso anno solare.
    netto_competenza = round(tot["incasso"] - tot["imposta"] - tot["inps_saldo"]
                             - tot["bollo"] - tot["commercialista"], 2)
    dovuto_saldo = round(tot["imposta"] + tot["inps_saldo"], 2)
    acconti = round(imposta_acconto + tot["inps_acconto"], 2)
    cassa_da_riservare = round(scadenza_giugno + scadenza_novembre, 2)

    # Accantonamento consigliato sull'incassato dell'anno, esposto anche
    # dall'API cosi' le altre pagine non devono rifare il calcolo.
    scomposizione = acc.scomponi(tot["incasso"], param,
                                 fatturato_riferimento=tot["incasso"],
                                 rivalsa=tot["rivalsa"], bollo_addebitato=tot["bollo"])

    return {
        "anno": anno,
        "parametri": param,
        "accantonamento": {
            **scomposizione["importi"],
            "aliquote": scomposizione["aliquote"],
            "netti": scomposizione["netti"],
        },
        "limite_ragguagliato": limite_ragguagliato,
        "mesi_attivita": mesi_attivita,
        "totali": {
            "fatturato": tot["fatturato"],
            "imponibile": tot["imponibile"],
            "incasso": tot["incasso"],
            "imposta_accantonata": tot["imposta"],
            "inps_saldo_accantonato": tot["inps_saldo"],
            "inps_acconto_accantonato": tot["inps_acconto"],
            "imposta_acconto": imposta_acconto,
            "bollo_totale": tot["bollo"],
            "rivalsa_totale": tot["rivalsa"],
            "commercialista_totale": tot["commercialista"],
            "spese_piva_totali": round(spese_piva_uscite_tot, 2),
            # Nuove grandezze, esplicite
            "dovuto_saldo": dovuto_saldo,
            "acconti": acconti,
            "cassa_da_riservare": cassa_da_riservare,
            "netto_competenza": netto_competenza,
            # Alias storici, mantenuti per non rompere chi li leggeva
            "totale_da_versare": cassa_da_riservare,
            "netto_stimato": netto_competenza,
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


def saldo_piva(sb, al: str | None = None) -> dict:
    """
    Saldo reale del conto P.IVA a una data (default: oggi).

    Non e' il saldo dell'anno filtrato che mostra /fatture/spese-piva: e'
    quanto c'e' sul conto, tutti i movimenti dall'apertura fino ad `al`.
    Dal secondo anno in poi i due numeri divergono, perche' il conto non
    riparte da zero a gennaio.

    Le tre direzioni sono diverse fra loro:
      entrata    il cliente ha pagato          -> entra
      uscita     un costo della P.IVA          -> esce
      giroconto  la tua quota va sul personale -> esce (ma non e' un costo)

    `rivalsa_incassata` e' la quota di rivalsa INPS gia' entrata su questo
    conto insieme agli incassi: non e' un ricavo tuo, e' la parte del
    corrispettivo destinata al contributo previdenziale. Va lasciata qui:
    serve a farla vedere, perche' dentro il saldo e' invisibile.

    Le righe si leggono a blocchi: PostgREST tronca ogni richiesta a un
    tetto, e un saldo troncato sarebbe sbagliato senza dare errore.
    """
    al = al or date.today().isoformat()
    vuoto = {"al": al, "disponibile": False, "saldo": 0.0, "entrate": 0.0,
             "uscite": 0.0, "girati": 0.0, "rivalsa_incassata": 0.0,
             "movimenti": 0}

    entrate = uscite = girati = 0.0
    n = 0
    offset, passo = 0, 1000
    while True:
        try:
            r = (sb.table("b2f_spese_piva").select("importo,tipo,data")
                   .lte("data", al).order("data", desc=False)
                   .range(offset, offset + passo - 1).execute())
            pagina = r.data or []
        except Exception:
            return vuoto
        for m in pagina:
            imp = abs(float(m.get("importo") or 0))
            tipo = m.get("tipo")
            if tipo == "entrata":
                entrate += imp
            elif tipo == "uscita":
                uscite += imp
            elif tipo == "giroconto":
                girati += imp
            n += 1
        if len(pagina) < passo:
            break
        offset += passo

    # Rivalsa gia' incassata: si conta sulle fatture incassate, non sui
    # movimenti P.IVA, perche' e' la fattura a sapere quanta parte del
    # totale era rivalsa (`cassa_importo`).
    rivalsa = 0.0
    try:
        r = (sb.table("b2f_fatture").select("cassa_importo,data_incasso")
               .eq("stato", "incassata").lte("data_incasso", al).execute())
        rivalsa = sum(float(f.get("cassa_importo") or 0) for f in (r.data or [])
                      if f.get("data_incasso"))
    except Exception:
        rivalsa = 0.0

    return {
        "al": al,
        "disponibile": True,
        "entrate": round(entrate, 2),
        "uscite": round(uscite, 2),
        "girati": round(girati, 2),
        "rivalsa_incassata": round(rivalsa, 2),
        "saldo": round(entrate - uscite - girati, 2),
        "movimenti": n,
    }


# Alias pubblici: app.py e i moduli fratelli hanno bisogno di questi due.
def get_parametri(sb) -> dict:
    """Parametri fiscali correnti, con i default applicati."""
    return _get_parametri(sb)


def situazione_data(sb, anno: int) -> dict:
    """Situazione fiscale completa dell'anno indicato."""
    return _situazione_data(sb, anno)


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
    limite_cls = "neg" if pct_limite >= 90 else "warn" if pct_limite >= 70 else ""
    pct_it = f"{pct_limite:.1f}".replace(".", ",")

    anno_opts = "".join(
        f'<option value="{y}"{" selected" if y == anno else ""}>{y}</option>'
        for y in range(anno_default + 1, anno_default - 5, -1)
    )
    toolbar_anno = (
        '<div class="toolbar">'
        '<select class="select-pill" aria-label="Anno"'
        ' onchange="location.href=\'/fatture/situazione?anno=\'+this.value">'
        f'{anno_opts}</select></div>'
    )

    # --- Tessere principali -------------------------------------------------
    kpi = f'''
    <div class="grid kpi mb-4">
      <div class="card"><div class="stat">
        <div class="val tnum">€ {_fmt_eur(t["fatturato"], 0)}</div>
        <div class="lbl">Fatturato {anno}</div></div></div>
      <div class="card"><div class="stat">
        <div class="val tnum">€ {_fmt_eur(t["incasso"], 0)}</div>
        <div class="lbl">Incassato</div>
        <div class="hint">su cui si pagano le tasse</div></div></div>
      <div class="card"><div class="stat">
        <div class="val tnum accent">€ {_fmt_eur(t["cassa_da_riservare"], 0)}</div>
        <div class="lbl">Cassa da riservare</div>
        <div class="hint">saldo + acconti</div></div></div>
      <div class="card"><div class="stat">
        <div class="val tnum pos">€ {_fmt_eur(t["netto_competenza"], 0)}</div>
        <div class="lbl">Netto di competenza</div>
        <div class="hint">quanto ti resta davvero</div></div></div>
    </div>

    <details class="explain card mb-4">
      <summary>Due basi di calcolo diverse, ed è voluto</summary>
      <p class="small muted mt-2">
        Imposta, INPS e scadenze qui sopra sono calcolate sul <strong>fatturato
        emesso</strong>, per restare allineate al foglio Excel di riferimento.
        L'accantonamento qui sotto lavora invece sull'<strong>incassato</strong>,
        che è la base corretta del forfettario (regime di cassa). Finché emetti
        e incassi nello stesso anno i due numeri quasi coincidono; a cavallo di
        fine anno divergono, ed è normale che sia così.
      </p>
    </details>'''

    # --- Accantonamento sull'incassato dell'anno ----------------------------
    scomposizione = acc.scomponi(t["incasso"], s["parametri"],
                                 fatturato_riferimento=t["incasso"],
                                 rivalsa=t.get("rivalsa_totale", 0),
                                 bollo_addebitato=t.get("bollo_totale", 0))
    acc_card = acc.card_html(
        scomposizione,
        titolo=f"Da accantonare sul {anno}",
        contesto="Calcolato sull'incassato dell'anno. Il minimo è il dovuto "
                 "esatto; il sicuro copre anche l'anno in cui saldo e acconti "
                 "cadono insieme.",
        uid="accAnno",
    ) if t["incasso"] > 0 else ""

    # --- Limite forfettario --------------------------------------------------
    residuo = max(s["limite_ragguagliato"] - t["fatturato"], 0)
    limite = f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">Limite forfettario</div>
        <span class="chip {limite_cls or "accent"}">{pct_it} %</span>
      </div>
      <div class="meter"><i class="{limite_cls}" style="width:{pct_limite:.1f}%"></i></div>
      <div class="small muted mt-3">
        € {_fmt_eur(t["fatturato"])} su € {_fmt_eur(s["limite_ragguagliato"])}
        ragguagliati a {s["mesi_attivita"]} mesi di attività.
        Restano <strong>€ {_fmt_eur(residuo)}</strong>.
      </div>
    </div>'''

    # --- Scadenze -------------------------------------------------------------
    scadenze_html = "".join(f'''
      <div class="row">
        <div class="t">{sc["descrizione"]}<span class="sub">{_fmt_date(sc["data"])}</span></div>
        <div class="v tnum">€ {_fmt_eur(sc["importo"])}</div>
      </div>''' for sc in s["scadenze"])
    scadenze = f'''
    <div class="card">
      <div class="card-head"><div class="eyebrow">Scadenze</div></div>
      <div class="rows detail">{scadenze_html}</div>
      <details class="explain mt-3">
        <summary>Perché l'imposta compare due volte</summary>
        <p class="small muted mt-2">
          A giugno versi il <strong>saldo</strong> dell'anno appena chiuso; a novembre
          l'<strong>acconto</strong> per l'anno in corso — INPS all'80 % col metodo
          storico, imposta sostitutiva al 100 %. L'acconto non è una tassa in più:
          si scomputa dal saldo successivo. Ma nell'anno in cui le due cose cadono
          insieme devi avere in banca la somma di entrambe.
        </p>
      </details>
    </div>'''

    # --- Riepilogo mensile: solo i mesi con movimento -------------------------
    mesi_attivi = [m for m in s["mensile"]
                   if m["fatturato"] or m["incasso"] or m["commercialista"]]
    if mesi_attivi:
        righe = "".join(f'''
        <tr>
          <td>{m["nome"]}</td>
          <td class="num">{_fmt_eur(m["fatturato"])}</td>
          <td class="num">{_fmt_eur(m["incasso"])}</td>
          <td class="num">{_fmt_eur(m["inps_saldo"])}</td>
          <td class="num">{_fmt_eur(m["imposta"])}</td>
          <td class="num">{_fmt_eur(m["netto_competenza"])}</td>
        </tr>''' for m in mesi_attivi)
        tabella = f'''
        <div class="scroll-x">
          <table class="table">
            <thead><tr>
              <th>Mese</th><th class="num">Fatturato</th><th class="num">Incassato</th>
              <th class="num">INPS</th><th class="num">Imposta</th>
              <th class="num">Netto</th>
            </tr></thead>
            <tbody>{righe}</tbody>
            <tfoot><tr>
              <td>Totale</td>
              <td class="num">{_fmt_eur(t["fatturato"])}</td>
              <td class="num">{_fmt_eur(t["incasso"])}</td>
              <td class="num">{_fmt_eur(t["inps_saldo_accantonato"])}</td>
              <td class="num">{_fmt_eur(t["imposta_accantonata"])}</td>
              <td class="num">{_fmt_eur(t["netto_competenza"])}</td>
            </tr></tfoot>
          </table>
        </div>'''
    else:
        tabella = ('<div class="small muted">Nessun movimento registrato '
                   f'per il {anno}.</div>')

    mensile = f'''
    <div class="card">
      <div class="card-head"><div class="eyebrow">Riepilogo mensile</div></div>
      {tabella}
    </div>'''

    azioni = f'''
    <div class="card">
      <div class="card-head"><div class="eyebrow">Strumenti</div></div>
      <div class="actions col mt-0">
        <a class="btn" href="/fatture/api/export/xlsx?anno={anno}">
          {_icon("download")}Esporta Excel
        </a>
        <a class="btn ghost" href="/fatture/parametri">Parametri fiscali</a>
        <a class="btn ghost" href="/fatture/spese-piva">Movimenti P.IVA</a>
      </div>
    </div>'''

    body = f'''
    {toolbar_anno}
    {kpi}
    {acc_card}
    <div class="grid split mt-4">
      <div class="stack">{mensile}</div>
      <div class="stack">{limite}{scadenze}{azioni}</div>
    </div>
    '''

    return _render(body, eyebrow="Fiscale",
                   title_html='Situazione <em>fiscale</em>',
                   breadcrumb=breadcrumb)


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
    # "Rivalsa INPS" e' in coda e non fra Fatturato e Imponibile apposta:
    # e' gia' dentro "Fatturato" (concorre al reddito, vedi accantonamento.py
    # e Risposta Agenzia Entrate 428/2022) — qui e' solo la quota mostrata
    # a parte per trasparenza, non un valore da sommare a se'.
    headers = ["Mese", "Fatturato", "Imponibile", "Incasso", "Imposta",
               "INPS Saldo", "INPS Acconto", "Bollo Fattura", "Commercialista",
               "Stipendio", "di cui Rivalsa INPS"]
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
        cell(f"E{r}", f"=(C{r}-F{r})*$E$5", fmt=money_fmt)
        cell(f"F{r}", f"=C{r}*$F$5", fmt=money_fmt)
        cell(f"G{r}", f"=F{r}*$G$5", fmt=money_fmt)
        cell(f"H{r}", m["bollo"], fmt=money_fmt, fill=input_fill)
        cell(f"I{r}", m["commercialista"], fmt=money_fmt, fill=input_fill)
        cell(f"J{r}", f"=D{r}-E{r}-F{r}-G{r}-H{r}-I{r}", fmt=money_fmt)
        cell(f"K{r}", m["rivalsa"], fmt=money_fmt, fill=input_fill)

    # --- Riga 19: Totale ---
    top_border = Border(top=thin, bottom=Side(style="double"))
    for col in "BCDEFGHIJK":
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
              "G": 13, "H": 14, "I": 15, "J": 13, "K": 18}
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

    # Anteprima dal vivo: mostra subito l'effetto dei parametri su 1.000 €
    anteprima = acc.scomponi(1000.0, p, fatturato_riferimento=0.0)
    scen_opts = "".join(
        f'<option value="{k}"{" selected" if p.get("scenario_preferito") == k else ""}>'
        f'{acc.ETICHETTE[k][0]}</option>' for k in acc.SCENARI
    )

    body = f'''
    <div class="grid split">
      <div class="stack">

        <div class="card">
          <div class="card-head"><div class="eyebrow">Regime</div></div>
          <div class="field"><label>Regime fiscale</label>
            <select id="f_regime">
              <option value="RF19"{" selected" if p["regime"] == "RF19" else ""}>RF19 — Forfettario</option>
            </select></div>
          <div class="field"><label>Codice ATECO</label>
            <input value="{p['ateco']} — {p.get('ateco_descrizione') or ''}" disabled>
            <div class="hint">Modificabile solo da database.</div></div>
          <div class="field-group">
            <div class="field"><label>Data apertura P.IVA</label>
              <input type="date" id="f_data_apertura" value="{p['data_apertura_piva']}"></div>
            <div class="field"><label>Fine regime agevolato</label>
              <input type="number" id="f_anno_fine" value="{p.get('anno_fine_regime_agevolato') or ''}">
              <div class="hint">Primo anno con aliquota al 15 %.</div></div>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Aliquote</div></div>
          <div class="field-group">
            <div class="field"><label>Coefficiente redditività</label>
              <input type="number" step="0.0001" id="f_coeff" value="{p['coeff_ateco']}">
              <div class="hint">0,67 per la consulenza informatica.</div></div>
            <div class="field"><label>Imposta sostitutiva</label>
              <input type="number" step="0.0001" id="f_aliq_imp" value="{p['aliquota_imposta']}">
              <div class="hint">0,05 nei primi cinque anni.</div></div>
          </div>
          <div class="field-group">
            <div class="field"><label>INPS gestione separata</label>
              <input type="number" step="0.0001" id="f_aliq_inps" value="{p['aliquota_inps']}"></div>
            <div class="field"><label>Acconto INPS</label>
              <input type="number" step="0.0001" id="f_aliq_acc" value="{p['aliquota_acconto']}">
              <div class="hint">0,80 col metodo storico.</div></div>
          </div>
          <div class="field-group">
            <div class="field"><label>Acconto imposta</label>
              <input type="number" step="0.01" id="f_acc_imp" value="{p.get('acconto_imposta_perc', 1.0)}">
              <div class="hint">1,00 = 100 % del saldo, nessuna riduzione.</div></div>
            <div class="field"><label>Limite fatturato annuo (€)</label>
              <input type="number" step="0.01" id="f_limite" value="{p['limite_fatturato_anno']}"></div>
          </div>
          <div class="field-group">
            <div class="field"><label>Bollo — soglia (€)</label>
              <input type="number" step="0.01" id="f_bollo_soglia" value="{p['bollo_soglia']}"></div>
            <div class="field"><label>Bollo — importo (€)</label>
              <input type="number" step="0.01" id="f_bollo_importo" value="{p['bollo_importo']}"></div>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Accantonamento</div></div>
          <p class="small muted mb-3">
            Questi tre valori determinano lo scarto tra il dovuto matematico e
            quanto l'app ti consiglia di mettere da parte.
          </p>
          <div class="field-group">
            <div class="field"><label>Margine di sicurezza</label>
              <input type="number" step="0.01" id="f_margine" value="{p.get('margine_sicurezza', 0.10)}">
              <div class="hint">0,10 = 10 % in più del dovuto.</div></div>
            <div class="field"><label>Scenario preferito</label>
              <select id="f_scenario">{scen_opts}</select>
              <div class="hint">Quello mostrato per primo.</div></div>
          </div>
          <div class="field-group">
            <div class="field"><label>Costi fissi annui (€)</label>
              <input type="number" step="0.01" id="f_costi" value="{p.get('costi_fissi_annui', 0)}">
              <div class="hint">Commercialista, PEC, bolli, commissioni.</div></div>
            <div class="field"><label>Fatturato atteso annuo (€)</label>
              <input type="number" step="0.01" id="f_atteso" value="{p.get('fatturato_atteso_anno', 0)}">
              <div class="hint">Su cui spalmare i costi fissi. A zero li stima
                dall'incassato dell'anno.</div></div>
          </div>
        </div>

        <div class="actions">
          <button type="button" class="btn" onclick="onSalva()">Salva parametri</button>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Effetto su 1.000 € incassati</div></div>
          <div class="rows detail">
            <div class="row"><span class="t">Minimo <span class="sub">{acc.ETICHETTE["minimo"][1]}</span></span>
              <span class="v tnum">€ {_fmt_eur(anteprima["importi"]["minimo"])}</span></div>
            <div class="row"><span class="t">Consigliato <span class="sub">{acc.ETICHETTE["consigliato"][1]}</span></span>
              <span class="v tnum accent">€ {_fmt_eur(anteprima["importi"]["consigliato"])}</span></div>
            <div class="row"><span class="t">Sicuro <span class="sub">{acc.ETICHETTE["sicuro"][1]}</span></span>
              <span class="v tnum">€ {_fmt_eur(anteprima["importi"]["sicuro"])}</span></div>
          </div>
          <div class="small muted mt-3">
            Salva per aggiornare l'anteprima.
          </div>
        </div>
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
      const v = id => document.getElementById(id).value;
      const body = {{
        regime: v('f_regime'),
        coeff_ateco: g('f_coeff'),
        aliquota_imposta: g('f_aliq_imp'),
        aliquota_inps: g('f_aliq_inps'),
        aliquota_acconto: g('f_aliq_acc'),
        acconto_imposta_perc: g('f_acc_imp'),
        bollo_soglia: g('f_bollo_soglia'),
        bollo_importo: g('f_bollo_importo'),
        limite_fatturato_anno: g('f_limite'),
        data_apertura_piva: v('f_data_apertura'),
        anno_fine_regime_agevolato: g('f_anno_fine'),
        margine_sicurezza: g('f_margine'),
        costi_fissi_annui: g('f_costi'),
        fatturato_atteso_anno: g('f_atteso'),
        scenario_preferito: v('f_scenario'),
      }};
      try {{
        const r = await fetch('/fatture/api/parametri', {{
          method: 'PATCH', headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(body),
        }});
        const j = await r.json();
        if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
        toast('Parametri aggiornati', 'ok');
        setTimeout(() => location.reload(), 700);
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
        msg = str(e)
        # I parametri di accantonamento vivono su colonne aggiunte da una
        # migrazione. Se non e' stata ancora eseguita, dirlo invece di
        # rilanciare l'errore grezzo del database.
        if "column" in msg.lower() and any(c in msg for c in acc.PARAMETRI_CAMPI):
            return jsonify({
                "error": "Colonne mancanti su b2f_parametri_fiscali: esegui le "
                         "migrazioni documentate nel README nell'SQL Editor di "
                         "Supabase."
            }), 409
        return jsonify({"error": msg[:200]}), 500


# ---------------------------------------------------------------------------
# CRUD spese P.IVA
# ---------------------------------------------------------------------------

def _card_rivalsa(rivalsa: float, conto: dict) -> str:
    """
    Quanta parte del saldo P.IVA e' rivalsa INPS incassata dai clienti.

    Dentro il saldo la rivalsa e' invisibile: e' arrivata insieme al
    corrispettivo, in un unico bonifico, e da li' in poi e' un numero
    solo. Ma non e' un ricavo tuo: e' la parte destinata al contributo
    previdenziale, e deve restare su questo conto finche' non la versi.
    Qui si dice quanta e', e che e' gia' compresa nell'accantonamento —
    non e' una quota da mettere da parte in piu'.
    """
    saldo = float(conto.get("saldo") or 0)
    # Niente percentuale sul saldo: accanto a "rivalsa 4 %" un secondo
    # numero in percentuale si legge come l'aliquota e confonde. Meglio
    # il confronto in euro, che e' quello che serve davvero.
    quota = (f' Sul conto ci sono in tutto € {_fmt_eur(saldo)}.'
             if saldo > 0 else "")
    return f'''
    <div class="card mb-3">
      <div class="card-head">
        <div class="eyebrow">Rivalsa INPS incassata</div>
        <span class="chip accent">€ {_fmt_eur(rivalsa)}</span>
      </div>
      <p class="small muted">
        È la quota di rivalsa INPS 4 % già entrata su questo conto insieme
        agli incassi delle fatture.{quota} Non è un ricavo: è la parte del
        corrispettivo destinata al contributo previdenziale, e va lasciata
        qui fino al versamento.
      </p>
      <details class="explain mt-3">
        <summary>Devo accantonarla a parte?</summary>
        <p class="small muted mt-2">
          No: è già dentro. Nel forfettario l'imponibile è il corrispettivo
          intero, rivalsa compresa, quindi l'INPS calcolata
          sull'accantonamento (circa il 17,5 % del lordo) è più alta della
          rivalsa stessa (3,85 % del lordo) e la contiene. Metterla da parte
          una seconda volta significherebbe accantonare due volte lo stesso
          denaro. La ripartizione dell'incasso non scende mai sotto la
          rivalsa proprio per questo.
        </p>
      </details>
    </div>'''


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

    anno_o = "".join(f'<option value="{y}"{" selected" if y == anno else ""}>{y}</option>'
                     for y in range(anno_default, anno_default - 6, -1))
    toolbar = f'''
    <div class="toolbar">
      <select class="select-pill" aria-label="Anno"
        onchange="const u=new URL(location.href);u.searchParams.set('anno',this.value);location.href=u">
        {anno_o}
      </select>
      <select class="select-pill" aria-label="Categoria"
        onchange="const u=new URL(location.href);if(this.value){{u.searchParams.set('categoria',this.value)}}else{{u.searchParams.delete('categoria')}};location.href=u">
        <option value="">Tutte le categorie</option>{cat_opts}
      </select>
      <select class="select-pill" aria-label="Tipo"
        onchange="const u=new URL(location.href);if(this.value){{u.searchParams.set('tipo',this.value)}}else{{u.searchParams.delete('tipo')}};location.href=u">
        <option value="">Tutti i tipi</option>{tipo_opts}
      </select>
    </div>
    '''

    entrate = sum(float(r.get("importo") or 0) for r in rows if r.get("tipo") == "entrata")
    uscite = sum(float(r.get("importo") or 0) for r in rows if r.get("tipo") == "uscita")
    # I giroconti escono dal conto P.IVA verso il personale: non sono una
    # spesa (restano tuoi), ma il saldo deve vederli uscire, altrimenti
    # mostrerebbe soldi che sull'altro conto ci sono gia'.
    girati = sum(float(r.get("importo") or 0) for r in rows if r.get("tipo") == "giroconto")
    tot = entrate - uscite - girati

    # Il saldo qui sopra e' quello dell'anno filtrato. Il conto pero' non
    # riparte da zero a gennaio: dal secondo anno in poi i due numeri
    # divergono, e il primo non e' quello che c'e' in banca.
    conto = saldo_piva(sb)
    rivalsa = float(conto.get("rivalsa_incassata") or 0)
    riga_conto = ""
    if conto.get("disponibile"):
        rivalsa_hint = (f'di cui € {_fmt_eur(rivalsa, 0)} di rivalsa INPS incassata'
                        if rivalsa > 0 else "tutti i movimenti fino a oggi")
        riga_conto = f'''
      <div class="card"><div class="stat">
        <div class="val tnum {"pos" if conto["saldo"] >= 0 else "neg"}">€ {_fmt_eur(conto["saldo"], 0)}</div>
        <div class="lbl">Saldo del conto, oggi</div>
        <div class="hint">{rivalsa_hint}</div></div></div>'''

    riepilogo = f'''
    <div class="grid kpi lead mb-3">
      {riga_conto}
      <div class="card"><div class="stat">
        <div class="val tnum {"pos" if tot >= 0 else "neg"}">€ {_fmt_eur(tot, 0)}</div>
        <div class="lbl">Movimento netto {anno}</div>
        <div class="hint">al netto dei giroconti</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum pos">€ {_fmt_eur(entrate, 0)}</div>
        <div class="lbl">Entrate</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum neg">€ {_fmt_eur(uscite, 0)}</div>
        <div class="lbl">Uscite</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum">€ {_fmt_eur(girati, 0)}</div>
        <div class="lbl">Girati al personale</div></div></div>
    </div>
    {_card_rivalsa(rivalsa, conto) if rivalsa > 0 else ""}
    '''

    if not rows:
        body = f'''{riepilogo}{toolbar}
        <div class="empty">
          {_icon("wallet")}
          <div class="t">Nessun movimento per il {anno}</div>
          <div class="s">Aggiungi il primo con il pulsante in basso.</div>
        </div>'''
    else:
        cat_lbl = dict(CATEGORIE_SPESE_PIVA)
        items = []
        for m in rows:
            segno, cls = _movimento_label(m)
            cat = _esc(cat_lbl.get(m.get("categoria"), m.get("categoria") or "—"))
            items.append(f'''
            <a class="item" href="/fatture/spese-piva/{m["id"]}">
              <span class="ico {cls or "neutral"}">{_icon("wallet")}</span>
              <span class="body">
                <span class="n">{_esc(m.get("descrizione") or "—")}</span>
                <span class="m">{_fmt_date(m.get("data"))} · {cat}</span>
              </span>
              <span class="end">
                <span class="amt tnum {cls}">{segno} € {_fmt_eur(m.get("importo"))}</span>
              </span>
            </a>''')
        body = f'{riepilogo}{toolbar}<div class="list">{"".join(items)}</div>'

    return _render(body, eyebrow="Movimenti P.IVA", title_html='Movimenti <em>P.IVA</em>',
                   breadcrumb=breadcrumb, fab=("Nuovo movimento", "/fatture/spese-piva/nuova"))


def _movimento_form_html(m: dict | None = None, collegamento: dict | None = None) -> str:
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

    # Un movimento che fa parte di un giroconto non si tocca da qui: si
    # può solo, quando questa e' l'origine dello spostamento, eliminarlo
    # (cosa che porta via anche la contropartita). Le guardie vere stanno
    # nell'endpoint; qui e' solo per non lasciare che l'utente provi un
    # salvataggio che verrebbe comunque rifiutato.
    bloccato = bool(collegamento)
    delete_ok = (not bloccato) or bool(collegamento.get("delete_ok"))
    ro = " readonly disabled" if bloccato else ""

    avviso = (f'<div class="notice info mb-4">{collegamento["msg"]}</div>'
              if collegamento else "")
    submit_btn = ("" if bloccato else
                  f'<button type="button" class="btn" onclick="onSubmit({mid or "null"})">{submit_lbl}</button>')
    delete_btn = (f'<button type="button" class="btn danger" onclick="onElimina({mid})">Elimina</button>'
                  if is_edit and delete_ok else "")
    torna_btn = ('<a class="btn ghost" href="/fatture/spese-piva">Torna ai movimenti</a>'
                 if bloccato and not delete_ok else "")

    return f'''
    <div class="narrow">
    {avviso}
    <div class="card">
      <div class="field-group">
        <div class="field"><label>Data</label>
          <input type="date" id="f_data" value="{v('data', date.today().isoformat())}"{ro}></div>
        <div class="field"><label>Importo (€)</label>
          <input type="number" step="0.01" inputmode="decimal" id="f_importo" value="{v('importo', 0)}"{ro}></div>
      </div>
      <div class="field"><label>Tipo</label>
        <select id="f_tipo"{ro}>
          <option value="entrata"{" selected" if tipo_current=="entrata" else ""}>Entrata</option>
          <option value="uscita"{" selected" if tipo_current=="uscita" else ""}>Uscita</option>
          <option value="giroconto"{" selected" if tipo_current=="giroconto" else ""}>Giroconto</option>
        </select></div>
      <div class="field"><label>Descrizione</label>
        <input id="f_descrizione" value="{_esc(v('descrizione'))}"{ro}></div>
      <div class="field-group">
        <div class="field"><label>Categoria</label>
          <select id="f_categoria"{ro}><option value="">—</option>{cat_opts}</select></div>
        <div class="field"><label>Sottocategoria</label>
          <input id="f_sottocategoria" value="{_esc(v('sottocategoria'))}"{ro}></div>
      </div>
      <div class="field inline">
        <input type="checkbox" id="f_ricorrente" {"checked" if m.get("ricorrente") else ""}{ro}>
        <label for="f_ricorrente">Movimento ricorrente</label>
      </div>
      <div class="field"><label>Note</label>
        <textarea id="f_note"{ro}>{_esc(m.get('note'))}</textarea></div>
      <div class="actions">
        {submit_btn}
        {delete_btn}
        {torna_btn}
      </div>
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

    origine = _origine_ripartizione(sb, mid)
    if origine:
        collegamento = {
            "msg": (f'Questo movimento fa parte della ripartizione della fattura '
                    f'{origine.get("numero") or origine.get("id")}. Per toccarlo '
                    f'annulla la ripartizione dalla fattura: così spariscono '
                    f'entrambe le righe.'),
            "delete_ok": False,
        }
    elif m.get("giroconto_personale_id"):
        collegamento = {
            "msg": ("Questo movimento ha generato un'entrata sul conto "
                    "personale. Tipo e importo non si possono cambiare da "
                    "qui: eliminalo per annullare entrambe le righe."),
            "delete_ok": True,
        }
    else:
        collegamento = None

    return _render(_movimento_form_html(m, collegamento), eyebrow="Movimento",
                   title_html=f'<em>{_esc((m.get("descrizione") or "Movimento")[:20])}</em>',
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


def _origine_ripartizione(sb, mid: int) -> dict | None:
    """
    Se questo movimento e' la meta' P.IVA della ripartizione automatica
    di un incasso (fatture/giroconto.py), la fattura a cui appartiene.

    Non copre il legame piu' debole di `spesa_piva_id` (la semplice
    registrazione dell'incasso): quello si scioglie apposta eliminando
    il movimento da qui — vedi `_stacca_da_fattura`.
    """
    try:
        r = (sb.table("b2f_fatture").select("id, numero")
               .eq("giroconto_piva_id", mid).limit(1).execute())
        righe = r.data or []
        return righe[0] if righe else None
    except Exception:
        return None


def _stacca_da_fattura(sb, mid: int) -> None:
    """
    Se il movimento appena eliminato era la registrazione dell'incasso di
    una fattura, scioglie il collegamento: altrimenti la fattura resta a
    puntare a una riga sparita, "già registrata" per sempre.
    """
    try:
        sb.table("b2f_fatture").update({"spesa_piva_id": None}) \
          .eq("spesa_piva_id", mid).execute()
    except Exception:
        pass


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
        riga = r.data[0] if r.data else {}
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500

    id_piva = riga.get("id")
    if payload.get("tipo") != "giroconto" or not id_piva:
        return jsonify(riga)

    # Un giroconto sposta soldi anche sul conto personale: senza questa
    # riga il denaro sparirebbe dal conto P.IVA senza arrivare da nessuna
    # parte. Stessa garanzia della ripartizione automatica di una fattura
    # (fatture/giroconto.py), solo innescata a mano invece che dall'incasso.
    from spese import dati as personale
    esito = personale.crea(sb, {
        "data":              payload.get("data"),
        "tipo":              "entrata",
        "importo":           payload.get("importo"),
        "descrizione":       f'Giroconto da P.IVA — {payload.get("descrizione")}',
        "metodo_pagamento":  "Giroconto",
        "categoria_link_id": personale.link_categoria(
            sb, personale.CATEGORIA_GIROCONTO),
    })
    if esito.get("error") or not esito.get("id"):
        try:
            sb.table("b2f_spese_piva").delete().eq("id", id_piva).execute()
        except Exception:
            pass
        msg = esito.get("error") or "nessun id di ritorno"
        return jsonify({"error": f"errore sul conto personale: {msg}"}), 500

    try:
        upd = (sb.table("b2f_spese_piva")
                 .update({"giroconto_personale_id": esito["id"]})
                 .eq("id", id_piva).execute())
        riga = upd.data[0] if upd.data else riga
    except Exception as e:
        # Senza il collegamento le due righe si perdono di vista: meglio
        # annullare tutto che lasciarle scollegate.
        try:
            sb.table("b2f_spese_piva").delete().eq("id", id_piva).execute()
        except Exception:
            pass
        try:
            personale.elimina(sb, esito["id"])
        except Exception:
            pass
        msg = str(e)
        if "column" in msg.lower() and "giroconto_personale_id" in msg:
            return jsonify({"error": (
                "Manca la colonna giroconto_personale_id su b2f_spese_piva: "
                "esegui la migrazione documentata nel README.")}), 409
        return jsonify({"error": f"collegamento fallito: {msg[:200]}"}), 500

    return jsonify(riga)


@fatture_bp.patch("/api/spese-piva/<int:mid>")
def api_spesa_piva_update(mid):
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503

    origine = _origine_ripartizione(sb, mid)
    if origine:
        return jsonify({"error": (
            f'Questo movimento fa parte della ripartizione della fattura '
            f'{origine.get("numero") or origine.get("id")}: per cambiarlo '
            f'annulla la ripartizione dalla fattura, così spariscono entrambe '
            f'le righe.')}), 409

    try:
        r = sb.table("b2f_spese_piva").select("giroconto_personale_id") \
              .eq("id", mid).single().execute()
        collegato_manuale = (r.data or {}).get("giroconto_personale_id")
    except Exception:
        collegato_manuale = None

    data = request.get_json(silent=True) or {}
    if collegato_manuale and ("tipo" in data or "importo" in data):
        return jsonify({"error": (
            "Questo movimento ha generato un'entrata sul conto personale: "
            "tipo e importo non si possono cambiare da qui, per non "
            "disallineare i due conti. Eliminalo e registrane uno nuovo se "
            "serve un altro importo.")}), 409

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

    origine = _origine_ripartizione(sb, mid)
    if origine:
        return jsonify({"error": (
            f'Questo movimento fa parte della ripartizione della fattura '
            f'{origine.get("numero") or origine.get("id")}: annulla la '
            f'ripartizione dalla fattura, così spariscono entrambe le righe.'
        )}), 409

    try:
        r = sb.table("b2f_spese_piva").select("giroconto_personale_id") \
              .eq("id", mid).single().execute()
        id_personale = (r.data or {}).get("giroconto_personale_id")
    except Exception:
        id_personale = None

    if id_personale:
        # Il giroconto e' nato da qui: eliminarlo toglie anche la
        # contropartita sul personale, altrimenti resterebbe un'entrata
        # senza piu' nessuna uscita dal conto P.IVA a spiegarla.
        from spese import dati as personale
        esito = personale.elimina(sb, id_personale)
        if esito.get("error"):
            return jsonify({"error": (
                "Non sono riuscito a togliere l'entrata collegata sul conto "
                f"personale: {esito['error']}")}), 500

    try:
        sb.table("b2f_spese_piva").delete().eq("id", mid).execute()
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500

    _stacca_da_fattura(sb, mid)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _render(content: str, eyebrow: str = "Situazione fiscale",
            title_html: str = 'Situazione <em>fiscale</em>',
            breadcrumb=None, fab=None, actions_html: str = "") -> Response:
    html = render_page(
        section="fatture", eyebrow=eyebrow, title_html=title_html,
        content=content, breadcrumb=breadcrumb, fab=fab,
        actions_html=actions_html,
    )
    return Response(html, mimetype="text/html")
