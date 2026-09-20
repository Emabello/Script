"""
Smoke test di tutte le rotte: nessuna pagina deve rompersi.

    python3 tools/verifica_rotte.py

Tre passate, e sono tre domande diverse:

1. **Ogni GET risponde 200?** Con i dati finti di `tools/preview.py`, e con
   gli id veri presenti li' dentro, cosi' le rotte con `<int:...>` non
   vanno a vuoto. Un 200 che contiene un traceback conta come rotto: e'
   il caso peggiore, perche' la pagina sembra viva.

2. **L'app regge le tabelle vuote?** Un'installazione nuova, o una
   tabella che non e' ancora stata popolata, non deve dare 500. Si
   svuota una tabella alla volta e si ricontrolla tutto.

3. **Le API rispondono 4xx a un payload sbagliato, mai 5xx?** Un 500
   arriva al browser come pagina HTML: il `fetch` che si aspetta JSON
   fallisce sul parse, e l'utente legge "Errore rete: Unexpected token
   '<'" invece del motivo vero. Le API di questa app rispondono gia'
   `{"error": ...}` quasi ovunque — questa passata trova i buchi.

Le rotte che parlano con l'esterno (portale ore, Google) restano fuori:
qui non c'e' rete, e un fallimento direbbe solo quello.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("APP_PIN", None)

import logging                                            # noqa: E402
logging.disable(logging.ERROR)

from tools.preview import application, DB                 # noqa: E402


# Rotte che dipendono dal portale ore o da Google: senza rete non dicono
# niente di utile. Non sono "saltate perche' rotte" — sono fuori perimetro.
ESTERNE = {
    "/api/catalog", "/api/range", "/api/google/preview", "/api/google/status",
    "/api/google/calendars", "/oauth/start", "/oauth/callback",
    "/fatture/api/fatture-per-ore", "/ore",
}

# Risposte binarie: il test legge il corpo come testo, e un PNG non lo e'.
BINARIE = {"/icon-192.png", "/icon-512.png", "/apple-touch-icon.png",
           "/apple-touch-icon-precomposed.png", "/fatture/api/export/xlsx"}

# Spie di un 500 travestito da 200.
SPIE = ("Traceback (most recent call last)", "jinja2.exceptions",
        "werkzeug.exceptions", "TypeError:", "KeyError:", "AttributeError:")

# Le pagine HTML, per la passata sulle tabelle vuote.
PAGINE = ["/", "/saldi", "/fatture/", "/fatture/storico", "/fatture/nuova",
          "/fatture/clienti", "/fatture/clienti/nuovo", "/fatture/situazione",
          "/fatture/parametri", "/fatture/emittente", "/fatture/spese-piva",
          "/fatture/spese-piva/nuova", "/spese/", "/spese/movimenti",
          "/spese/movimenti/nuovo", "/spese/risparmi", "/spese/revolut",
          "/spese/importa", "/health"]

VUOTI = [
    ("database completamente vuoto",
     ["b2f_fatture", "b2f_clienti", "spese", "v_spese", "b2f_spese_piva",
      "b2f_revolut", "impostazioni", "v_risparmi_mese", "risparmi_periodo",
      "b2f_emittente", "b2f_parametri_fiscali", "b2f_saldi_verifica"]),
    ("senza emittente e parametri", ["b2f_emittente", "b2f_parametri_fiscali"]),
    ("senza apertura del conto", ["impostazioni"]),
    ("senza movimenti", ["spese", "v_spese", "v_risparmi_mese"]),
    ("senza fatture", ["b2f_fatture"]),
    ("senza snapshot Revolut", ["b2f_revolut"]),
    ("senza categorie",
     ["cfg_categorie", "cfg_sottocategorie", "cfg_categoria_sottocategoria"]),
]

# Payload sbagliati sulle API che scrivono. Ci si aspetta 4xx, mai 5xx.
MALFORMATI = [
    ("POST",  "/spese/api/movimenti", {}),
    ("POST",  "/spese/api/movimenti", {"importo": "abc", "tipo": "uscita", "data": "2026-01-01"}),
    ("POST",  "/spese/api/movimenti", {"importo": 10, "tipo": "uscita", "data": "non-una-data"}),
    ("PATCH", "/spese/api/movimenti/999999", {"importo": 1}),
    ("DELETE", "/spese/api/movimenti/999999", None),
    ("POST",  "/spese/api/risparmi/esegui", {}),
    ("POST",  "/spese/api/risparmi/esegui", {"importo": "tanti", "data": "ieri"}),
    ("PATCH", "/spese/api/risparmi", {"x": 1}),
    ("POST",  "/spese/api/revolut", {}),
    ("POST",  "/spese/api/revolut", {"data": "non-data", "conto": "x"}),
    ("POST",  "/spese/api/importa/salva", {}),
    ("POST",  "/fatture/api/fatture", {}),
    ("POST",  "/fatture/api/fatture", {"anno": "abc", "progressivo": "x", "data": "y",
                                       "tipo_doc": "TD01", "cliente_snapshot": {},
                                       "righe": [], "totale": "molti"}),
    ("PATCH", "/fatture/api/fatture/999999", {"totale": 1}),
    ("PATCH", "/fatture/api/fatture/1/stato", {"stato": "inesistente"}),
    ("POST",  "/fatture/api/fatture/1/giroconto", {"scenario": "inventato"}),
    ("POST",  "/fatture/api/clienti", {}),
    ("PATCH", "/fatture/api/parametri", {"coeff_ateco": "abc"}),
    ("POST",  "/fatture/api/spese-piva", {"importo": "x", "data": "y", "tipo": "z"}),
]


def _id(tabella, quanti=2):
    return [r["id"] for r in DB.get(tabella, []) if r.get("id")][:quanti]


def _url_concreti(rule):
    """Sostituisce i segnaposto con id che esistono davvero."""
    if "<int:fid>" in rule:
        return [rule.replace("<int:fid>", str(i)) for i in _id("b2f_fatture")]
    if "<int:cid>" in rule:
        return [rule.replace("<int:cid>", str(i)) for i in _id("b2f_clienti")]
    if "<int:mid>" in rule:
        tab = "b2f_spese_piva" if "spese-piva" in rule else "spese"
        return [rule.replace("<int:mid>", str(i)) for i in _id(tab)]
    return [rule] if "<" not in rule else []


def passata_get(c):
    problemi, n = [], 0
    for r in sorted(application.url_map.iter_rules(), key=lambda x: str(x.rule)):
        rule = str(r.rule)
        if "GET" not in r.methods or rule.startswith("/static/"):
            continue
        for url in _url_concreti(rule):
            if url in ESTERNE:
                continue
            n += 1
            try:
                resp = c.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    problemi.append(f"{url} -> HTTP {resp.status_code}")
                    continue
                if url in BINARIE:
                    continue
                corpo = resp.get_data(as_text=True)
                for spia in SPIE:
                    if spia in corpo:
                        problemi.append(f"{url} -> 200 ma contiene «{spia}»")
                        break
            except Exception as e:
                problemi.append(f"{url} -> {type(e).__name__}: {str(e)[:100]}")
    return n, problemi


def passata_vuoti(c):
    problemi = []
    for nome, tabelle in VUOTI:
        backup = {t: DB.get(t) for t in tabelle}
        for t in tabelle:
            DB[t] = []
        for p in PAGINE:
            try:
                resp = c.get(p, follow_redirects=True)
                if resp.status_code != 200:
                    problemi.append(f"[{nome}] {p} -> HTTP {resp.status_code}")
            except Exception as e:
                problemi.append(f"[{nome}] {p} -> {type(e).__name__}: {str(e)[:80]}")
        for t, v in backup.items():
            DB[t] = v
    return len(VUOTI) * len(PAGINE), problemi


def passata_malformati(c):
    problemi = []
    for metodo, url, body in MALFORMATI:
        try:
            f = getattr(c, metodo.lower())
            resp = f(url, json=body) if body is not None else f(url)
            if resp.status_code >= 500:
                problemi.append(f"{metodo} {url} -> HTTP {resp.status_code} "
                                f"(atteso 4xx) · body {str(body)[:50]}")
        except Exception as e:
            problemi.append(f"{metodo} {url} -> {type(e).__name__}: {str(e)[:80]}")
    return len(MALFORMATI), problemi


def main():
    c = application.test_client()
    tutto = []
    for etichetta, fn in (("GET su tutte le rotte", passata_get),
                          ("tabelle vuote", passata_vuoti),
                          ("payload malformati", passata_malformati)):
        n, problemi = fn(c)
        segno = "✗" if problemi else "✓"
        print(f"{segno} {etichetta}: {n} prove, {len(problemi)} da guardare")
        for p in problemi:
            print(f"    {p}")
        tutto += problemi
        print()
    if tutto:
        print(f"{len(tutto)} cose da guardare.")
        return 1
    print("tutte le rotte rispondono, anche a tabelle vuote e payload sbagliati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
