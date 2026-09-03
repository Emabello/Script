"""
fatture/accantonamento.py — Quanto mettere da parte di un incasso.

IL PROBLEMA
-----------
Nel forfettario le tasse si pagano per cassa: quando incassi una fattura,
una parte di quei soldi non e' tua. Il conto matematico e' semplice, ma
il conto matematico da solo e' una pessima guida all'accantonamento.

LA MATEMATICA
-------------
Su un incasso lordo L (totale della fattura, rivalsa e bollo riaddebitati
inclusi: entrambi concorrono al reddito):

    Imponibile   I = L x coeff_ateco                       (0,67)
    INPS         C = I x aliquota_inps                     (26,07 %)
    Imposta      T = (I - C) x aliquota_imposta            (5 %)

I contributi previdenziali sono deducibili, per questo l'imposta si
calcola su (I - C) e non su I.

    Saldo dell'anno = C + T                                (19,94 % di L)

IL PRIMO ANNO NON HA CONTRIBUTI DA DEDURRE
------------------------------------------
La deduzione vale per i contributi **versati**, per cassa (art. 1 c. 64
L. 190/2014). Nell'anno in cui apri la partita IVA non versi niente —
il primo versamento cade a giugno dell'anno dopo — quindi in quell'anno
non c'e' niente da dedurre e l'imposta si calcola sull'imponibile pieno:

    anno di apertura   T = I x aliquota_imposta            (3,35 % di L)
    dagli anni dopo    T = (I - C) x aliquota_imposta      (2,48 % di L)

Sono 0,87 punti di L sul saldo e altrettanti sull'acconto imposta: in
totale il primo anno costa **1,75 punti in piu'** di quanto direbbe la
formula a regime. Calcolarlo con la deduzione anche il primo anno
sottostima il fabbisogno, ed e' l'unica direzione dell'errore che fa
male. Serve `anno` e `data_apertura_piva` per saperlo: senza, si assume
il caso a regime.

Dal secondo anno il modello resta a una annualita' di contributi dedotti,
mentre nella realta' nel secondo anno se ne versano circa 1,8 (saldo del
primo piu' acconti del secondo). L'errore in quel caso e' **verso
l'alto** — accantoni un po' piu' del dovuto — e va bene cosi'.

GLI ACCONTI, CHE SONO IL VERO MOTIVO PER CUI SERVE UN MODELLO
-------------------------------------------------------------
Il saldo dell'anno N si paga a giugno N+1, ma nello stesso anno solare si
versano anche gli acconti per l'anno N+1 (INPS all'80 % col metodo
storico, imposta sostitutiva al 100 %). Il fabbisogno di cassa e' quindi:

    Fabbisogno fiscale = saldo + acconti = C + T + 0,8C + T

       a regime          36,39 % di L
       anno di apertura  38,14 % di L

DUE SCADENZE, NON UNA
---------------------
Il fabbisogno non serve tutto insieme, e sapere QUANDO serve e' meta'
della risposta: e' quello che decide quanto devi avere liquido a giugno
e quanto a novembre.

    30 giugno anno+1     saldo dell'anno + prima rata degli acconti
    (di norma prorogato   (40 %, `acconto_prima_rata_perc`)
     al 31 luglio)
    30 novembre anno+1   seconda rata degli acconti (il resto, 60 %)

La quota della prima rata e' un parametro e non una costante: la soglia
sotto cui l'acconto si versa in unica rata a novembre, e le proroghe, le
decide il commercialista. Mettendolo a 0 si torna esattamente al modello
precedente — acconto tutto a novembre — senza toccare il codice.

A regime gli acconti si scomputano dal saldo successivo, e a fatturato
costante l'uscita annua torna a essere una annualita' sola. Ma quel
fondo, la prima volta, va costituito — e finche' non c'e' il fabbisogno
e' quello pieno.

I QUATTRO SCENARI: TUTTI COPRONO, CAMBIA SOLO IL CUSCINETTO
------------------------------------------------------------
Prima gli scenari erano quattro gradi di copertura, e i primi due
lasciavano scoperti gli acconti: sceglierli voleva dire trovarsi corti
a giugno, senza che niente lo dicesse. Ora **tutti e quattro coprono
saldo, acconti e costi fissi**. Quello che cambia e' il margine sul
fabbisogno fiscale, cioe' il cuscinetto per la crescita e gli imprevisti
— e il cuscinetto, se l'anno va come previsto, e' il bonus che resta.

    copertura    fabbisogno + costi                      margine x 0
    consigliato  fabbisogno x (1 + margine) + costi       margine x 1
    prudente     fabbisogno x (1 + 2 margine) + costi     margine x 2
    blindato     fabbisogno x (1 + 3,5 margine) + costi   margine x 3,5

Con `margine_sicurezza` al 10 % (il default) diventano 0 / +10 / +20 /
+35 % sul fabbisogno:

    anno di apertura   38,1 %   42,0 %   45,8 %   51,5 %
    a regime           36,4 %   40,0 %   43,7 %   49,1 %

"Prudente" a +20 % regge una crescita del fatturato del 20 % senza dover
recuperare: gli acconti versati sono calcolati sull'anno prima, e se
cresci il saldo dopo e' piu' alto di quanto avevi accantonato.

Il margine di sicurezza, i costi fissi annui e il fatturato atteso sono
parametri modificabili in /fatture/parametri.
"""

# Parametri specifici dell'accantonamento, con i loro default. Vengono
# uniti a quelli fiscali generali (coefficiente, aliquote, ...).
PARAMETRI_DEFAULT = {
    "margine_sicurezza": 0.10,       # cuscinetto relativo sul fabbisogno
    "costi_fissi_annui": 0.0,        # commercialista + PEC + varie
    "fatturato_atteso_anno": 0.0,    # 0 = stimalo dai dati dell'anno
    "acconto_imposta_perc": 1.00,    # acconto imposta sostitutiva (100 %)
    # Quota dell'acconto che si versa con il saldo di giugno; il resto va
    # al 30 novembre. A 0 l'acconto e' tutto sulla seconda scadenza, che
    # era il modello di prima (vedi DUE SCADENZE, NON UNA).
    "acconto_prima_rata_perc": 0.40,
    "scenario_preferito": "consigliato",
}

PARAMETRI_CAMPI = tuple(PARAMETRI_DEFAULT.keys())

SCENARI = ("copertura", "consigliato", "prudente", "blindato")

# Quante volte il margine di sicurezza entra in ciascuno scenario. Il
# margine resta UN parametro solo (`margine_sicurezza`): cambiando quello
# si muovono tutti e quattro mantenendo le distanze. Con il default al
# 10 % escono 0 / +10 / +20 / +35 % sul fabbisogno fiscale.
MOLTIPLICATORI_MARGINE = {
    "copertura":   0.0,
    "consigliato": 1.0,
    "prudente":    2.0,
    "blindato":    3.5,
}

ETICHETTE = {
    "copertura":   ("Copertura",
                    "Saldo, acconti e costi fissi. Coperto esatto, senza cuscinetto."),
    "consigliato": ("Consigliato",
                    "Copertura piu' un margine per gli imprevisti. E' quello che l'app propone."),
    "prudente":    ("Prudente",
                    "Regge una crescita del fatturato del 20 % senza doverla recuperare."),
    "blindato":    ("Blindato",
                    "Circa meta' dell'incasso resta ferma: a giugno non ci pensi."),
}

# Gli scenari di prima. Restano scritti sulle fatture gia' ripartite, e
# vanno letti senza rompersi: "minimo" copriva solo il saldo, quindi il
# suo erede naturale e' "copertura" (il minimo che oggi e' ancora sicuro);
# "sicuro" copriva saldo e acconti senza margine, cioe' la stessa cosa.
SCENARI_LEGACY = {"minimo": "copertura", "sicuro": "copertura"}


def normalizza_scenario(scenario: str | None) -> str:
    """Riporta gli scenari storici sulla nomenclatura attuale."""
    s = scenario or "consigliato"
    s = SCENARI_LEGACY.get(s, s)
    return s if s in SCENARI else "consigliato"


def _f(param: dict, chiave: str, default: float) -> float:
    """Legge un parametro numerico con fallback, tollerando None e stringhe."""
    v = param.get(chiave, default)
    if v is None or v == "":
        return float(default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def primo_anno_attivita(param: dict, anno: int | None) -> bool:
    """
    L'anno indicato e' quello in cui la partita IVA e' stata aperta?

    E' l'unico anno in cui non si versa un euro di contributi, quindi
    l'unico in cui non c'e' niente da dedurre dall'imponibile. Senza
    `anno` o senza `data_apertura_piva` si risponde no: si assume il caso
    a regime, che e' quello che vale per tutti gli anni tranne uno.
    """
    if anno is None:
        return False
    apertura = param.get("data_apertura_piva")
    try:
        return int(anno) == int(str(apertura)[:4])
    except (TypeError, ValueError):
        return False


def aliquote(param: dict, anno: int | None = None) -> dict:
    """
    Aliquote effettive **sul lordo incassato**, non sull'imponibile.
    Sono i numeri che servono per dire "di 100 euro incassati, X sono
    del fisco" senza rifare ogni volta la catena di moltiplicazioni.

    `anno` serve solo a sapere se e' l'anno di apertura della partita
    IVA: in quell'anno i contributi non sono ancora stati versati e
    quindi non si deducono (vedi il modulo).
    """
    coeff     = _f(param, "coeff_ateco", 0.67)
    aliq_inps = _f(param, "aliquota_inps", 0.2607)
    aliq_imp  = _f(param, "aliquota_imposta", 0.05)
    acc_inps  = _f(param, "aliquota_acconto", 0.80)
    acc_imp   = _f(param, "acconto_imposta_perc", 1.00)
    primo     = primo_anno_attivita(param, anno)

    q_inps    = coeff * aliq_inps
    base_imposta = coeff if primo else coeff * (1.0 - aliq_inps)
    q_imposta = base_imposta * aliq_imp
    saldo     = q_inps + q_imposta
    q_acc_inps = q_inps * acc_inps
    q_acc_imp  = q_imposta * acc_imp
    acconti   = q_acc_inps + q_acc_imp

    # Le due scadenze. Il saldo sta tutto sulla prima; gli acconti si
    # dividono fra le due secondo `acconto_prima_rata_perc`.
    prima_rata = min(max(_f(param, "acconto_prima_rata_perc", 0.40), 0.0), 1.0)
    q_giugno = saldo + acconti * prima_rata
    q_novembre = acconti * (1.0 - prima_rata)

    return {
        "inps": q_inps,
        "imposta": q_imposta,
        # "dovuto" e' il vecchio nome del saldo dell'anno: resta come
        # alias perche' fuori di qui qualcuno potrebbe leggerlo.
        "dovuto": saldo,
        "saldo": saldo,
        "acconto_inps": q_acc_inps,
        "acconto_imposta": q_acc_imp,
        "acconti": acconti,
        "acconti_prima_rata": acconti * prima_rata,
        "acconti_seconda_rata": acconti * (1.0 - prima_rata),
        # Quanto serve avere liquido a ciascuna delle due scadenze.
        "entro_giugno": q_giugno,
        "entro_novembre": q_novembre,
        "prima_rata_perc": prima_rata,
        # Quello che serve avere in mano l'anno in cui saldo e acconti
        # cadono insieme. E' il pavimento di tutti e quattro gli scenari.
        "fabbisogno": saldo + acconti,
        "picco_cassa": saldo + acconti,
        "primo_anno": primo,
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
            rivalsa: float = 0.0, bollo_addebitato: float = 0.0,
            anno: int | None = None) -> dict:
    """
    Scompone un incasso lordo e calcola i quattro scenari.

    Args:
      lordo: importo incassato (totale fattura).
      param: parametri fiscali uniti a quelli di accantonamento.
      fatturato_riferimento: base su cui spalmare i costi fissi, usata
        solo se `fatturato_atteso_anno` non e' impostato.
      rivalsa, bollo_addebitato: gia' inclusi in `lordo` (concorrono al
        reddito, vedi il modulo — Risposta Agenzia Entrate 428/2022 per
        il bollo). Non entrano in nessun calcolo qui: servono solo a
        mostrarne la quota, a scopo di trasparenza.
      anno: l'anno dell'incasso. Serve a sapere se e' l'anno di apertura
        della partita IVA, l'unico senza contributi da dedurre. Senza, si
        assume il caso a regime.

    OGNI SCENARIO E' UNA SOMMA DI VOCI DICHIARATE, non un numero a se'.
    `importi[k]` e' esattamente `sum(componenti[k].values())`: il totale
    non puo' contenere niente che non sia nominato, e le righe mostrate
    a schermo sommano al numero grande.
    """
    try:
        lordo = float(lordo or 0)
    except (TypeError, ValueError):
        lordo = 0.0

    a = aliquote(param, anno)
    margine_perc = _f(param, "margine_sicurezza", 0.10)
    costi_perc = quota_costi_fissi(param, fatturato_riferimento)

    coeff = _f(param, "coeff_ateco", 0.67)
    imponibile = round(lordo * coeff, 2)
    inps       = round(lordo * a["inps"], 2)
    imposta    = round(lordo * a["imposta"], 2)
    acconto_inps    = round(lordo * a["acconto_inps"], 2)
    acconto_imposta = round(lordo * a["acconto_imposta"], 2)
    costi      = round(lordo * costi_perc, 2)

    # Il fabbisogno fiscale e' il pavimento: sotto non scende nessuno
    # scenario. Il margine si applica a quello, non al solo saldo — e'
    # il numero che deve reggere, non una sua parte.
    fabbisogno = round(inps + imposta + acconto_inps + acconto_imposta, 2)

    # Le due scadenze, in euro. La seconda rata si ricava per differenza
    # cosi' le due risommano esattamente agli acconti dovuti: e' la
    # stessa regola dello scorporo della rivalsa, e per lo stesso motivo.
    acconti_tot = round(acconto_inps + acconto_imposta, 2)
    acconto_prima_rata = round(acconti_tot * a["prima_rata_perc"], 2)
    acconto_seconda_rata = round(acconti_tot - acconto_prima_rata, 2)
    entro_giugno = round(inps + imposta + acconto_prima_rata, 2)
    entro_novembre = acconto_seconda_rata

    componenti = {}
    for k in SCENARI:
        componenti[k] = {
            "inps": inps,
            "imposta": imposta,
            "acconto_inps": acconto_inps,
            "acconto_imposta": acconto_imposta,
            "costi": costi,
            "margine": round(fabbisogno * margine_perc
                             * MOLTIPLICATORI_MARGINE[k], 2),
        }
    importi = {k: round(sum(v.values()), 2) for k, v in componenti.items()}

    return {
        "lordo": round(lordo, 2),
        "anno": anno,
        "primo_anno": a["primo_anno"],
        "rivalsa": round(float(rivalsa or 0), 2),
        "bollo_addebitato": round(float(bollo_addebitato or 0), 2),
        "coeff": coeff,
        "imponibile": imponibile,
        "inps": inps,
        "imposta": imposta,
        "saldo": round(inps + imposta, 2),
        "acconto_inps": acconto_inps,
        "acconto_imposta": acconto_imposta,
        "acconti_dovuti": acconti_tot,
        # Quando servono davvero. Il saldo sta tutto sulla prima
        # scadenza; gli acconti si dividono fra le due.
        "acconto_prima_rata": acconto_prima_rata,
        "acconto_seconda_rata": acconto_seconda_rata,
        "entro_giugno": entro_giugno,
        "entro_novembre": entro_novembre,
        "prima_rata_perc": a["prima_rata_perc"],
        # Quanto serve avere in mano, tasse e costi, senza cuscinetto.
        # E' il pavimento di ogni scenario: `acconti_scoperti` e' zero
        # ovunque per costruzione, e resta esposto perche' le pagine lo
        # leggono e perche' un domani un margine negativo lo romperebbe.
        "fabbisogno": fabbisogno,
        "fabbisogno_con_costi": round(fabbisogno + costi, 2),
        "acconti_scoperti": {k: 0.0 for k in SCENARI},
        "aliquote_acconto": {
            "inps": _f(param, "aliquota_acconto", 0.80),
            "imposta": _f(param, "acconto_imposta_perc", 1.00),
        },
        "costi_fissi": costi,
        # Il margine dello scenario preferito, per chi vuole un numero
        # solo; quello per scenario sta in `componenti`.
        "margine": componenti[normalizza_scenario(
            param.get("scenario_preferito"))]["margine"],
        "componenti": componenti,
        "importi": importi,
        "netti": {k: round(lordo - v, 2) for k, v in importi.items()},
        # Le aliquote effettive escono dagli importi, non da una seconda
        # catena di formule: cosi' non possono divergere dal totale
        # mostrato accanto.
        "aliquote": {
            **{k: ((importi[k] / lordo) if lordo else 0.0) for k in SCENARI},
            "inps": a["inps"],
            "imposta": a["imposta"],
            "fabbisogno": a["fabbisogno"],
        },
        "scenario_preferito": normalizza_scenario(param.get("scenario_preferito")),
    }


def totali_periodo(incassato: float, param: dict,
                   fatturato_riferimento: float = 0.0,
                   anno: int | None = None) -> dict:
    """Stessa scomposizione applicata a un aggregato (mese, anno)."""
    return scomponi(incassato, param, fatturato_riferimento, anno=anno)


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
    from shared.design import info
    rivalsa = s.get("rivalsa", 0)
    bollo = s.get("bollo_addebitato", 0)
    if not rivalsa and not bollo:
        return ""
    righe = ""
    if rivalsa:
        righe += ('<div class="row"><span class="t">di cui rivalsa INPS'
                  + info("Inclusa nel lordo e concorre al reddito: imposta e "
                         "INPS si calcolano sul totale, non sul compenso.")
                  + '</span>'
                  + f'<span class="v tnum">€ {eur(rivalsa)}</span></div>')
    if bollo:
        righe += ('<div class="row"><span class="t">di cui bollo addebitato al cliente'
                  + info("Incluso nel lordo e concorre al reddito "
                         "(Risposta Agenzia Entrate 428/2022).")
                  + '</span>'
                  + f'<span class="v tnum">€ {eur(bollo)}</span></div>')
    return righe


# ---------------------------------------------------------------------------
# L'albero della fattura
# ---------------------------------------------------------------------------
# Il numero grande dice quanto accantoni. L'albero dice DOVE VA, e lo dice
# in una forma sola: ogni riga e' un ramo di quella sopra, le foglie
# sommano al ramo, i tre rami grossi sommano al lordo. Se il conto non
# torna si vede, perche' le barre sono tutte in scala sullo stesso lordo.
#
# Tre gruppi, tre colori, e il colore e' il significato:
#   rosso   uscira' davvero — tasse e costi certi, non sono tuoi
#   giallo  resta fermo ma e' tuo — il margine: se l'anno va come previsto
#           e' il bonus che ti prendi alla fine
#   verde   tuo subito — va sul conto personale stasera

ALBERO_CSS = """
<style>
  .alb{margin-top:var(--sp-3)}
  .alb-ramo{margin-left:9px;padding-left:14px;
    border-left:1px solid var(--line-strong)}
  .alb-riga{position:relative;display:grid;
    grid-template-columns:minmax(0,1fr) 72px auto 54px;
    gap:10px;align-items:center;padding:7px 0;font-size:13px}
  .alb-riga::before{content:"";position:absolute;left:-14px;top:50%;
    width:10px;height:1px;background:var(--line-strong)}
  .alb-riga.radice::before{display:none}
  .alb-nome{min-width:0;color:var(--ink-2);line-height:1.35}
  .alb-eur{text-align:right;color:var(--ink-2);white-space:nowrap}
  .alb-pct{text-align:right;font-size:11.5px;color:var(--ink-3);white-space:nowrap}
  .alb-barra{height:7px;border-radius:var(--r-full);background:var(--surface-3);
    overflow:hidden}
  .alb-barra i{display:block;height:100%;border-radius:var(--r-full);
    background:var(--ink-4);transition:width .25s ease}

  /* La radice: il lordo, in grande. Tutto il resto e' una sua parte. */
  .alb-riga.radice{padding:4px 0 10px;border-bottom:1px solid var(--line);
    margin-bottom:4px}
  .alb-riga.radice .alb-nome{color:var(--ink);font-weight:600;font-size:13.5px}
  .alb-riga.radice .alb-eur{color:var(--ink);font-weight:600;font-size:14px}

  /* I tre rami grossi. */
  .alb-riga.gruppo .alb-nome{font-weight:600;color:var(--ink);font-size:13.5px}
  .alb-riga.gruppo .alb-eur{font-weight:600}
  .alb-riga.g-esce .alb-barra i{background:var(--neg)}
  .alb-riga.g-fermo .alb-barra i{background:var(--warn)}
  .alb-riga.g-tuo  .alb-barra i{background:var(--pos)}
  .alb-riga.g-esce .alb-eur{color:var(--neg)}
  .alb-riga.g-fermo .alb-eur{color:var(--warn)}
  .alb-riga.g-tuo  .alb-eur{color:var(--pos)}

  /* Le due scadenze: sono i nodi che rispondono alla domanda vera —
     quanto devo avere liquido, e per quando. Stanno un gradino sopra le
     voci che contengono, anche visivamente. */
  .alb-riga.scadenza .alb-nome{font-weight:600;color:var(--ink);font-size:13px}
  .alb-riga.scadenza .alb-eur{font-weight:600;color:var(--ink)}
  .alb-riga.scadenza{padding-top:9px}

  /* Le voci dentro "uscira' davvero": stessa famiglia, tinta piu' bassa. */
  .ramo-esce .alb-riga:not(.gruppo) .alb-barra i{
    background:color-mix(in srgb,var(--neg) 55%,transparent)}
  /* Gli acconti a righe: sono un debito dell'anno prossimo, non di questo. */
  .alb-riga.acconto .alb-barra i{
    background:repeating-linear-gradient(135deg,
      color-mix(in srgb,var(--neg) 55%,transparent) 0 3px,
      color-mix(in srgb,var(--neg) 16%,transparent) 3px 6px)}
  .ramo-fermo .alb-riga:not(.gruppo) .alb-barra i{
    background:color-mix(in srgb,var(--warn) 55%,transparent)}

  /* Il totale accantonato: la somma dei primi due rami, staccata. */
  .alb-totale{display:grid;grid-template-columns:minmax(0,1fr) auto 54px;
    gap:10px;align-items:baseline;margin-top:var(--sp-3);
    padding-top:var(--sp-3);border-top:1px solid var(--line)}
  .alb-totale .t{font-weight:600;color:var(--ink);font-size:13.5px}
  .alb-totale .t span{display:block;font-size:11px;font-weight:400;
    color:var(--ink-3);margin-top:1px}
  .alb-totale .v{text-align:right;font-weight:600;color:var(--accent-text);
    font-size:15px;white-space:nowrap}
  .alb-totale .p{text-align:right;font-size:11.5px;color:var(--ink-3)}

  @media (max-width:420px){
    .alb-riga{grid-template-columns:minmax(0,1fr) auto 48px}
    .alb-riga .alb-barra{display:none}
  }
</style>
"""


def gruppi(s: dict, k: str) -> dict:
    """
    I tre rami dell'albero per uno scenario, piu' i sotto-rami del primo.
    Ogni chiave qui e' una somma di voci di `componenti[k]`: e' l'unico
    posto dove si decide cosa sta con cosa.
    """
    c = s["componenti"][k]
    saldo = round(c["inps"] + c["imposta"], 2)
    acconti = round(c["acconto_inps"] + c["acconto_imposta"], 2)
    return {
        "saldo": saldo,
        "acconti": acconti,
        "costi": c["costi"],
        # Rosso: uscira' davvero. I costi fissi non sono tasse, ma sono
        # uscite certe, e da qui in poi si comportano allo stesso modo.
        "esce": round(saldo + acconti + c["costi"], 2),
        # Giallo: fermo, ma tuo.
        "fermo": c["margine"],
        # Verde: va sul conto personale.
        "tuo": s["netti"][k],
        "accantoni": s["importi"][k],
    }


def albero_html(s: dict, uid: str, anno_acconto=None, anno_saldo=None,
                aperto: bool = False) -> str:
    """
    La scomposizione del lordo ad albero, reattiva allo scenario.

    Le voci fisse (INPS, imposta, acconti, costi) non cambiano con lo
    scenario: cambiano solo il margine e, di conseguenza, i tre totali di
    ramo, quanto resta tuo e il totale accantonato. Quelle sono le uniche
    celle marcate con `data-alb`; il resto e' scritto una volta e sta
    fermo.
    """
    from shared.fmt import eur, pct
    from shared.design import info

    lordo = s["lordo"] or 0.0
    pref = s["scenario_preferito"]
    g = gruppi(s, pref)
    a_acc = f"{anno_acconto}" if anno_acconto else "dell'anno prossimo"
    a_sal = f"{anno_saldo}" if anno_saldo else "di quest'anno"
    scad = (f"lo paghi a giugno {anno_acconto}" if anno_acconto
            else "lo paghi a giugno dell'anno dopo")
    scad_acc = (f"giugno e novembre {anno_acconto}" if anno_acconto
                else "giugno e novembre dell'anno dopo")

    def q(v):
        return (v / lordo * 100) if lordo else 0.0

    def riga(nome, sub, valore, classi="", chiave=None):
        """
        Una riga dell'albero. `chiave` la rende aggiornabile dal JS.

        La descrizione non sta piu' sotto il nome: dieci sottotitoli grigi
        su dodici righe raddoppiavano l'altezza dell'albero e si smetteva
        di leggerli. Ora sta dietro la "i", che la apre a richiesta.
        """
        attr = f' data-alb="{chiave}" data-alb-uid="{uid}"' if chiave else ""
        sub_html = info(sub) if sub else ""
        return (f'<div class="alb-riga {classi}"{attr}>'
                f'<span class="alb-nome">{nome}{sub_html}</span>'
                f'<span class="alb-barra"><i style="width:{q(valore):.2f}%"></i></span>'
                f'<span class="alb-eur tnum">&euro; {eur(valore)}</span>'
                f'<span class="alb-pct tnum">{pct(q(valore) / 100, 1)}</span>'
                f'</div>')

    sub_imposta = ("sull'imponibile pieno: primo anno, nessun contributo ancora "
                   "versato e quindi niente da dedurre" if s.get("primo_anno")
                   else "al netto dei contributi, che sono deducibili")

    righe_esce = "".join([
        # PRIMA SCADENZA — saldo dell'anno piu' la prima rata degli acconti.
        # E' il ramo che risponde a "quanto devo avere liquido a giugno",
        # ed e' il motivo per cui l'albero e' raggruppato per DATA e non
        # per tipo di tributo: i tributi sono tre, le date sono due, e
        # quella che ti serve sapere e' la data.
        riga(f"Entro il 30 giugno {a_acc}",
             "saldo dell'anno pi&ugrave; la prima rata degli acconti &mdash; "
             "di norma prorogato al 31 luglio",
             s["entro_giugno"], "scadenza"),
        '<div class="alb-ramo">',
        riga(f"Saldo INPS {a_sal}", "gestione separata", s["inps"]),
        riga(f"Saldo imposta {a_sal}", sub_imposta, s["imposta"]),
        riga(f"1&ordf; rata acconti {a_acc}",
             f"{pct(s['prima_rata_perc'], 0)} degli acconti, versata insieme al saldo",
             s["acconto_prima_rata"], "acconto"),
        "</div>",
        # SECONDA SCADENZA — il resto degli acconti.
        riga(f"Entro il 30 novembre {a_acc}", "seconda rata degli acconti",
             s["entro_novembre"], "scadenza"),
        '<div class="alb-ramo">',
        riga(f"2&ordf; rata acconti {a_acc}",
             f"il resto: {pct(1 - s['prima_rata_perc'], 0)} degli acconti",
             s["acconto_seconda_rata"], "acconto"),
        "</div>",
        riga("Costi fissi pro-quota",
             "commercialista, PEC, bolli: escono durante l'anno, non a scadenza",
             g["costi"]),
    ])

    rivalsa_html = _riga_rivalsa_bollo(s)
    testata = f'<div class="rows">{rivalsa_html}</div>' if rivalsa_html else ""

    corpo = (
        ALBERO_CSS
        + '<div class="alb">'
        + riga("Incasso lordo", "quello che il cliente ti versa", lordo, "radice")
        + '<div class="alb-ramo ramo-esce">'
        + riga("Uscir&agrave; davvero", "tasse e costi certi: non sono tuoi",
               g["esce"], "gruppo g-esce", "esce")
        + f'<div class="alb-ramo">{righe_esce}</div>'
        + "</div>"
        + '<div class="alb-ramo ramo-fermo">'
        + riga("Resta fermo, ma &egrave; tuo",
               "se l'anno va come previsto, alla fine te lo prendi",
               g["fermo"], "gruppo g-fermo", "fermo")
        + '<div class="alb-ramo">'
        + riga("Margine di sicurezza", "il cuscinetto dello scenario scelto",
               g["fermo"], "", "margine")
        + "</div></div>"
        + '<div class="alb-ramo">'
        + riga("Tuo subito", "si sposta sul conto personale",
               g["tuo"], "gruppo g-tuo", "tuo")
        + "</div>"
        + '<div class="alb-totale">'
        + '<span class="t">Accantoni in tutto'
        + info("Resta sul conto P.IVA: quello che uscir&agrave; davvero "
               "pi&ugrave; il cuscinetto.")
        + '</span>'
        + f'<span class="v tnum" data-alb="accantoni" data-alb-uid="{uid}">'
          f'&euro; {eur(g["accantoni"])}</span>'
        + f'<span class="p tnum" data-alb-pcttot="{uid}">'
          f'{pct(s["aliquote"][pref], 1)}</span>'
        + "</div></div>"
    )

    apri = " open" if aperto else ""
    return (f'<details class="explain mt-4"{apri}>'
            f"<summary>Dove vanno questi soldi</summary>"
            f"{testata}{corpo}</details>")


# ---------------------------------------------------------------------------

def card_html(s: dict, titolo: str = "Da accantonare",
              contesto: str = "", uid: str = "acc",
              anno_acconto=None, anno_saldo=None,
              albero_aperto: bool = False) -> str:
    """
    La card: quanto accantoni, il selettore di scenario, la barra a
    segmenti e l'albero di dove vanno i soldi.

    TUTTI E QUATTRO GLI SCENARI COPRONO. La domanda a cui la card
    risponde non e' piu' "sono coperto?" — lo sei sempre — ma "quanto
    cuscinetto mi tengo, e quanto di quello che accantono e' bonus".
    Per questo il numero grande e' accompagnato dal numero verde di
    quanto resta tuo, e dalla riga gialla del bonus.
    """
    from shared.fmt import eur, pct
    from shared.design import info

    lordo = s["lordo"] or 0.0
    pref = s["scenario_preferito"]
    comp = s["componenti"]
    a_acc = f"del {anno_acconto}" if anno_acconto else "dell'anno prossimo"

    seg = "".join(
        f'<button type="button" data-acc="{uid}" data-scen="{k}"'
        + (' class="is-active"' if k == pref else "")
        + f">{ETICHETTE[k][0]}</button>"
        for k in SCENARI
    )

    def q(v):
        return (v / lordo * 100) if lordo else 0.0

    def frase(k):
        """La riga gialla: cosa ci guadagni a scegliere questo scenario."""
        g = gruppi(s, k)
        if g["fermo"] <= 0:
            return ("<strong>Copri esatto, senza cuscinetto.</strong>"
                    + info("Tasse e costi ci sono tutti, ma un imprevisto o una "
                           "crescita del fatturato ti trovano scoperto."))
        return (f"<strong>&euro; {eur(g['fermo'])} sono cuscinetto, non tasse.</strong>"
                + info("Se l'anno va come previsto restano l&igrave;: &egrave; il "
                       "bonus che ti prendi quando hai pagato tutto."))

    def classe(k):
        return "neg" if gruppi(s, k)["fermo"] <= 0 else "pos"

    # Il contesto era una frase lunga sotto la barra: adesso sta dietro la
    # "i" accanto al titolo della card. Non e' un avviso, e' una nota.
    ctx = info(contesto) if contesto else ""

    import json
    dati = json.dumps({
        "lordo": lordo,
        "importi": s["importi"],
        "netti": s["netti"],
        "aliquote": {k: s["aliquote"][k] for k in SCENARI},
        "gruppi": {k: gruppi(s, k) for k in SCENARI},
        "frasi": {k: frase(k) for k in SCENARI},
        "classi": {k: classe(k) for k in SCENARI},
    }, ensure_ascii=False)

    g = gruppi(s, pref)

    # La barra: le quattro quote del lordo, nell'ordine in cui l'albero le
    # racconta. Chi guarda solo la barra deve vedere la stessa storia.
    barra = (
        '<div class="bar-split mt-4" aria-hidden="true">'
        f'<span data-acc-bar-tuo="{uid}" style="background:var(--pos);'
        f'width:{q(g["tuo"]):.2f}%"></span>'
        f'<span style="background:var(--neg);width:{q(g["saldo"]):.2f}%"></span>'
        f'<span class="seg-acconti" style="width:{q(g["acconti"]):.2f}%"></span>'
        f'<span style="background:var(--ink-4);width:{q(g["costi"]):.2f}%"></span>'
        f'<span data-acc-bar-fermo="{uid}" style="background:var(--warn);'
        f'width:{q(g["fermo"]):.2f}%"></span>'
        "</div>"
    )

    voci_legenda = [
        f'<div><i class="dot" style="background:var(--pos)"></i>Tuoi '
        f'<span data-acc-leg-tuo="{uid}" class="tnum">&euro; {eur(g["tuo"])}</span></div>',
        f'<div><i class="dot" style="background:var(--neg)"></i>Saldo '
        f'<span class="tnum">&euro; {eur(g["saldo"])}</span></div>',
        f'<div><i class="dot acconti"></i>Acconti {a_acc} '
        f'<span class="tnum">&euro; {eur(g["acconti"])}</span></div>',
    ]
    if g["costi"] > 0:
        voci_legenda.append(
            f'<div><i class="dot" style="background:var(--ink-4)"></i>Costi fissi '
            f'<span class="tnum">&euro; {eur(g["costi"])}</span></div>')
    voci_legenda.append(
        f'<div><i class="dot" style="background:var(--warn)"></i>Cuscinetto '
        f'<span data-acc-leg-fermo="{uid}" class="tnum">&euro; {eur(g["fermo"])}</span></div>')

    # Le due scadenze, in cima e non solo dentro l'albero: e' la domanda
    # che uno si fa guardando la fattura ("quanto mi serve, e per
    # quando"), e non deve costare l'apertura di un accordion.
    anno_sc = anno_acconto or ""
    chip_scadenze = f'''
  <div class="scad-due">
    <div class="scad">
      <div class="scad-quando">entro il 30 giugno {anno_sc}</div>
      <div class="scad-quanto tnum">&euro; {eur(s["entro_giugno"])}</div>
      <div class="scad-cosa">saldo + 1&ordf; rata acconti</div>
    </div>
    <div class="scad">
      <div class="scad-quando">entro il 30 novembre {anno_sc}</div>
      <div class="scad-quanto tnum">&euro; {eur(s["entro_novembre"])}</div>
      <div class="scad-cosa">2&ordf; rata acconti</div>
    </div>
  </div>'''

    albero = albero_html(s, uid, anno_acconto=anno_acconto,
                         anno_saldo=anno_saldo, aperto=albero_aperto)

    nota_primo = ""
    if s.get("primo_anno"):
        nota_primo = (
            '<div class="notice info small mt-3">'
            "<strong>Primo anno: il fabbisogno &egrave; pi&ugrave; alto.</strong>"
            + info("Non hai ancora versato contributi, quindi non c'&egrave; niente "
                   "da dedurre: l'imposta si calcola sull'imponibile pieno. "
                   "Sono 1,75 punti in pi&ugrave; sul lordo. Dall'anno prossimo "
                   "scende da s&eacute;.")
            + "</div>")

    return f"""
<div class="card acc-card" id="{uid}">
  <div class="card-head">
    <div class="eyebrow">{titolo}{ctx}</div>
    <div class="segmented acc-seg">{seg}</div>
  </div>

  <div class="acc-main">
    <div class="stat">
      <div class="val accent tnum" data-acc-val="{uid}">&euro; {eur(s["importi"][pref])}</div>
      <div class="lbl">
        <span data-acc-pct="{uid}">{pct(s["aliquote"][pref])}</span> di &euro; {eur(lordo)} incassati
      </div>
    </div>
    <div class="acc-netto">
      <div class="lbl muted small">Restano tuoi</div>
      <div class="tnum h2 pos" data-acc-netto="{uid}">&euro; {eur(s["netti"][pref])}</div>
    </div>
  </div>

  {barra}
  <div class="legend">{"".join(voci_legenda)}</div>
  {chip_scadenze}

  <div class="acc-acconti {classe(pref)}" data-acc-acconti="{uid}">
    <i class="dot" style="background:var(--warn)" aria-hidden="true"></i>
    <span data-acc-frase="{uid}">{frase(pref)}</span>
  </div>
  {nota_primo}
  {albero}
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
  var alb = function(k){{
    return document.querySelector('[data-alb="' + k + '"][data-alb-uid="' + uid + '"]');
  }};

  // Aggiorna una riga dell'albero: importo, larghezza della barra e
  // percentuale. Le righe non marcate non cambiano con lo scenario.
  function riga(k, v){{
    var r = alb(k);
    if (!r) return;
    var eur = r.querySelector('.alb-eur'), barra = r.querySelector('.alb-barra i'),
        p = r.querySelector('.alb-pct');
    if (r.classList.contains('alb-totale') || !eur) {{
      r.textContent = '\\u20ac ' + fmt(v);
      return;
    }}
    eur.textContent = '\\u20ac ' + fmt(v);
    if (barra) barra.style.width = q(v).toFixed(2) + '%';
    // q() torna gia' una percentuale 0-100, pctFmt vuole una frazione.
    if (p) p.textContent = pctFmt(q(v) / 100);
  }}

  function pick(scen){{
    var g = D.gruppi[scen];
    el('data-acc-val').textContent   = '\\u20ac ' + fmt(D.importi[scen]);
    el('data-acc-pct').textContent   = pctFmt(D.aliquote[scen]);
    el('data-acc-netto').textContent = '\\u20ac ' + fmt(D.netti[scen]);
    el('data-acc-bar-tuo').style.width   = q(g.tuo).toFixed(2) + '%';
    el('data-acc-bar-fermo').style.width = q(g.fermo).toFixed(2) + '%';
    el('data-acc-leg-tuo').textContent   = '\\u20ac ' + fmt(g.tuo);
    el('data-acc-leg-fermo').textContent = '\\u20ac ' + fmt(g.fermo);

    var box = el('data-acc-acconti');
    if (box) {{
      box.className = 'acc-acconti ' + D.classi[scen];
      el('data-acc-frase').innerHTML = D.frasi[scen];
    }}

    riga('esce', g.esce);
    riga('fermo', g.fermo);
    riga('margine', g.fermo);
    riga('tuo', g.tuo);
    var tot = alb('accantoni');
    if (tot) tot.textContent = '\\u20ac ' + fmt(g.accantoni);
    var pt = document.querySelector('[data-alb-pcttot="' + uid + '"]');
    if (pt) pt.textContent = pctFmt(D.aliquote[scen]);

    document.querySelectorAll('[data-acc="' + uid + '"]').forEach(function(b){{
      b.classList.toggle('is-active', b.dataset.scen === scen);
    }});
  }}

  document.querySelectorAll('[data-acc="' + uid + '"]').forEach(function(b){{
    b.addEventListener('click', function(){{ pick(b.dataset.scen); }});
  }});
}})();
</script>
"""
