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

    costi  = round(lordo * costi_perc, 2)
    margine = round(round(inps + imposta, 2) * margine_perc, 2)

    # Gli acconti dell'anno successivo che questo incasso si tira dietro:
    # e' la quota per cui, l'anno in cui saldo e acconti cadono insieme,
    # servono due annualita' invece di una.
    acconto_inps = round(lordo * a["acconto_inps"], 2)
    acconto_imposta = round(lordo * a["acconto_imposta"], 2)
    acconti_pieni = round(acconto_inps + acconto_imposta, 2)
    acconti_meta = round(acconti_pieni * PRUDENTE_QUOTA_ACCONTI, 2)

    # OGNI SCENARIO E' UNA SOMMA DI VOCI DICHIARATE, non un numero a se'.
    # Prima gli importi si calcolavano ciascuno per conto suo e la card
    # mostrava il resto sotto un'unica etichetta "Costi e margine" — che
    # per "prudente" e "sicuro" conteneva in realta' la quota acconti,
    # cioe' l'unica voce che dice quanto stai tenendo per l'anno dopo.
    # Tenendo le voci esplicite, il totale non puo' piu' contenere niente
    # che non sia nominato, e la card puo' dirlo riga per riga.
    componenti = {
        "minimo":      {"inps": inps, "imposta": imposta,
                        "acconti": 0.0, "costi": 0.0, "margine": 0.0},
        "consigliato": {"inps": inps, "imposta": imposta,
                        "acconti": 0.0, "costi": costi, "margine": margine},
        "prudente":    {"inps": inps, "imposta": imposta,
                        "acconti": acconti_meta, "costi": costi, "margine": margine},
        # "sicuro" non ha margine: il margine c'e' gia', ed e' l'anno
        # intero di acconti che sta mettendo da parte.
        "sicuro":      {"inps": inps, "imposta": imposta,
                        "acconti": acconti_pieni, "costi": costi, "margine": 0.0},
    }
    importi = {k: round(sum(v.values()), 2) for k, v in componenti.items()}

    return {
        "lordo": round(lordo, 2),
        "rivalsa": round(float(rivalsa or 0), 2),
        "bollo_addebitato": round(float(bollo_addebitato or 0), 2),
        "coeff": coeff,
        "imponibile": imponibile,
        "inps": inps,
        "imposta": imposta,
        "acconto_inps": acconto_inps,
        "acconto_imposta": acconto_imposta,
        # Quanto di acconti questo incasso porta con se', in totale: e' il
        # metro su cui si misura la copertura di ogni scenario.
        "acconti_dovuti": acconti_pieni,
        # Le due percentuali con cui si calcolano gli acconti (INPS 80 %,
        # imposta 100 % di default). Servono all'etichetta della card:
        # sono parametri, non costanti, e scritte a mano invecchierebbero.
        "aliquote_acconto": {
            "inps": _f(param, "aliquota_acconto", 0.80),
            "imposta": _f(param, "acconto_imposta_perc", 1.00),
        },
        "costi_fissi": costi,
        "margine": margine,
        "componenti": componenti,
        # Quanto resta scoperto degli acconti, scenario per scenario.
        "acconti_scoperti": {k: round(acconti_pieni - v["acconti"], 2)
                             for k, v in componenti.items()},
        "importi": importi,
        "netti": {k: round(lordo - v, 2) for k, v in importi.items()},
        # Le aliquote effettive escono dagli importi, non da una seconda
        # catena di formule: cosi' non possono divergere dal totale
        # mostrato accanto.
        "aliquote": {
            **{k: ((importi[k] / lordo) if lordo else 0.0) for k in SCENARI},
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
              contesto: str = "", uid: str = "acc",
              anno_acconto: int | None = None) -> str:
    """
    Card con il numero da mettere da parte, il selettore di scenario e la
    scomposizione visiva dell'incasso.

    `s` e' il dizionario restituito da scomponi(). `uid` distingue piu'
    card nella stessa pagina. `anno_acconto` e' l'anno a cui si riferiscono
    gli acconti (quello dopo l'incasso): serve solo alle etichette — senza,
    si dice "anno prossimo".

    LA RIGA DEGLI ACCONTI E' IL MOTIVO PER CUI QUESTA CARD ESISTE COSI'.
    Il numero grande da solo non dice la cosa piu' importante: di quello
    che stai mettendo da parte, quanto e' saldo di quest'anno e quanto e'
    acconto per l'anno prossimo. Sono due debiti diversi, con due
    scadenze diverse, e "consigliato" — lo scenario di default — del
    secondo non tiene NIENTE. Finche' restava dentro un segmento
    chiamato "Costi e margine", quella scoperta la si faceva a giugno.
    """
    from shared.fmt import eur, pct

    lordo = s["lordo"] or 0.0
    pref = s["scenario_preferito"]
    comp = s["componenti"]
    dovuti = s["acconti_dovuti"]
    etichetta_anno = f"del {anno_acconto}" if anno_acconto else "dell'anno prossimo"

    seg = "".join(
        f'<button type="button" data-acc="{uid}" data-scen="{k}"'
        f'{" class=\"is-active\"" if k == pref else ""}>{ETICHETTE[k][0]}</button>'
        for k in SCENARI
    )

    # Percentuali per la barra: quote del lordo. Il resto e' "tuo".
    def q(v):
        return (v / lordo * 100) if lordo else 0.0

    def extra(k):
        """Costi fissi + margine: quello che non e' tassa ne' acconto."""
        return round(comp[k]["costi"] + comp[k]["margine"], 2)

    def frase_acconti(k):
        """La riga che risponde a «e per l'anno prossimo?»."""
        messo = comp[k]["acconti"]
        scoperto = s["acconti_scoperti"][k]
        if dovuti <= 0:
            return ""
        if messo <= 0:
            return (f'<strong>Per gli acconti {etichetta_anno} non tiene niente.</strong> '
                    f'Restano scoperti € {eur(scoperto)}, che serviranno '
                    f'nell\'anno in cui saldo e acconti cadono insieme.')
        if scoperto <= 0:
            return (f'<strong>Gli acconti {etichetta_anno} sono dentro per intero:</strong> '
                    f'€ {eur(messo)} di questa cifra non sono per quest\'anno.')
        return (f'<strong>Di questi, € {eur(messo)} sono acconti {etichetta_anno}.</strong> '
                f'Ne restano scoperti € {eur(scoperto)}.')

    def copertura(k):
        return (comp[k]["acconti"] / dovuti) if dovuti > 0 else 0.0

    def classe_acconti(k):
        c = copertura(k)
        return "neg" if c <= 0 else ("pos" if c >= 0.999 else "warn")

    ctx = f'<div class="stat-hint muted small">{contesto}</div>' if contesto else ""

    import json
    dati = json.dumps({
        "lordo": lordo,
        "importi": s["importi"],
        "netti": s["netti"],
        "aliquote": {k: s["aliquote"][k] for k in SCENARI},
        "inps": s["inps"],
        "imposta": s["imposta"],
        "dovuti": dovuti,
        "acconti": {k: comp[k]["acconti"] for k in SCENARI},
        "scoperti": {k: s["acconti_scoperti"][k] for k in SCENARI},
        "extra": {k: extra(k) for k in SCENARI},
        "extraCosti": {k: comp[k]["costi"] for k in SCENARI},
        "extraMargine": {k: comp[k]["margine"] for k in SCENARI},
        "copertura": {k: copertura(k) for k in SCENARI},
        "frasi": {k: frase_acconti(k) for k in SCENARI},
        "classi": {k: classe_acconti(k) for k in SCENARI},
    }, ensure_ascii=False)

    riga_acconti = ""
    if dovuti > 0:
        riga_acconti = f'''
  <div class="acc-acconti {classe_acconti(pref)}" data-acc-acconti="{uid}">
    <i class="dot acconti" aria-hidden="true"></i>
    <span data-acc-frase="{uid}">{frase_acconti(pref)}</span>
  </div>'''

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
    <span class="seg-acconti" data-acc-bar-acconti="{uid}" style="width:{q(comp[pref]['acconti']):.2f}%"></span>
    <span data-acc-bar-extra="{uid}" style="background:var(--ink-4);width:{q(extra(pref)):.2f}%"></span>
  </div>
  <div class="legend">
    <div><i class="dot" style="background:var(--pos)"></i>Tuoi</div>
    <div><i class="dot" style="background:var(--accent)"></i>INPS € {eur(s["inps"])}</div>
    <div><i class="dot" style="background:var(--warn)"></i>Imposta € {eur(s["imposta"])}</div>
    <div data-acc-leg-acconti="{uid}"><i class="dot acconti"></i>Acconti {etichetta_anno} € {eur(comp[pref]["acconti"])}</div>
    <div data-acc-leg-extra="{uid}"><i class="dot" style="background:var(--ink-4)"></i>Costi e margine € {eur(extra(pref))}</div>
  </div>
{riga_acconti}
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
      <div class="row"><span class="t"><strong>Saldo di quest'anno</strong> <span class="sub">quello che si paga a giugno prossimo</span></span>
        <span class="v tnum"><strong>€ {eur(s["importi"]["minimo"])}</strong></span></div>
      <div class="row"><span class="t">Acconti {etichetta_anno} <span class="sub">INPS {pct(s["aliquote_acconto"]["inps"], 0)}, imposta {pct(s["aliquote_acconto"]["imposta"], 0)} del dovuto: si versano nello stesso anno del saldo qui sopra</span></span>
        <span class="v tnum">€ {eur(dovuti)}</span></div>
      <div class="row"><span class="t">— di cui coperti da questo scenario</span>
        <span class="v tnum" data-acc-row-acconti="{uid}">€ {eur(comp[pref]["acconti"])}</span></div>
      <div class="row"><span class="t">— ancora scoperti <span class="sub">da trovare altrove, o con uno scenario più alto</span></span>
        <span class="v tnum" data-acc-row-scoperti="{uid}">€ {eur(s["acconti_scoperti"][pref])}</span></div>
      <div class="row"><span class="t">Costi fissi pro-quota</span>
        <span class="v tnum" data-acc-row-costi="{uid}">€ {eur(comp[pref]["costi"])}</span></div>
      <div class="row"><span class="t">Margine di sicurezza</span>
        <span class="v tnum" data-acc-row-margine="{uid}">€ {eur(comp[pref]["margine"])}</span></div>
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
  var el = function(sel){{ return document.querySelector('[' + sel + '="' + uid + '"]'); }};

  function pick(scen){{
    el('data-acc-val').textContent   = '\u20ac ' + fmt(D.importi[scen]);
    el('data-acc-pct').textContent   = pctFmt(D.aliquote[scen]);
    el('data-acc-netto').textContent = '\u20ac ' + fmt(D.netti[scen]);
    el('data-acc-bar-netto').style.width = q(D.netti[scen]).toFixed(2) + '%';
    el('data-acc-bar-acconti').style.width = q(D.acconti[scen]).toFixed(2) + '%';
    el('data-acc-bar-extra').style.width = q(D.extra[scen]).toFixed(2) + '%';

    // Le due legende reattive: il testo dice l'importo dello scenario
    // scelto, non quello con cui la pagina e' nata.
    el('data-acc-leg-acconti').lastChild.textContent =
      ' Acconti {etichetta_anno} \u20ac ' + fmt(D.acconti[scen]);
    el('data-acc-leg-extra').lastChild.textContent =
      ' Costi e margine \u20ac ' + fmt(D.extra[scen]);

    ['acconti', 'scoperti', 'costi', 'margine'].forEach(function(k){{
      var r = el('data-acc-row-' + k);
      if (!r) return;
      var v = (k === 'scoperti') ? D.scoperti[scen]
            : (k === 'acconti')  ? D.acconti[scen]
            : (k === 'costi')    ? D.extraCosti[scen]
            :                      D.extraMargine[scen];
      r.textContent = '\u20ac ' + fmt(v);
    }});

    var box = el('data-acc-acconti');
    if (box) {{
      box.className = 'acc-acconti ' + D.classi[scen];
      el('data-acc-frase').innerHTML = D.frasi[scen];
    }}

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
