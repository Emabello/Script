"""
Verifica che ogni menu a tendina dell'app elenchi i dati in ordine
alfabetico per la descrizione mostrata (la regola sta in shared/ordina.py).

Percorre tutte le pagine con l'harness di `preview.py` — finto client
Supabase, dati finti ma realistici — estrae ogni `<select>` e ogni
`<datalist>` dall'HTML servito e ne controlla l'ordine delle opzioni.

    python3 tools/verifica_menu.py

Cosa NON controlla, ed e' voluto: i menu in cui l'ordine e' informazione
(mesi, anni, stati della fattura, scenari di accantonamento). Sono
elencati in ECCEZIONI con il motivo, uno per uno: se un menu nuovo
compare qui come "non ordinato", la domanda giusta e' se sia un elenco di
dati (allora si ordina) o una sequenza (allora si aggiunge qui).

Le prime opzioni "vuote" ("— seleziona —", "Tutte le categorie", "Tutti i
tipi") restano in testa: sono l'assenza di filtro, non un dato.
"""
import os
import re
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.preview import application                      # noqa: E402
from shared.ordina import chiave_alfabetica                # noqa: E402


# (identificativo del menu) -> perche' non e' alfabetico
ECCEZIONI = {
    "Mese": "i mesi vanno in ordine di calendario",
    "Anno": "gli anni vanno dal piu' recente",
    "Stato": "gli stati seguono il ciclo di vita della fattura",
    "statoSel": "gli stati seguono il ciclo di vita della fattura",
    "f_scenario": "gli scenari vanno dal minimo al piu' prudente",
    "d_tipo": "i tipi documento vanno per codice (TD01, TD04, TD06)",
    "f_regime": "un'opzione sola",
}

PAGINE = [
    "/", "/saldi",
    "/fatture", "/fatture/storico", "/fatture/nuova", "/fatture/clienti",
    "/fatture/clienti/nuovo", "/fatture/clienti/1", "/fatture/situazione",
    "/fatture/parametri", "/fatture/spese-piva", "/fatture/spese-piva/nuova",
    "/fatture/spese-piva/1", "/fatture/emittente",
    "/spese", "/spese/movimenti", "/spese/movimenti/nuovo", "/spese/movimenti/1",
    "/spese/importa", "/spese/risparmi", "/spese/revolut",
]

# Placeholder di testa: non sono dati, non entrano nel confronto.
VUOTE = re.compile(r"^\s*(—|-|tutt[ieo]\b|nessun|seleziona|— seleziona)", re.I)


class _Menu(HTMLParser):
    """Estrae (identificativo, [etichette]) da ogni select/datalist."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.menu = []
        self._corrente = None
        self._testo = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("select", "datalist"):
            nome = (a.get("aria-label") or a.get("id") or a.get("class") or tag)
            self._corrente = (nome, [])
        elif tag == "option" and self._corrente is not None:
            # Nelle datalist le <option> non si chiudono e non hanno testo:
            # una nuova apertura e' la fine della precedente, e l'etichetta
            # e' il value.
            self._chiudi_opzione()
            self._testo = a.get("value") or ""

    def handle_data(self, data):
        if self._testo is not None and data.strip():
            self._testo = data.strip()

    def _chiudi_opzione(self):
        if self._corrente is not None and self._testo is not None:
            self._corrente[1].append(self._testo)
        self._testo = None

    def handle_endtag(self, tag):
        if tag == "option":
            self._chiudi_opzione()
        elif tag in ("select", "datalist") and self._corrente is not None:
            self._chiudi_opzione()
            self.menu.append(self._corrente)
            self._corrente = None


# Menu riempiti via JavaScript: nell'HTML c'e' solo il segnaposto,
# l'elenco vero arriva da qui. (identificativo, url, come si legge
# l'etichetta di ogni voce della risposta JSON.)
API = [
    ("c_pick (clienti dell'editor)", "/fatture/api/clienti-picker",
     lambda c: c.get("denominazione")
     or " ".join(x for x in (c.get("nome"), c.get("cognome")) if x)),
    ("f_categoria (albero categorie)", "/spese/api/categorie",
     lambda g: g.get("categoria")),
]


def _in_ordine(etichette):
    dati = [e for e in etichette if not VUOTE.match(e)]
    return dati == sorted(dati, key=chiave_alfabetica), dati


def main():
    client = application.test_client()
    problemi, controllati, saltati = [], 0, 0

    for url in PAGINE:
        # follow_redirects: "/fatture" e "/spese" rispondono 308 verso la
        # variante con lo slash finale.
        r = client.get(url, follow_redirects=True)
        if r.status_code != 200:
            problemi.append(f"{url} -> HTTP {r.status_code}")
            continue
        p = _Menu()
        p.feed(r.get_data(as_text=True))
        for nome, etichette in p.menu:
            if len(etichette) < 2:
                continue
            if nome in ECCEZIONI:
                saltati += 1
                continue
            controllati += 1
            ok, dati = _in_ordine(etichette)
            if not ok:
                atteso = sorted(dati, key=chiave_alfabetica)
                problemi.append(
                    f"{url} · menu «{nome}» non alfabetico\n"
                    f"    ha:      {', '.join(dati[:8])}\n"
                    f"    dovrebbe: {', '.join(atteso[:8])}")

    for nome, url, etichetta in API:
        r = client.get(url)
        if r.status_code != 200:
            problemi.append(f"{url} -> HTTP {r.status_code}")
            continue
        voci = [etichetta(x) or "" for x in (r.get_json() or [])]
        if len(voci) < 2:
            continue
        controllati += 1
        ok, dati = _in_ordine(voci)
        if not ok:
            problemi.append(
                f"{url} · elenco «{nome}» non alfabetico\n"
                f"    ha:      {', '.join(dati[:8])}\n"
                f"    dovrebbe: {', '.join(sorted(dati, key=chiave_alfabetica)[:8])}")

    # Le sottocategorie dei form si costruiscono in pagina dall'albero: se
    # l'albero e' ordinato lo sono anche loro, ma l'ordine dentro ogni
    # gruppo e' un secondo ordinamento e va guardato a parte.
    r = client.get("/spese/api/categorie")
    for gruppo in (r.get_json() or []):
        subs = [v.get("sottocategoria") for v in gruppo.get("voci") or []
                if v.get("sottocategoria")]
        if len(subs) < 2:
            continue
        controllati += 1
        if subs != sorted(subs, key=chiave_alfabetica):
            problemi.append(
                f"/spese/api/categorie · sottocategorie di «{gruppo['categoria']}» "
                f"non alfabetiche\n    ha:      {', '.join(subs)}\n"
                f"    dovrebbe: {', '.join(sorted(subs, key=chiave_alfabetica))}")

    print(f"{controllati} menu controllati, {saltati} saltati "
          f"(ordine voluto), su {len(PAGINE)} pagine")
    for p in problemi:
        print("  ✗ " + p)
    if not problemi:
        print("  ✓ tutti in ordine alfabetico per descrizione")
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
