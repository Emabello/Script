"""
fatture/costanti.py — Costanti condivise del modulo fiscale.
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
    ("altro",            "Altro"),
]

MESI_NOMI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]
