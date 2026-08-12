"""
fatture/accantonamento.py — Quanto mettere da parte di un incasso.

IL PROBLEMA
-----------
Nel forfettario le tasse si pagano per cassa: quando incassi una fattura,
una parte di quei soldi non e' tua. Il conto matematico e' semplice, ma
il conto matematico da solo e' una pessima guida all'accantonamento,
per due motivi che qui vengono resi espliciti.

LA MATEMATICA
-------------
Su un incasso lordo L (totale della fattura, rivalsa e bollo riaddebitati
inclusi: entrambi concorrono al reddito):

    Imponibile   I = L x coeff_ateco                       (0,67)
    INPS         C = I x aliquota_inps                     (26,07 %)
    Imposta      T = (I - C) x aliquota_imposta            (5 %)

I contributi previdenziali sono deducibili, per questo l'imposta si
calcola su (I - C) e non su I.

    Dovuto = C + T

In percentuale sul lordo, con i parametri di default:
    C/L = 0,67 x 0,2607                = 17,47 %
    T/L = 0,67 x (1-0,2607) x 0,05     =  2,48 %
    ------------------------------------------------
    Dovuto                             = 19,94 %

PERCHE' 19,94 % NON E' LA CIFRA DA METTERE DA PARTE
---------------------------------------------------
1. Gli acconti. Il saldo dell'anno N si paga a giugno N+1, ma nello
   stesso anno solare si versano anche gli acconti per l'anno N+1
   (INPS all'80 % col metodo storico, imposta sostitutiva al 100 %).
   A regime gli acconti si scomputano dal saldo successivo e l'uscita
   annua torna a essere una sola annualita' — ma nell'anno di
   transizione le due cose cadono insieme e il fabbisogno di cassa e':

       1,8 x C + 2 x T  =  36,39 % del lordo

2. I costi fissi. Commercialista, PEC, bolli, commissioni: non sono
   tasse, ma sono uscite certe che escono dagli stessi soldi.

I QUATTRO SCENARI
-----------------
    minimo       C + T                          il puro dovuto, margine zero
    consigliato  minimo x (1+margine) + costi   quello che l'app evidenzia
    prudente     minimo + meta' acconti
                 + costi + margine              la via di mezzo
    sicuro       1,8C + 2T + costi              copre l'anno degli acconti

Perche' esiste "prudente": fra consigliato (~22 %) e sicuro (~36 %) c'e'
un salto grosso, e immobilizzare il 36 % di ogni incasso e' pesante se
l'anno degli acconti non e' imminente. "Prudente" mette da parte il
dovuto pieno piu' meta' degli acconti: ci arrivi in due anni invece che
in uno, senza scoprirti del tutto.

Il margine di sicurezza, i costi fissi annui e il fatturato atteso sono
parametri modificabili in /fatture/parametri.
"""

# Parametri specifici dell'accantonamento, con i loro default. Vengono
# uniti a quelli fiscali generali (coefficiente, aliquote, ...).
PARAMETRI_DEFAULT = {
    "margine_sicurezza": 0.10,       # cuscinetto relativo sul dovuto
    "costi_fissi_annui": 0.0,        # commercialista + PEC + varie
    "fatturato_atteso_anno": 0.0,    # 0 = stimalo dai dati dell'anno
    "acconto_imposta_perc": 1.00,    # acconto imposta sostitutiva (100 %)
    "scenario_preferito": "consigliato",
}

PARAMETRI_CAMPI = tuple(PARAMETRI_DEFAULT.keys())

SCENARI = ("minimo", "consigliato", "prudente", "sicuro")

ETICHETTE = {
    "minimo":      ("Minimo", "Il puro dovuto: nessun margine, nessun costo fisso coperto."),
    "consigliato": ("Consigliato", "Dovuto + costi fissi pro-quota + margine di sicurezza."),
    "prudente":    ("Prudente", "Dovuto + metà degli acconti + costi + margine: ci arrivi in due anni."),
    "sicuro":      ("Sicuro", "Copre anche l'anno in cui saldo e acconti cadono insieme."),
}

# Quota degli acconti coperta dallo scenario "prudente". A 0,5 il
# fabbisogno dell'anno-picco si accumula in due anni invece che in uno.
PRUDENTE_QUOTA_ACCONTI = 0.5


def _f(param: dict, chiave: str, default: float) -> float:
    """Legge un parametro numerico con fallback, tollerando None e stringhe."""
    v = param.get(chiave, default)
    if v is None or v == "":
        return float(default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def aliquote(param: dict) -> dict:
    """
    Aliquote effettive **sul lordo incassato**, non sull'imponibile.
    Sono i numeri che servono per dire "di 100 euro incassati, X sono
    del fisco" senza rifare ogni volta la catena di moltiplicazioni.
    """
    coeff     = _f(param, "coeff_ateco", 0.67)
    aliq_inps = _f(param, "aliquota_inps", 0.2607)
    aliq_imp  = _f(param, "aliquota_imposta", 0.05)
    acc_inps  = _f(param, "aliquota_acconto", 0.80)
    acc_imp   = _f(param, "acconto_imposta_perc", 1.00)

    q_inps    = coeff * aliq_inps
    q_imposta = coeff * (1.0 - aliq_inps) * aliq_imp
    dovuto    = q_inps + q_imposta
    picco     = q_inps * (1.0 + acc_inps) + q_imposta * (1.0 + acc_imp)

    return {
        "inps": q_inps,
        "imposta": q_imposta,
        "dovuto": dovuto,
        "picco_cassa": picco,
        "acconto_inps": q_inps * acc_inps,
        "acconto_imposta": q_imposta * acc_imp,
    }


def quota_costi_fissi(param: dict, fatturato_riferimento: float = 0.0) -> float:
    """
    Frazione del lordo da riservare per i costi fissi annui.

    Si spalmano i costi sul fatturato atteso dell'anno. Se il parametro
    `fatturato_atteso_anno` non e' impostato si usa il fatturato reale
    passato da chi chiama (tipicamente l'incassato dell'anno in corso).
    Senza nessuno dei due la quota e' zero: meglio non inventare.
    """
    costi = _f(param, "costi_fissi_annui", 0.0)
    if costi <= 0:
        return 0.0
    base = _f(param, "fatturato_atteso_anno", 0.0) or float(fatturato_riferimento or 0)
    if base <= 0:
        return 0.0
    return min(costi / base, 0.5)   # tetto di sicurezza: mai oltre il 50 %


def scomponi(lordo: float, param: dict, fatturato_riferimento: float = 0.0,
            rivalsa: float = 0.0, bollo_addebitato: float = 0.0) -> dict:
    """
    Scompone un incasso lordo e calcola i tre scenari di accantonamento.

    Args:
      lordo: importo incassato (totale fattura).
      param: parametri fiscali uniti a quelli di accantonamento.
      fatturato_riferimento: base su cui spalmare i costi fissi, usata
        solo se `fatturato_atteso_anno` non e' impostato.
      rivalsa, bollo_addebitato: gia' inclusi in `lordo` (concorrono al
        reddito, vedi il modulo — Risposta Agenzia Entrate 428/2022 per
        il bollo). Non entrano in nessun calcolo qui: servono solo a
        `card_html()` per mostrarne la quota, a scopo di trasparenza.
    """
    try:
        lordo = float(lordo or 0)
    except (TypeError, ValueError):
        lordo = 0.0

    a = aliquote(param)
    margine_perc = _f(param, "margine_sicurezza", 0.10)
    costi_perc = quota_costi_fissi(param, fatturato_riferimento)

    coeff = _f(param, "coeff_ateco", 0.67)
    imponibile = round(lordo * coeff, 2)
    inps       = round(lordo * a["inps"], 2)
    imposta    = round(lordo * a["imposta"], 2)

    minimo = round(inps + imposta, 2)
    costi  = round(lordo * costi_perc, 2)
    margine = round(minimo * margine_perc, 2)
    consigliato = round(minimo + costi + margine, 2)
    sicuro = round(lordo * a["picco_cassa"] + costi, 2)
    # Via di mezzo: il dovuto pieno piu' una frazione degli acconti.
    # `picco_cassa - dovuto` e' esattamente la quota-acconti sul lordo.
    quota_acconti = max(a["picco_cassa"] - a["dovuto"], 0.0)
    prudente = round(
        lordo * (a["dovuto"] + PRUDENTE_QUOTA_ACCONTI * quota_acconti)
        + costi + margine, 2)

    importi = {"minimo": minimo, "consigliato": consigliato,
               "prudente": prudente, "sicuro": sicuro}

    return {
        "lordo": round(lordo, 2),
        "rivalsa": round(float(rivalsa or 0), 2),
        "bollo_addebitato": round(float(bollo_addebitato or 0), 2),
        "coeff": coeff,
        "imponibile": imponibile,
        "inps": inps,
        "imposta": imposta,
        "acconto_inps": round(lordo * a["acconto_inps"], 2),
        "acconto_imposta": round(lordo * a["acconto_imposta"], 2),
        "costi_fissi": costi,
        "margine": margine,
        "importi": importi,
        "netti": {k: round(lordo - v, 2) for k, v in importi.items()},
        "aliquote": {
            "minimo": a["dovuto"],
            "consigliato": (consigliato / lordo) if lordo else 0.0,
            "prudente": (prudente / lordo) if lordo else 0.0,
            "sicuro": (sicuro / lordo) if lordo else 0.0,
            "inps": a["inps"],
            "imposta": a["imposta"],
        },
        "scenario_preferito": (param.get("scenario_preferito")
                               if param.get("scenario_preferito") in SCENARI
                               else "consigliato"),
    }


def totali_periodo(incassato: float, param: dict,
                   fatturato_riferimento: float = 0.0) -> dict:
    """Stessa scomposizione applicata a un aggregato (mese, anno)."""
    return scomponi(incassato, param, fatturato_riferimento)


# ---------------------------------------------------------------------------
# Presentazione
def _riga_rivalsa_bollo(s: dict) -> str:
    """
    Riga informativa: quanto del lordo e' rivalsa INPS o bollo addebitato
    al cliente. Non cambia nessun conto (sono gia' dentro "lordo" e
    "imponibile" — concorrono al reddito, vedi scomponi()): serve solo a
    far vedere la composizione, non lasciarla nascosta dentro un unico
    numero. Non renderizza nulla se la fattura non li ha.
    """
    from shared.fmt import eur
    rivalsa = s.get("rivalsa", 0)
    bollo = s.get("bollo_addebitato", 0)
    if not rivalsa and not bollo:
        return ""
    righe = ""
    if rivalsa:
        righe += (f'<div class="row"><span class="t">di cui rivalsa INPS '
                  f'<span class="sub">inclusa nel lordo, concorre al reddito</span></span>'
                  f'<span class="v tnum">€ {eur(rivalsa)}</span></div>')
    if bollo:
        righe += (f'<div class="row"><span class="t">di cui bollo addebitato al cliente '
                  f'<span class="sub">inclusa nel lordo, concorre al reddito</span></span>'
                  f'<span class="v tnum">€ {eur(bollo)}</span></div>')
    return righe


# ---------------------------------------------------------------------------

def card_html(s: dict, titolo: str = "Da accantonare",
              contesto: str = "", uid: str = "acc") -> str:
    """
    Card con il numero da mettere da parte, il selettore di scenario e la
    scomposizione visiva dell'incasso.

    `s` e' il dizionario restituito da scomponi(). `uid` distingue piu'
    card nella stessa pagina.
    """
    from shared.fmt import eur, pct

    lordo = s["lordo"] or 0.0
    pref = s["scenario_preferito"]

    seg = "".join(
        f'<button type="button" data-acc="{uid}" data-scen="{k}"'
        f'{" class=\"is-active\"" if k == pref else ""}>{ETICHETTE[k][0]}</button>'
        for k in SCENARI
    )

    # Percentuali per la barra: quote del lordo. Il resto e' "tuo".
    def q(v):
        return (v / lordo * 100) if lordo else 0.0

    # Ultimo segmento della barra ("Costi e margine"): il resto di
    # importi[pref] oltre INPS e imposta. Non e' sempre costi_fissi+margine
    # in senso stretto — per "prudente"/"sicuro" include anche la quota
    # acconti — ma e' esattamente cosi' che lo ricalcola pick() lato client
    # quando si cambia scenario: se qui si usasse sempre costi_fissi+margine
    # (validi solo per "consigliato"), il rendering iniziale di uno
    # scenario diverso da quello di default non tornerebbe con il totale.
    extra_pref = max(s["importi"][pref] - s["inps"] - s["imposta"], 0.0)

    ctx = f'<div class="stat-hint muted small">{contesto}</div>' if contesto else ""

    import json
    dati = json.dumps({
        "lordo": lordo,
        "importi": s["importi"],
        "netti": s["netti"],
        "aliquote": {k: s["aliquote"][k] for k in SCENARI},
        "inps": s["inps"],
        "imposta": s["imposta"],
        "costi": s["costi_fissi"],
        "margine": s["margine"],
    }, ensure_ascii=False)

    return f'''
<div class="card acc-card" id="{uid}">
  <div class="card-head">
    <div class="eyebrow">{titolo}</div>
    <div class="segmented acc-seg">{seg}</div>
  </div>

  <div class="acc-main">
    <div class="stat">
      <div class="val accent tnum" data-acc-val="{uid}">€ {eur(s["importi"][pref])}</div>
      <div class="lbl">
        <span data-acc-pct="{uid}">{pct(s["aliquote"][pref])}</span> di € {eur(lordo)} incassati
      </div>
    </div>
    <div class="acc-netto">
      <div class="lbl muted small">Restano tuoi</div>
      <div class="tnum h2" data-acc-netto="{uid}">€ {eur(s["netti"][pref])}</div>
    </div>
  </div>

  <div class="bar-split mt-4" aria-hidden="true">
    <span data-acc-bar-netto="{uid}" style="background:var(--pos);width:{q(s['netti'][pref]):.2f}%"></span>
    <span style="background:var(--accent);width:{q(s['inps']):.2f}%"></span>
    <span style="background:var(--warn);width:{q(s['imposta']):.2f}%"></span>
    <span data-acc-bar-extra="{uid}" style="background:var(--ink-4);width:{q(extra_pref):.2f}%"></span>
  </div>
  <div class="legend">
    <div><i class="dot" style="background:var(--pos)"></i>Tuoi</div>
    <div><i class="dot" style="background:var(--accent)"></i>INPS € {eur(s["inps"])}</div>
    <div><i class="dot" style="background:var(--warn)"></i>Imposta € {eur(s["imposta"])}</div>
    <div data-acc-extra-legend="{uid}"><i class="dot" style="background:var(--ink-4)"></i>Costi e margine € {eur(extra_pref)}</div>
  </div>
  {ctx}

  <details class="explain mt-4">
    <summary>Come esce questo numero</summary>
    <div class="rows">
      {_riga_rivalsa_bollo(s)}
      <div class="row"><span class="t">Imponibile <span class="sub">lordo × coefficiente {pct(s.get("coeff", 0.67), 0)}</span></span>
        <span class="v tnum">€ {eur(s["imponibile"])}</span></div>
      <div class="row"><span class="t">INPS gestione separata</span>
        <span class="v tnum">€ {eur(s["inps"])}</span></div>
      <div class="row"><span class="t">Imposta sostitutiva <span class="sub">calcolata al netto dei contributi, che sono deducibili</span></span>
        <span class="v tnum">€ {eur(s["imposta"])}</span></div>
      <div class="row"><span class="t"><strong>Dovuto</strong></span>
        <span class="v tnum"><strong>€ {eur(s["importi"]["minimo"])}</strong></span></div>
      <div class="row"><span class="t">Acconti dell'anno successivo <span class="sub">INPS all'80 %, imposta al 100 %: nell'anno di transizione cadono insieme al saldo</span></span>
        <span class="v tnum">€ {eur(s["acconto_inps"] + s["acconto_imposta"])}</span></div>
      <div class="row"><span class="t">Costi fissi pro-quota</span>
        <span class="v tnum">€ {eur(s["costi_fissi"])}</span></div>
      <div class="row"><span class="t">Margine di sicurezza</span>
        <span class="v tnum">€ {eur(s["margine"])}</span></div>
    </div>
  </details>
</div>

<script>
(function(){{
  var uid = {uid!r};
  var D = {dati};
  var fmt = function(v){{ return new Intl.NumberFormat('it-IT',
    {{minimumFractionDigits:2, maximumFractionDigits:2}}).format(v); }};
  var pctFmt = function(v){{ return (v*100).toFixed(1).replace('.',',') + '%'; }};
  var q = function(v){{ return D.lordo ? (v / D.lordo * 100) : 0; }};

  function pick(scen){{
    var el = function(sel){{ return document.querySelector('[' + sel + '="' + uid + '"]'); }};
    el('data-acc-val').textContent   = '€ ' + fmt(D.importi[scen]);
    el('data-acc-pct').textContent   = pctFmt(D.aliquote[scen]);
    el('data-acc-netto').textContent = '€ ' + fmt(D.netti[scen]);
    el('data-acc-bar-netto').style.width = q(D.netti[scen]).toFixed(2) + '%';
    var extra = D.importi[scen] - D.inps - D.imposta;
    el('data-acc-bar-extra').style.width = q(Math.max(extra, 0)).toFixed(2) + '%';
    el('data-acc-extra-legend').innerHTML =
      '<i class="dot" style="background:var(--ink-4)"></i>Costi e margine € ' + fmt(Math.max(extra, 0));
    document.querySelectorAll('[data-acc="' + uid + '"]').forEach(function(b){{
      b.classList.toggle('is-active', b.dataset.scen === scen);
    }});
  }}

  document.querySelectorAll('[data-acc="' + uid + '"]').forEach(function(b){{
    b.addEventListener('click', function(){{ pick(b.dataset.scen); }});
  }});
}})();
</script>
'''
