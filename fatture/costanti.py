"""
fatture/costanti.py — Costanti condivise del modulo fatture.
"""
from shared.ordina import ordina_coppie

# Le categorie del conto P.IVA, alfabetiche per etichetta: e' cosi' che
# arrivano nei menu (filtro movimenti P.IVA, form del movimento, foglio
# "registra entrata" sulla fattura). Il valore scritto a database e' la
# chiave, non la posizione: riordinarle non tocca nessuna riga esistente.
CATEGORIE_SPESE_PIVA = ordina_coppie([
    ("fatturato",        "Fatturato incassato"),
    ("commercialista",   "Commercialista"),
    ("pec",              "PEC"),
    ("licenze",          "Licenze / software"),
    ("hardware",         "Hardware"),
    ("inps_pagata",      "INPS versata"),
    ("imposta_pagata",   "Imposta sostitutiva versata"),
    ("bollo_pagato",     "Bollo pagato"),
    ("bancarie",         "Commissioni bancarie"),
    ("formazione",       "Formazione"),
    ("giroconto_personale", "Giroconto P.IVA"),
    ("altro",            "Altro"),
])

# I tipi di movimento del conto P.IVA. A differenza del conto personale
# qui "giroconto" e' un tipo legittimo e scrivibile: e' la meta' che esce
# dal conto P.IVA quando si ripartisce un incasso (vedi giroconto.py).
TIPI_SPESE_PIVA = ordina_coppie([
    ("entrata",   "Entrata"),
    ("uscita",    "Uscita"),
    ("giroconto", "Giroconto"),
])

# Categoria dei giroconti che spostano la quota tua dal conto P.IVA a
# quello personale. Non e' una spesa: e' denaro che cambia conto, e per
# questo va tenuta fuori dai totali delle uscite.
CATEGORIA_GIROCONTO = "giroconto_personale"

MESI_NOMI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]


# ---------------------------------------------------------------------------
# Ciclo di vita della fattura
# ---------------------------------------------------------------------------
# Il documento che questa app produce NON e' la fattura elettronica: e' il
# facsimile. Il percorso vero, quello che si vuole vedere sulla pagina, e'
# questo (deciso il 01/09/2026, sostituisce l'ordine precedente):
#
#   bozza           in lavorazione, solo tua. Modificabile ed eliminabile.
#   inviata_nadia   facsimile mandato a Nadia, l'amministrazione interna
#                   di B2FORGE. E' il documento su cui pagano.
#   incassata       il denaro e' arrivato. E' questo che fa scattare
#                   l'accantonamento, perche' il forfettario e' per cassa.
#   inviata_studio  facsimile mandato allo studio, che predispone la
#                   fattura elettronica. Da qui non si tocca piu'.
#   trasmessa_sdi   lo studio ha confermato la trasmissione allo SDI.
#                   Fine del percorso.
#   annullata       fuori dal giro, non concorre a nulla.
#
# L'INCASSO NON E' PIU' L'ULTIMO PASSO, ed e' la cosa da tenere a mente
# leggendo il resto del codice: `stato == "incassata"` NON vuol piu' dire
# "i soldi sono arrivati" — una fattura pagata e poi mandata allo studio
# sta in `inviata_studio` e i soldi ci sono lo stesso. La domanda "e'
# stata incassata?" si fa a `data_incasso` (vedi `ha_incassato`), che e'
# anche l'unica risposta che regge sui dati vecchi, dove `inviata_studio`
# significava "spedita ma non ancora pagata".

STATI = (
    # (chiave, etichetta, classe del chip, descrizione breve)
    ("bozza",          "Bozza",              "",       "In lavorazione, non ancora inviata"),
    ("inviata_nadia",  "Inviata a Nadia",    "accent", "Il facsimile è all'amministrazione di B2FORGE"),
    ("incassata",      "Incassata",          "pos",    "Il denaro è arrivato"),
    ("inviata_studio", "Inviata allo studio", "accent", "Lo studio predispone la fattura elettronica"),
    ("trasmessa_sdi",  "Trasmessa a SDI",    "pos",    "Lo studio ha trasmesso la fattura elettronica"),
    ("annullata",      "Annullata",          "neg",    "Fuori dal giro, non concorre ai calcoli"),
)

STATI_CHIAVI = tuple(k for k, _, _, _ in STATI)
STATI_LABEL = {k: lbl for k, lbl, _, _ in STATI}
STATI_CLASSE = {k: cls for k, _, cls, _ in STATI}
STATI_DESCR = {k: d for k, _, _, d in STATI}

# Ordine di avanzamento, per la linea temporale sul dettaglio.
STATI_PERCORSO = ("bozza", "inviata_nadia", "incassata",
                  "inviata_studio", "trasmessa_sdi")

# Stati che concorrono al fatturato e ai calcoli fiscali: la bozza no
# (non e' ancora un documento), l'annullata nemmeno.
STATI_EMESSE = tuple(k for k in STATI_PERCORSO if k != "bozza")

# Gli stati che stanno a incasso avvenuto, cioe' da "incassata" in poi.
# Serve alle query che devono chiedere al database "quali fatture sono
# state pagate" senza poter chiamare `ha_incassato` riga per riga.
STATI_INCASSATE = STATI_PERCORSO[STATI_PERCORSO.index("incassata"):]

# Data da chiedere quando si entra in un certo stato: (campo, etichetta)
DATE_STATO = {
    "inviata_nadia":  ("data_invio_nadia", "Data di invio a Nadia"),
    "incassata":      ("data_incasso", "Data di incasso"),
    "inviata_studio": ("data_invio_studio", "Data di invio allo studio"),
    "trasmessa_sdi":  ("data_trasmissione_sdi", "Data di trasmissione"),
}

# Il documento e' modificabile finche' non e' successo niente di
# irreversibile. Il confine e' l'INCASSO, non la spedizione: finche' i
# soldi non si sono mossi, una correzione concordata con Nadia e' solo
# un facsimile rifatto. Dopo, correggere qui vorrebbe dire far divergere
# l'importo dal denaro gia' entrato — e, piu' avanti, dalla fattura vera
# che lo studio ha gia' costruito.
STATI_MODIFICABILI = ("bozza", "inviata_nadia")

# Mappatura degli stati storici: prima dell'introduzione del passaggio
# dallo studio esisteva un solo stato "emessa".
STATI_LEGACY = {"emessa": "inviata_studio"}


def normalizza_stato(stato: str | None) -> str:
    """Riporta gli stati storici sulla nomenclatura attuale."""
    s = stato or "bozza"
    return STATI_LEGACY.get(s, s)


def indice_percorso(stato: str) -> int:
    """
    Posizione dello stato lungo il percorso, o -1 se ne sta fuori
    (annullata, o una chiave che non conosciamo). Confrontare due indici
    e' l'unico modo corretto di dire "piu' avanti / piu' indietro": da
    quando l'incasso sta in mezzo, l'ordine alfabetico o quello di
    dichiarazione non dicono piu' niente.
    """
    s = normalizza_stato(stato)
    return STATI_PERCORSO.index(s) if s in STATI_PERCORSO else -1


def ha_incassato(f: dict) -> bool:
    """
    I soldi di questa fattura sono arrivati?

    Lo dice la DATA, non lo stato. Da quando l'incasso e' un passo in
    mezzo al percorso, una fattura pagata puo' trovarsi in
    `inviata_studio` o `trasmessa_sdi`: chiedere `stato == "incassata"`
    la conterebbe come non pagata e farebbe sparire un incasso vero dai
    totali. La data invece resta scritta, e viene ripulita da sola se si
    torna indietro prima dell'incasso (vedi l'API di cambio stato).

    Una fattura annullata non conta mai, anche se la data e' rimasta li'.
    """
    if normalizza_stato(f.get("stato")) == "annullata":
        return False
    return bool(f.get("data_incasso"))


def prossimo_stato(stato: str) -> str | None:
    """Passo successivo naturale del percorso, o None se non ce n'e'."""
    i = indice_percorso(stato)
    if i < 0:
        return None
    return STATI_PERCORSO[i + 1] if i + 1 < len(STATI_PERCORSO) else None


def modificabile(stato: str) -> bool:
    return normalizza_stato(stato) in STATI_MODIFICABILI


def motivo_blocco(stato: str) -> str:
    """
    Perche' la fattura non si puo' modificare, e cosa fare invece.
    Testo mostrato all'utente: deve dire il passo successivo, non solo
    negare l'operazione.
    """
    s = normalizza_stato(stato)
    if s == "annullata":
        return ("Questa fattura è annullata. Per rifatturare, creane una nuova: "
                "modificare un documento annullato lascerebbe due verità diverse "
                "sullo stesso numero.")
    if s == "incassata":
        return ("Questa fattura è già stata incassata: cambiarne gli importi ora "
                "la farebbe divergere dal denaro entrato sul conto P.IVA, e "
                "dall'accantonamento calcolato su quella cifra. Se l'incasso "
                "è stato segnato per sbaglio, riportala prima a «Inviata a Nadia»: "
                "da lì torna modificabile.")
    if s in ("inviata_studio", "trasmessa_sdi"):
        return ("Il facsimile è già dallo studio, che predispone e trasmette la "
                "fattura elettronica. Modificarla qui la farebbe divergere da "
                "quella vera senza che nessuno se ne accorga. Scrivi allo studio: "
                "se non hanno ancora trasmesso la correggono loro, altrimenti "
                "serve una nota di credito.")
    return ""


# ---------------------------------------------------------------------------
# Rivalsa INPS gestione separata
# ---------------------------------------------------------------------------
# Accordo con lo studio (mail del 5 agosto 2026): la rivalsa del 4 % si
# SCORPORA dal corrispettivo concordato, non si aggiunge sopra.
#
#   corrispettivo concordato  5.000,00   <- quello che il cliente paga
#   di cui compenso           4.807,69   = 5.000 / 1,04
#   di cui rivalsa INPS 4 %     192,31   = 5.000 - compenso
#
# La variante ad addebito (5.000 + 200 = 5.200) e' stata tolta di
# proposito: tenerla disponibile significava solo poterla premere per
# sbaglio e produrre un facsimile che non combacia con la fattura vera.

RIVALSA_PERC = 4.0


def rivalsa_perc(emittente: dict | None) -> float:
    """
    La percentuale di rivalsa da usare, letta dall'EMITTENTE.

    `b2f_emittente.aliquota_cassa` e' il posto in cui questo numero deve
    stare: c'e' una pagina per modificarlo, e chi lo cambia si aspetta che
    l'app lo usi. Prima non lo usava nessuno — finiva solo dentro il
    payload del PDF — mentre lo scorporo girava sulla costante qui sopra.
    Due verita' sullo stesso numero, e quella scritta a database era zero
    senza che niente lo segnalasse.

    Il fallback sulla costante resta per un motivo solo: un emittente non
    ancora compilato non deve far sparire una rivalsa che l'accordo con
    lo studio prevede. Chi non ha rivalsa la mette esplicitamente a zero,
    e l'editor lo dice invece di limitarsi a non spuntare la casella.
    """
    if emittente is None:
        return RIVALSA_PERC
    val = emittente.get("aliquota_cassa")
    if val is None or val == "":
        return RIVALSA_PERC
    try:
        return max(float(val), 0.0)
    except (TypeError, ValueError):
        return RIVALSA_PERC


def scorpora_rivalsa(corrispettivo: float, perc: float = RIVALSA_PERC) -> dict:
    """
    Scompone il corrispettivo concordato in compenso e rivalsa.

    Il totale non cambia: e' il compenso a ridursi. Ritorna importi gia'
    arrotondati al centesimo, con la rivalsa calcolata per differenza
    cosi' le due voci risommano esattamente al corrispettivo.
    """
    try:
        lordo = float(corrispettivo or 0)
    except (TypeError, ValueError):
        lordo = 0.0
    if lordo <= 0 or perc <= 0:
        return {"corrispettivo": round(lordo, 2), "compenso": round(lordo, 2),
                "rivalsa": 0.0, "perc": 0.0}
    compenso = round(lordo / (1 + perc / 100.0), 2)
    return {
        "corrispettivo": round(lordo, 2),
        "compenso": compenso,
        "rivalsa": round(lordo - compenso, 2),
        "perc": perc,
    }
