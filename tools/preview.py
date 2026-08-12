"""
Harness di anteprima: monta l'app B2F con un finto client Supabase e dati
realistici, per poter guardare le schermate senza toccare il database.

    python3 preview.py [porta]
"""
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("APP_PIN", None)

# ---------------------------------------------------------------------------
# Dati finti — agosto 2026
# ---------------------------------------------------------------------------

DB = {
    "b2f_emittente": [{
        "id": 1, "nome": "Emanuele", "cognome": "Bellotti",
        "denominazione": None, "piva": "IT04512380231", "cf": "BLLMNL95A01L781X",
        "regime_fisc": "RF19", "indirizzo": "Via Mazzini 14", "cap": "37121",
        "comune": "Verona", "provincia": "VR", "nazione": "IT",
        "email": "ebellotti01@gmail.com", "pec": "e.bellotti@pec.it",
        "telefono": "+39 345 1122334", "iban": "IT60X0542811101000000123456",
        "cassa_prev": "INPS Gestione Separata", "aliquota_cassa": 4.00,
        "studio_nome": "Studio Bagaglia",
        "studio_email": "amministrazione@studiobagaglia.it",
    }],
    "b2f_parametri_fiscali": [{
        "id": 1, "regime": "RF19", "ateco": "622010",
        "ateco_descrizione": "Attività di consulenza informatica",
        "coeff_ateco": 0.67, "aliquota_imposta": 0.05, "aliquota_inps": 0.2607,
        "aliquota_acconto": 0.80, "bollo_soglia": 77.47, "bollo_importo": 2.00,
        "limite_fatturato_anno": 85000, "data_apertura_piva": "2026-05-28",
        "anno_fine_regime_agevolato": 2031,
        "margine_sicurezza": 0.10, "costi_fissi_annui": 1200.0,
        "fatturato_atteso_anno": 40000.0, "acconto_imposta_perc": 1.00,
        "scenario_preferito": "consigliato",
    }],
    "b2f_clienti": [
        {"id": 1, "tipo": "azienda", "denominazione": "B2FORGE SRL",
         "piva": "IT01234560239", "cf": None, "indirizzo": "Viale Industria 8",
         "cap": "37135", "comune": "Verona", "provincia": "VR", "nazione": "IT",
         "sdi": "M5UXCR1", "pec": "acme@pec.it", "email": "amministrazione@acme.it",
         "attivo": True, "note": None},
        {"id": 2, "tipo": "azienda", "denominazione": "Studio Ferri & Associati",
         "piva": "IT03344550248", "cf": None, "indirizzo": "Corso Cavour 3",
         "cap": "36100", "comune": "Vicenza", "provincia": "VI", "nazione": "IT",
         "sdi": "0000000", "pec": "studioferri@pec.it", "email": None,
         "attivo": True, "note": None},
        {"id": 3, "tipo": "estero", "denominazione": "Nordwind GmbH",
         "piva": "DE811234567", "cf": None, "indirizzo": "Hauptstrasse 22",
         "cap": "80331", "comune": "München", "provincia": None, "nazione": "DE",
         "sdi": "XXXXXXX", "pec": None, "email": "billing@nordwind.de",
         "attivo": True, "note": None},
        {"id": 4, "tipo": "privato", "nome": "Chiara", "cognome": "Rossetti",
         "denominazione": None, "piva": None, "cf": "RSSCHR90M41L781K",
         "indirizzo": "Via Torbido 5", "cap": "37129", "comune": "Verona",
         "provincia": "VR", "nazione": "IT", "sdi": "0000000", "pec": None,
         "email": "chiara.rossetti@example.it", "attivo": True, "note": None},
    ],
    "b2f_fatture": [],
    "b2f_spese_piva": [
        {"id": 1, "data": "2026-06-02", "importo": 350.00, "tipo": "uscita",
         "descrizione": "Acconto commercialista 2026", "categoria": "commercialista",
         "sottocategoria": None, "fattura_id": None, "ricorrente": False, "note": None},
        {"id": 2, "data": "2026-06-10", "importo": 45.00, "tipo": "uscita",
         "descrizione": "Rinnovo PEC annuale", "categoria": "pec",
         "sottocategoria": None, "fattura_id": None, "ricorrente": True, "note": None},
        {"id": 3, "data": "2026-06-30", "importo": 3200.00, "tipo": "entrata",
         "descrizione": "Fattura 2026/001 — ACME Sistemi S.r.l.", "categoria": "fatturato",
         "sottocategoria": None, "fattura_id": 1, "ricorrente": False, "note": None},
        {"id": 4, "data": "2026-07-05", "importo": 129.00, "tipo": "uscita",
         "descrizione": "Licenza JetBrains", "categoria": "licenze",
         "sottocategoria": "IDE", "fattura_id": None, "ricorrente": True, "note": None},
        {"id": 5, "data": "2026-07-10", "importo": 1850.00, "tipo": "entrata",
         "descrizione": "Fattura 2026/002 — Studio Ferri & Associati",
         "categoria": "fatturato", "sottocategoria": None, "fattura_id": 2,
         "ricorrente": False, "note": None},
        {"id": 6, "data": "2026-07-18", "importo": 1490.00, "tipo": "uscita",
         "descrizione": "MacBook Air M4", "categoria": "hardware",
         "sottocategoria": None, "fattura_id": None, "ricorrente": False, "note": None},
        {"id": 7, "data": "2026-07-31", "importo": 4100.00, "tipo": "entrata",
         "descrizione": "Fattura 2026/003 — ACME Sistemi S.r.l.", "categoria": "fatturato",
         "sottocategoria": None, "fattura_id": 3, "ricorrente": False, "note": None},
        {"id": 8, "data": "2026-08-01", "importo": 2600.00, "tipo": "entrata",
         "descrizione": "Fattura 2026/004 — Nordwind GmbH", "categoria": "fatturato",
         "sottocategoria": None, "fattura_id": 4, "ricorrente": False, "note": None},
        {"id": 9, "data": "2026-08-02", "importo": 12.40, "tipo": "uscita",
         "descrizione": "Commissioni bonifico estero", "categoria": "bancarie",
         "sottocategoria": None, "fattura_id": None, "ricorrente": False, "note": None},
    ],
    "spese": [
        {"id": 1, "data": "2026-07-14", "importo": 50.00, "tipo": "uscita",
         "descrizione": "Bonifico a favore di Emanuele Bellotti",
         "categoria": "Personale", "sottocategoria": "Bonifici"},
        {"id": 2, "data": "2026-07-14", "importo": 20.00, "tipo": "uscita",
         "descrizione": "SDD Satispay Europe S.A.",
         "categoria": "Personale", "sottocategoria": None},
        {"id": 3, "data": "2026-07-13", "importo": 3.30, "tipo": "uscita",
         "descrizione": "pagamento con carta - carta *2058-mcdonald's 35 milano mi ita",
         "categoria": "Personale", "sottocategoria": "Ristoranti"},
        {"id": 4, "data": "2026-08-03", "importo": 1.10, "tipo": "uscita",
         "descrizione": "pagamento con carta - carta *2058-mcdonald's 35 milano mi ita",
         "categoria": "Personale", "sottocategoria": "Ristoranti"},
        {"id": 5, "data": "2026-07-12", "importo": 1200.00, "tipo": "entrata",
         "descrizione": "BONIFICO ISTANTANEO DA B2FORGE SRL SALDO FATTURA 2026/001",
         "categoria": "Stipendio", "sottocategoria": None},
        {"id": 6, "data": "2026-08-05", "importo": 42.90, "tipo": "uscita",
         "descrizione": "addebito diretto sepa core - vodafone italia s.p.a. rata mensile",
         "categoria": "Fisso", "sottocategoria": "Telefonia"},
        # Giroconto dalla P.IVA: tipo=entrata con la categoria dedicata,
        # esattamente come lo scrive fatture/giroconto.py.
        {"id": 7, "data": "2026-08-06", "importo": 2320.55, "tipo": "entrata",
         "descrizione": "Giroconto da P.IVA — fattura 2026/003",
         "categoria": "Giroconto P.IVA", "sottocategoria": None},
    ],
    # Saldo di apertura del conto personale: e' da qui che parte il saldo
    # mostrato in home e su /spese.
    "impostazioni": [{
        "valido_dal": "2024-01-01", "saldo_iniziale": 4200.00,
        "percentuale_risparmio": 0.25, "perc_fondo_emergenze": 0.40,
        "perc_viaggi": 0.20, "perc_fondo_casa": 0.20,
        "perc_regali": 0.10, "perc_altro": 0.10,
    }],
    # Il risparmio dichiarato periodo per periodo. Non e' una riga di
    # `spese`: e' denaro che esce dal conto e va nei salvadanai Revolut —
    # v_risparmi_mese lo sottrae dal saldo, e cosi' fa saldo_conto().
    "risparmi_periodo": [
        {"data_bonifico": "2026-07-12", "effettivo_risparmio": 300.00},
    ],
    # Snapshot Revolut, dall'estratto conto consolidato.
    "b2f_revolut": [{
        "data": "2026-08-12", "conto": 604.55, "risparmi": 8525.39,
        "investimenti": 1240.00, "fonte": "estratto", "note": None,
        "salvadanai": {"emergenze": 4100.00, "casa": 2500.00,
                       "vacanze": 1400.00, "regali": 400.00, "altro": 125.39},
    }],
    "b2f_webauthn_credentials": [],
}

# `v_spese` e' la vista che porta i nomi di categoria/sottocategoria e i
# campi derivati: l'app legge sempre da li', mai da `spese`, quindi il
# finto database deve averla anche lui o le pagine restano vuote.
DB["v_spese"] = [
    {**r, "mese": int(r["data"][5:7]), "anno": int(r["data"][:4]),
     "metodo_pagamento": None, "categoria_link_id": None}
    for r in DB["spese"]
]

# v_risparmi_mese: i nomi delle colonne hanno spazi e maiuscole come nella
# vista vera (spese/dati.py::periodi_risparmio li traduce).
DB["v_risparmi_mese"] = [
    {"Data bonifico": "2026-07-12", "Data prossimo bonifico": "2026-08-06",
     "Mese": "luglio", "Importo Bonifico": 1200.00,
     "Importo Prima Del Bonifico": 4200.00, "Totale Fisso": 42.90,
     "Totale Personale": 74.40, "Totale Benzina": 0, "Totale Viaggi": 0,
     "Totale Speso": 117.30, "Totale Altre Entrate": 0,
     "Totale Rimanente": 1082.70, "Risparmio consigliato (€)": 325.00,
     "Risparmio effettivo (€)": 300.00, "Totale Rimanente (finale)": 4982.70,
     "Quota Fondo Emergenze": 120.00, "Quota Viaggi": 60.00,
     "Quota Fondo Casa": 60.00, "Quota Regali": 30.00, "Quota Altro": 30.00},
]


def _fattura(fid, prog, data, cliente_id, righe, stato, data_incasso=None,
             cassa=True, spesa_piva_id=None):
    cli = next(c for c in DB["b2f_clienti"] if c["id"] == cliente_id)
    snap = {k: cli.get(k) for k in ("tipo", "denominazione", "nome", "cognome",
                                    "piva", "cf", "indirizzo", "cap", "comune",
                                    "provincia", "nazione", "sdi", "pec", "email")}
    # Scorporo, come nell'app: il corrispettivo concordato non cambia, la
    # rivalsa si estrae da dentro.
    corrispettivo = round(sum(r["qta"] * r["prezzo"] for r in righe), 2)
    cassa_imp = round(corrispettivo - corrispettivo / 1.04, 2) if cassa else 0.0
    imponibile = corrispettivo
    bollo_dovuto = imponibile > 77.47
    bollo = 2.00 if bollo_dovuto else 0.0
    totale = round(imponibile + (bollo if bollo_dovuto else 0), 2)
    return {
        "id": fid, "anno": 2026, "progressivo": prog,
        "numero": f"2026/{prog:03d}", "data": data, "tipo_doc": "TD01",
        "natura_iva": "N2.2", "cliente_id": cliente_id, "cliente_snapshot": snap,
        "righe": [{**r, "tot": round(r["qta"] * r["prezzo"], 2)} for r in righe],
        "imponibile": imponibile, "bollo": bollo, "bollo_addebitato": bollo_dovuto,
        "cassa_perc": 4.0 if cassa else 0.0, "cassa_importo": cassa_imp,
        "totale": totale, "divisa": "EUR",
        "pagamento_mod": "Bonifico bancario", "pagamento_cond": "30 gg data fattura",
        "scadenza": None, "iban": DB["b2f_emittente"][0]["iban"],
        "stato": stato, "data_incasso": data_incasso,
        "data_invio_studio": (data if stato != "bozza" else None),
        "data_trasmissione_sdi": (data if stato in ("trasmessa_sdi", "incassata") else None),
        "numero_sdi": None,
        "spesa_piva_id": spesa_piva_id, "pdf_url": None, "xml_url": None,
        "note": None,
    }


DB["b2f_fatture"] = [
    _fattura(1, 1, "2026-06-05", 1,
             [{"descrizione": "Attività di consulenza SAP / sviluppo ABAP", "qta": 20, "um": "", "prezzo": 250.00}],
             "incassata", "2026-06-30", spesa_piva_id=3),
    _fattura(2, 2, "2026-06-20", 2,
             [{"descrizione": "Consulenza infrastruttura di rete", "qta": 9, "um": "h", "prezzo": 195.00}],
             "incassata", "2026-07-10", spesa_piva_id=5),
    _fattura(3, 3, "2026-07-03", 1,
             [{"descrizione": "Sviluppo modulo reportistica", "qta": 20, "um": "h", "prezzo": 190.00},
              {"descrizione": "Sessione di formazione al team", "qta": 1, "um": "gg", "prezzo": 350.00}],
             "incassata", "2026-07-31", spesa_piva_id=7),
    _fattura(4, 4, "2026-07-22", 3,
             [{"descrizione": "Migration assessment", "qta": 12, "um": "h", "prezzo": 205.00}],
             "incassata", "2026-08-01", cassa=False, spesa_piva_id=8),
    _fattura(5, 5, "2026-08-01", 1,
             [{"descrizione": "Manutenzione evolutiva agosto", "qta": 18, "um": "h", "prezzo": 190.00}],
             "trasmessa_sdi"),
    _fattura(6, 6, "2026-08-03", 2,
             [{"descrizione": "Intervento urgente su backup", "qta": 5, "um": "h", "prezzo": 195.00}],
             "inviata_studio"),
    _fattura(7, 7, "2026-08-04", 4,
             [{"descrizione": "Recupero dati da disco danneggiato", "qta": 3, "um": "h", "prezzo": 90.00}],
             "bozza"),
]


# ---------------------------------------------------------------------------
# Finto client Supabase — riproduce solo la parte di API usata dall'app
# ---------------------------------------------------------------------------

class _Res:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self.table = table
        self.filters = []
        self._order = None
        self._desc = False
        self._limit = None
        self._single = False
        self._count = False
        self._head = False
        self._op = "select"
        self._payload = None
        self._range = None

    # -- costruzione ---------------------------------------------------
    def select(self, *a, **k):
        self._op = "select"
        self._count = bool(k.get("count"))
        self._head = bool(k.get("head"))
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op, self._payload = "upsert", payload
        self._conflict = on_conflict or "id"
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val)); return self

    def neq(self, col, val):
        self.filters.append(("neq", col, val)); return self

    def in_(self, col, vals):
        self.filters.append(("in", col, vals)); return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val)); return self

    def lte(self, col, val):
        self.filters.append(("lte", col, val)); return self

    def order(self, col, desc=False):
        self._order, self._desc = col, desc; return self

    def limit(self, n):
        self._limit = n; return self

    def range(self, start, end):
        self._range = (start, end); return self

    def single(self):
        self._single = True; return self

    # -- esecuzione ----------------------------------------------------
    def _match(self, row):
        for kind, col, val in self.filters:
            v = row.get(col)
            if kind == "eq" and v != val: return False
            if kind == "neq" and v == val: return False
            if kind == "in" and v not in val: return False
            if kind == "gte" and (v is None or str(v) < str(val)): return False
            if kind == "lte" and (v is None or str(v) > str(val)): return False
        return True

    def execute(self):
        rows = DB.setdefault(self.table, [])

        if self._op == "upsert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                chiave = getattr(self, "_conflict", "id")
                esistente = next((r for r in rows if r.get(chiave) == it.get(chiave)), None)
                if esistente:
                    esistente.update(deepcopy(it))
                    out.append(esistente)
                else:
                    new = deepcopy(it)
                    new.setdefault("id", max([r.get("id", 0) for r in rows], default=0) + 1)
                    rows.append(new)
                    out.append(new)
            return _Res([deepcopy(r) for r in out])

        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                new = deepcopy(it)
                new.setdefault("id", max([r.get("id", 0) for r in rows], default=0) + 1)
                rows.append(new)
                out.append(new)
            return _Res(out)

        sel = [r for r in rows if self._match(r)]

        if self._op == "update":
            for r in sel:
                r.update(deepcopy(self._payload))
            return _Res([deepcopy(r) for r in sel])

        if self._op == "delete":
            for r in sel:
                rows.remove(r)
            return _Res([])

        if self._order:
            sel = sorted(sel, key=lambda r: (r.get(self._order) is None,
                                             r.get(self._order)),
                         reverse=self._desc)
        if self._range:
            start, end = self._range
            sel = sel[start:end + 1]
        elif self._limit:
            sel = sel[:self._limit]

        if self._head:
            return _Res(None, len(sel))
        if self._single:
            if not sel:
                raise RuntimeError(f"nessuna riga in {self.table}")
            return _Res(deepcopy(sel[0]), len(sel) if self._count else None)
        return _Res([deepcopy(r) for r in sel], len(sel) if self._count else None)


class _FakeClient:
    def table(self, name):
        return _Query(name)

    def rpc(self, fn, params=None):
        class _R:
            def execute(_self):
                if fn == "b2f_next_progressivo":
                    anno = (params or {}).get("p_anno", 2026)
                    vals = [f["progressivo"] for f in DB["b2f_fatture"]
                            if f["anno"] == anno]
                    return _Res(max(vals, default=0) + 1)
                return _Res(None)
        return _R()


# ---------------------------------------------------------------------------
# Montaggio
# ---------------------------------------------------------------------------

import shared.supabase_client as sc          # noqa: E402
sc.get_client = lambda: _FakeClient()
sc.is_configured = lambda: True

import app as b2f_app                        # noqa: E402

# I moduli hanno importato get_client/is_configured per nome: li rimpiazzo
# anche nei rispettivi namespace.
import fatture.views, fatture.storico, fatture.clienti          # noqa: E402
import fatture.editor, fatture.emittente, fatture.fiscale       # noqa: E402
import spese.views                                              # noqa: E402
for mod in (b2f_app, fatture.views, fatture.storico, fatture.clienti,
            fatture.editor, fatture.emittente, fatture.fiscale, spese.views):
    if hasattr(mod, "get_client"):
        mod.get_client = lambda: _FakeClient()
    if hasattr(mod, "is_configured"):
        mod.is_configured = lambda: True

application = b2f_app.app

if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
    application.run(host="127.0.0.1", port=porta, debug=False, use_reloader=False)
