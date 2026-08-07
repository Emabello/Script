"""
fatture/costanti.py — Costanti condivise del modulo fatture.
"""

CATEGORIE_SPESE_PIVA = [
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
    ("giroconto_personale", "Giroconto al personale"),
    ("altro",            "Altro"),
]

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
# facsimile che viene mandato allo studio, che poi predispone e trasmette
# l'XML allo SDI. Gli stati rispecchiano quel passaggio di mano, perche' e'
# il momento oltre il quale il documento non e' piu' modificabile senza
# passare da loro.
#
# Ordine e significato:
#   bozza           in lavorazione, solo tua. Modificabile ed eliminabile.
#   inviata_studio  facsimile mandato allo studio. Da qui il documento e'
#                   in mano loro: niente piu' modifiche.
#   trasmessa_sdi   lo studio ha confermato la trasmissione allo SDI.
#   incassata       il denaro e' arrivato. E' questo che fa scattare
#                   l'accantonamento, perche' il forfettario e' per cassa.
#   annullata       fuori dal giro, non concorre a nulla.

STATI = (
    # (chiave, etichetta, classe del chip, descrizione breve)
    ("bozza",          "Bozza",              "",       "In lavorazione, non ancora inviata"),
    ("inviata_studio", "Inviata allo studio", "accent", "Il facsimile è dallo studio, che predispone la fattura elettronica"),
    ("trasmessa_sdi",  "Trasmessa a SDI",    "accent", "Lo studio ha trasmesso la fattura elettronica"),
    ("incassata",      "Incassata",          "pos",    "Il denaro è arrivato"),
    ("annullata",      "Annullata",          "neg",    "Fuori dal giro, non concorre ai calcoli"),
)

STATI_CHIAVI = tuple(k for k, _, _, _ in STATI)
STATI_LABEL = {k: lbl for k, lbl, _, _ in STATI}
STATI_CLASSE = {k: cls for k, _, cls, _ in STATI}
STATI_DESCR = {k: d for k, _, _, d in STATI}

# Ordine di avanzamento, per la linea temporale sul dettaglio.
STATI_PERCORSO = ("bozza", "inviata_studio", "trasmessa_sdi", "incassata")

# Stati che concorrono al fatturato e ai calcoli fiscali: la bozza no
# (non e' ancora un documento), l'annullata nemmeno.
STATI_EMESSE = ("inviata_studio", "trasmessa_sdi", "incassata")

# Il documento e' modificabile o eliminabile solo finche' non e' uscito
# dalle tue mani. Dopo, correggerlo qui vorrebbe dire divergere dalla
# fattura vera senza che nessuno se ne accorga.
STATI_MODIFICABILI = ("bozza",)

# Data da chiedere quando si entra in un certo stato: (campo, etichetta)
DATE_STATO = {
    "inviata_studio": ("data_invio_studio", "Data di invio allo studio"),
    "trasmessa_sdi":  ("data_trasmissione_sdi", "Data di trasmissione"),
    "incassata":      ("data_incasso", "Data di incasso"),
}

# Mappatura degli stati storici: prima dell'introduzione del passaggio
# dallo studio esisteva un solo stato "emessa".
STATI_LEGACY = {"emessa": "inviata_studio"}


def normalizza_stato(stato: str | None) -> str:
    """Riporta gli stati storici sulla nomenclatura attuale."""
    s = stato or "bozza"
    return STATI_LEGACY.get(s, s)


def prossimo_stato(stato: str) -> str | None:
    """Passo successivo naturale del percorso, o None se non ce n'e'."""
    s = normalizza_stato(stato)
    if s not in STATI_PERCORSO:
        return None
    i = STATI_PERCORSO.index(s)
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
    if s in ("inviata_studio", "trasmessa_sdi", "incassata"):
        return ("Il facsimile è già stato mandato allo studio, che predispone e "
                "trasmette la fattura elettronica. Modificarla qui la farebbe "
                "divergere da quella vera senza che nessuno se ne accorga. "
                "Scrivi allo studio: se non hanno ancora trasmesso la correggono "
                "loro, altrimenti serve una nota di credito.")
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
