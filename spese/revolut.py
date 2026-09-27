"""
spese/revolut.py — Il terzo conto: Revolut (liquidità, risparmi, investimenti).

PERCHE' ESISTE
--------------
I risparmi non stanno sul conto personale: stanno su Revolut. La cosa era
già dentro il modello dei dati, ma implicita — `v_risparmi_mese` sottrae
`effettivo_risparmio` dal saldo corrente proprio perché quel denaro *esce*
dal conto e va altrove. Quell'"altrove" non aveva un posto in cui essere
mostrato, quindi il risparmio spariva dalla vista: usciva da un conto e
non entrava in nessuno.

Qui c'è quel posto. E il cerchio si chiude: la somma di quanto hai
dichiarato come risparmiato dovrebbe combaciare con quanto c'è davvero
nei salvadanai Revolut. Se non combacia, uno dei due numeri è sbagliato —
ed è una cosa che vale la pena sapere.

I SALVADANAI SONO GIA' LE CATEGORIE DELL'APP
--------------------------------------------
Emergenze, Fondo casa, Vacanze, Regali, Altro sono esattamente le cinque
quote di `impostazioni` (`perc_fondo_emergenze`, `perc_fondo_casa`,
`perc_viaggi`, `perc_regali`, `perc_altro`). La pagina Risparmi calcola
quanto *dovrebbe* esserci in ognuno; Revolut sa quanto c'è. Il confronto
è il motivo per cui i nomi vanno tenuti allineati.

COME ARRIVANO I NUMERI
----------------------
Dall'estratto conto consolidato che Revolut esporta in .xlsx. Non è un
vero xlsx: è un CSV infilato dentro un foglio, tutto nella colonna A, con
i caratteri accentati e il simbolo dell'euro passati due volte per la
codifica sbagliata. Il parser se ne occupa.

**L'estratto non contiene il valore del portafoglio investimenti**: dà i
redditi del periodo (dividendi, vendite, PnL) ma nessuna valorizzazione
delle posizioni. Quel numero si scrive a mano, e l'app dice chiaramente
che è stato scritto a mano e a che data.

Lo stesso vale per i saldi dei singoli salvadanai: dal 15 aprile 2026 i
salvadanai vivono dentro il "Deposito senza vincoli" e l'estratto ne dà
solo il totale. Il totale arriva dall'import, la ripartizione la scrivi tu.

I MOVIMENTI
-----------
Dallo stesso file si leggono anche i movimenti, riga per riga, con la
stessa forma di quelli degli altri due conti: vivono in
`spese/revolut_movimenti.py`. Qui la pagina li mostra e li fa salvare.

Rotte HTML:
  GET  /conti/revolut

Rotte JSON:
  GET  /spese/api/revolut                 -> ultimo saldo registrato
  POST /spese/api/revolut/leggi           -> (multipart) legge saldi e movimenti, non scrive
  POST /spese/api/revolut                 -> salva uno snapshot
"""
import csv
import io
import json
import re
from datetime import date, datetime

import openpyxl
from flask import Response, jsonify, request

from . import dati as D
from . import spese_bp
from . import revolut_movimenti as RM
from shared.fmt import eur, eur_segno, data_it
from shared.design import icon, info
from shared.ordina import ordina
from shared.theme import render_page


TABELLA = "b2f_revolut"

# I cinque salvadanai. E' l'unico posto in cui la corrispondenza fra i
# tre modi di chiamare la stessa cosa sta scritta: il nome su Revolut, la
# percentuale in `impostazioni` e la colonna di v_risparmi_mese. Erano
# elenchi separati in due file, e due elenchi separati prima o poi
# divergono — qui invece la pagina Risparmi legge da questo.
#
# "Casa" e "Fondo casa" sono lo stesso salvadanaio con due nomi: il conto
# separato si chiamava "Fondo casa", dentro il deposito e' diventato
# "Casa". Idem "Emergenze"/"Fondo emergenze". Gli alias servono a
# riconoscerli entrambi senza creare due secchielli per la stessa cosa.
SALVADANAI = (
    # (chiave, nome su Revolut, nome nell'app, % in `impostazioni`,
    #  colonna di v_risparmi_mese, alias riconosciuti nell'estratto)
    ("emergenze", "Emergenze",  "Fondo emergenze", "perc_fondo_emergenze",
     "quota_emergenze", ("emergenze", "fondo emergenze")),
    ("casa",      "Fondo casa", "Fondo casa",      "perc_fondo_casa",
     "quota_casa",      ("casa", "fondo casa")),
    ("vacanze",   "Vacanze",    "Viaggi",          "perc_viaggi",
     "quota_viaggi",    ("vacanze", "viaggi")),
    ("regali",    "Regali",     "Regali",          "perc_regali",
     "quota_regali",    ("regali",)),
    ("altro",     "Altro",      "Altro",           "perc_altro",
     "quota_altro",     ("altro",)),
)
SALVADANAI_CHIAVI = tuple(s[0] for s in SALVADANAI)


def _chiave_salvadanaio(nome: str) -> str | None:
    """Dal nome che compare nell'estratto alla chiave interna, o None."""
    n = (nome or "").strip().lower().replace("eur", "").strip()
    for riga in SALVADANAI:
        if n in riga[-1]:
            return riga[0]
    return None


# ---------------------------------------------------------------------------
# Lettura dell'estratto
# ---------------------------------------------------------------------------

def _demojibake(s) -> str:
    """
    Rimette a posto il testo passato due volte per la codifica sbagliata.

    L'estratto e' UTF-8 letto come cp1252 e poi riscritto: "à" diventa
    "Ã ", "€" diventa "â‚¬". Si disfa riapplicando la codifica al
    contrario, finche' smette di cambiare. Si prova prima cp1252 e poi
    latin-1 perche' i due differiscono proprio sui caratteri che qui
    contano (€ sta in cp1252, non in latin-1).
    """
    s = "" if s is None else str(s)
    for _ in range(4):
        for enc in ("cp1252", "latin-1"):
            try:
                t = s.encode(enc).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if t != s:
                s = t
                break
        else:
            return s
    return s


def _importo(s: str) -> float | None:
    """"8.525,39€" -> 8525.39. None se la cella non e' un importo."""
    t = (s or "").replace("\xa0", " ").replace(" ", "").strip()
    # Il simbolo o il codice della valuta: «€», «¥», ma anche «13.600,00 EGP».
    t = re.sub(r"[€$£¥+]|[A-Z]{3}", "", t).strip()
    # "12.50" senza virgola: il punto e' il separatore decimale, non
    # quello delle migliaia. Letto all'italiana diventava 1250 — un
    # errore di cento volte, su un movimento che sembrava normalissimo.
    # "1.234" (tre cifre dopo il punto) resta invece mille e rotti.
    if "," not in t and re.fullmatch(r"-?\d+\.\d{1,2}", t):
        return float(t)
    if not re.fullmatch(r"-?[\d.]*,?\d*", t) or not re.search(r"\d", t):
        return None
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return None


_MESI = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
         "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
         # L'estratto si scarica anche in inglese: stesse colonne, altri
         # nomi dei mesi. Solo quelli che non coincidono con l'italiano.
         "jan": 1, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
         "oct": 10, "dec": 12}


def _data(s: str):
    """
    "12 ago 2026", "20/04/26", "20/04/2026" o "2026-04-20" -> date.
    None se non e' una data.
    """
    t = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s+([a-zà-ú]{3})[a-zà-ú]*\.?\s+(\d{4})", t, re.I)
    if m and m.group(2).lower() in _MESI:
        try:
            return date(int(m.group(3)), _MESI[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", t)
    if m:
        anno = int(m.group(3))
        try:
            return date(anno + 2000 if anno < 100 else anno,
                        int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _righe_csv(file_bytes: bytes) -> list[list[str]]:
    """
    Le righe dell'estratto, come liste di celle.

    Il file e' un CSV messo dentro un xlsx: ogni riga del foglio ha il
    contenuto in colonna A, virgole e virgolette comprese. Si rimette
    insieme il testo e lo si rilegge come CSV vero — non si puo' leggere
    per celle, perche' celle non ce ne sono.
    """
    if not file_bytes.startswith(b"PK"):
        # Il consolidato si scarica anche come .csv: stesso contenuto, e
        # gli stessi accenti passati due volte per la codifica sbagliata.
        # (Un xlsx e' uno zip, e uno zip comincia sempre con «PK».)
        try:
            testo = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            testo = file_bytes.decode("cp1252", errors="replace")
        testo = "\n".join(_demojibake(r) for r in testo.splitlines())
        return list(csv.reader(io.StringIO(testo)))
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.active
    testo = "\n".join(_demojibake(r[0]) for r in ws.iter_rows(values_only=True))
    return list(csv.reader(io.StringIO(testo)))


def _data_estratto(righe, nome_file: str = ""):
    """
    A che data sono i saldi.

    L'estratto non ha una riga che lo dichiari. Il nome del file si':
    "...v2_20240910_20260812_it_....xlsx" e' l'intervallo, e la seconda
    data e' la fine. Se manca (file rinominato) si ripiega sull'ultimo
    movimento presente, che e' comunque dentro il periodo.
    """
    # Due forme del nome: «..._20240910_20260812_...» e, nel csv,
    # «..._2024-09-10_2026-09-27_...».
    date_nome = [d.replace("-", "") for d in
                 re.findall(r"(20\d{2}-?\d{2}-?\d{2})", nome_file or "")]
    if date_nome:
        try:
            return datetime.strptime(date_nome[-1], "%Y%m%d").date()
        except ValueError:
            pass
    ultima = None
    for r in righe:
        if not r:
            continue
        d = _data(r[0])
        if d and (ultima is None or d > ultima):
            ultima = d
    return ultima or date.today()


def _sezione_da_titolo(titolo: str) -> str | None:
    """
    Da un titolo di sezione ("Riepiloghi dei conti deposito", "Estratti
    conto dei conti correnti", "Savings Transaction Statements"…) al tipo
    di conto: 'risparmi', 'investimenti' o 'conto'.
    """
    basso = titolo.lower()
    if any(k in basso for k in ("deposit", "risparm", "saving", "salvadana")):
        return "risparmi"
    if any(k in basso for k in ("investment", "investiment", "trading",
                                "cripto", "crypto", "commodit")):
        return "investimenti"
    return "conto"


def _intestazione_movimenti(celle: list[str]) -> dict | None:
    """
    Riconosce la riga di intestazione della tabella dei movimenti e dice
    in che colonna sta cosa. None se la riga non e' un'intestazione.

    Le colonne si trovano **per nome**, non per posizione: l'estratto
    italiano e quello inglese hanno lo stesso contenuto con nomi diversi
    ("Denaro in uscita" / "Money out"), e basta che Revolut aggiunga una
    colonna per spostare tutte le altre di un posto. Leggere la terza
    colonna perche' "di solito e' l'uscita" e' il modo in cui un'entrata
    finisce registrata come spesa senza che niente se ne accorga.
    """
    basse = [c.strip().lower() for c in celle]

    def trova(*chiavi, escludi=()):
        for i, c in enumerate(basse):
            if any(k in c for k in chiavi) and not any(e in c for e in escludi):
                return i
        return None

    i_data = next((i for i, c in enumerate(basse)
                   if c.startswith(("data", "date"))), None)
    i_desc = trova("descri")
    if i_data is None or i_desc is None:
        return None
    # Le colonne con il SEGNO: «Denaro in entrata/uscita» (una colonna
    # sola, «-5,50€» o «100,00€») o «Importo». Sui conti in valuta sono
    # due con lo stesso nome, la valuta del conto e il controvalore in
    # euro: si tengono tutte e la riga sceglie quella in euro.
    firmati = [i for i, c in enumerate(basse)
               if ("entrat" in c and "uscit" in c)
               or (("importo" in c or "amount" in c)
                   and not any(e in c for e in ("saldo", "balance")))]
    uscita = trova("uscit", "money out", "addebit", "paid out")
    entrata = trova("entrat", "money in", "accredit", "paid in")
    if uscita in firmati or entrata in firmati:
        uscita = entrata = None
    return {
        "data": i_data,
        "desc": i_desc,
        "categoria": trova("categoria", "category", "tipo", "type"),
        "uscita": uscita,
        "entrata": entrata,
        "firmati": firmati,
        # Il deposito elenca solo gli interessi, con «Net interest».
        "interessi": trova("net interest", "interessi netti"),
        "saldo": trova("saldo", "balance"),
    }


def _chiave_movimento(m: dict, n: int) -> str:
    """
    L'impronta di un movimento, per non importarlo due volte.

    Due estratti che si sovrappongono (luglio-agosto, poi agosto-
    settembre) contengono le stesse righe di agosto. L'estratto non ha un
    id per riga, quindi l'impronta e' fatta di quello che la riga dice —
    conto, data, direzione, importo, descrizione — piu' `n`, il numero
    d'ordine fra le righe **identiche** dello stesso file: due caffe' da
    1,20 lo stesso giorno sono due movimenti, e senza `n` il secondo
    verrebbe scartato come doppione del primo.
    """
    import hashlib
    base = "|".join(_impronta_movimento(m) + (str(n),))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:24]


def _impronta_movimento(m: dict) -> tuple:
    """
    Quello che identifica un movimento **qualunque sia il file** da cui
    arriva: parte di Revolut (liquidita' o risparmi), data, direzione,
    importo, descrizione. Non il nome del conto — il consolidato dice
    «Emergenze», l'export dei movimenti dice solo «Risparmi» —, cosi'
    importare i due formati dello stesso periodo non raddoppia niente.
    """
    # In valuta l'importo in euro dipende dal cambio, e i due formati ne
    # usano due diversi (il consolidato quello del giorno, l'export quello
    # ricavato dalle conversioni): conta l'importo nella valuta del conto,
    # che e' lo stesso in entrambi (-428 ¥ resta -428 ¥).
    if m.get("valuta", "EUR") != "EUR" and m.get("importo_valuta") is not None:
        importo = f'{m["valuta"]} {m["importo_valuta"]:.2f}'
    else:
        importo = f'{m["importo"]:.2f}'
    return (m["sezione"], m["data"], m["tipo"], importo,
            _descrizione_canonica(m["descrizione"]))


def _descrizione_canonica(desc: str) -> str:
    """
    La descrizione ridotta a quello che non cambia fra i due formati:
    minuscole, spazi singoli, senza la data ripetuta negli interessi
    («… in data 20 apr 2026» nel consolidato, «… in data Apr 20, 2026»
    nell'export dei movimenti).
    """
    d = re.sub(r"\s+in data .*$", "", str(desc or ""), flags=re.I)
    return re.sub(r"\s+", " ", d).strip().lower()


def parse_estratto(file_bytes: bytes, nome_file: str = "") -> dict:
    """
    Legge l'estratto conto consolidato di Revolut.

    Ritorna i saldi di chiusura, divisi fra liquidità (conti correnti) e
    risparmi (conti deposito), più l'elenco dei conti trovati così chi
    guarda può controllare che il totale sia la somma di quello che si
    aspetta. Non scrive niente.

    Ritorna anche **i movimenti**, dalle sezioni "Estratti conto": ogni
    riga con data, direzione e importo, nella stessa forma dei movimenti
    degli altri due conti (importo sempre positivo, la direzione la dà
    `tipo`). E per ogni conto il controllo che li rende affidabili:
    saldo di apertura + entrate − uscite deve dare il saldo di chiusura
    che la banca dichiara. Se torna al centesimo, nel file non manca
    nessuna riga; se non torna, lo si dice prima di salvare.

    Struttura del file: sezioni "<qualcosa> Riepiloghi" con dentro un
    blocco per conto ("Conto personale (EUR)", "Deposito senza vincoli
    (EUR)", …), ognuno con le righe "Saldo di apertura" e "Saldo di
    chiusura"; poi le sezioni "Estratti conto", con lo stesso blocco per
    conto seguito dalla tabella dei movimenti.
    """
    righe = _righe_csv(file_bytes)
    if not righe:
        raise ValueError("Il file è vuoto.")
    intestazione = [c.strip().lower() for c in righe[0]]
    if "prodotto" in intestazione and "data di completamento" in intestazione:
        return parse_movimenti_revolut(righe, nome_file)

    modo = None             # 'saldi' | 'movimenti' | None
    sezione = None          # 'conto' | 'risparmi' | 'investimenti' | None
    conto_corrente = None   # (nome, valuta) del blocco in corso
    colonne = None          # intestazione della tabella movimenti in corso
    dettaglio: list[dict] = []
    aperture: dict[tuple, float] = {}
    movimenti: list[dict] = []
    viste: dict[tuple, int] = {}
    sezione_blocco = None
    blocchi_interessi: set = set()
    investimenti_trovati = False
    avvisi: list[str] = []
    in_valuta = 0
    illeggibili = 0

    for r in righe:
        celle = [c.strip() for c in r]
        piene = [c for c in celle if c]
        if not piene:
            continue
        testa = piene[0]

        # Cambio di macro-sezione: i riepiloghi danno i saldi, gli
        # estratti conto ("Transaction Statements") i movimenti.
        # Il file vero intitola le sezioni «<qualcosa> Riepiloghi»; si
        # accetta la parola anche in testa («Riepiloghi dei conti…»), che e'
        # come la scrive l'estratto in inglese («Account summaries») una
        # volta tradotto. Mai dentro il nome di un conto: quello finisce
        # sempre con la valuta fra parentesi.
        basso_testa = testa.lower()
        titolo = len(piene) == 1 and not re.search(r"\([A-Z]{3}\)\s*$", testa)
        # Solo il plurale: «Riepilogo delle transazioni» e «Interest and
        # Tax Summary» stanno DENTRO un conto, e trattarli come titoli di
        # sezione azzerava il conto in lettura — zero movimenti letti.
        if titolo and re.search(r"(^|\s)(riepiloghi|summaries)(\s|$)", basso_testa):
            modo = "saldi"
            sezione = _sezione_da_titolo(testa)
            if sezione == "investimenti":
                investimenti_trovati = True
            conto_corrente = colonne = None
            continue
        if titolo and ("estratti conto" in basso_testa
                       or "statements" in basso_testa):
            modo = "movimenti"
            sezione = _sezione_da_titolo(testa)
            if sezione == "investimenti":
                investimenti_trovati = True
            conto_corrente = colonne = None
            continue

        if sezione in (None, "investimenti"):
            continue

        # Nome del conto: unica cella piena, nella forma "Qualcosa (EUR)".
        # I salvadanai («Emergenze», «Fondo casa»…) stanno fra i conti
        # correnti dell'estratto, ma sono risparmi: la sezione la decide
        # il nome, non il titolo sotto cui compaiono.
        if len(piene) == 1:
            m = re.fullmatch(r"(.+?)\s*\(([A-Z]{3})\)", testa)
            if m:
                nome_conto = re.sub(r"\s+", " ", m.group(1)).strip()
                # «Conto personale» c'e' in euro, in yen, in sterline egiziane:
                # stesso nome, conti diversi. Fuori dall'euro il nome porta la
                # valuta, o i movimenti in yen finirebbero nella quadratura
                # del conto in euro.
                if m.group(2) != "EUR":
                    nome_conto = f"{nome_conto} ({m.group(2)})"
                conto_corrente = (nome_conto, m.group(2))
                colonne = None
                sezione_blocco = ("risparmi" if _chiave_salvadanaio(conto_corrente[0])
                                  else sezione)
            continue

        if modo == "saldi":
            basso = testa.lower()
            if not conto_corrente:
                continue
            # Su un conto in valuta la riga porta prima l'importo nella
            # valuta del conto e poi il controvalore in euro: l'ultimo
            # numero della riga e' sempre quello in euro.
            importi = [v for v in (_importo(c) for c in piene[1:]) if v is not None]
            if not importi:
                continue
            if basso.startswith(("saldo di apertura", "opening balance")):
                aperture[(sezione_blocco, conto_corrente[0])] = round(importi[-1], 2)
            elif basso.startswith(("saldo di chiusura", "closing balance")):
                dettaglio.append({
                    "sezione": sezione_blocco,
                    "nome": conto_corrente[0],
                    "valuta": conto_corrente[1],
                    "saldo": round(importi[-1], 2),
                })
            continue

        if modo != "movimenti" or not conto_corrente:
            continue

        intest = _intestazione_movimenti(celle)
        if intest:
            colonne = intest
            continue
        if not colonne:
            continue

        def cella(i):
            return celle[i] if i is not None and i < len(celle) else ""

        quando = _data(cella(colonne["data"]))
        if not quando:
            continue            # righe di servizio: totali, note, ripetizioni
        in_euro = conto_corrente[1] == "EUR"
        uscita = entrata = in_originale = None
        if colonne["firmati"]:
            # Sui conti in valuta c'e' anche il controvalore in euro: si
            # prende quello. Un movimento in yen non si somma agli euro, e
            # inventare un cambio darebbe un saldo sbagliato con l'aria di
            # giusto; il controvalore e' quello che la banca ha applicato.
            celle_imp = [cella(i) for i in colonne["firmati"]]
            scelta = next((c for c in celle_imp if "€" in c or "EUR" in c), None)
            if scelta is None and in_euro:
                scelta = celle_imp[0]
            firmato = _importo(scelta) if scelta is not None else None
            originale = next((c for c in celle_imp if c.strip() and "€" not in c
                              and "EUR" not in c), None) if not in_euro else None
            in_originale = _importo(originale) if originale is not None else None
            if firmato is not None:
                (entrata, uscita) = (firmato, None) if firmato >= 0 else (None, -firmato)
            elif not in_euro:
                in_valuta += 1
                continue
        elif colonne["interessi"] is not None:
            entrata = _importo(cella(colonne["interessi"]))
            blocchi_interessi.add((sezione_blocco, conto_corrente[0]))
        else:
            if not in_euro:
                in_valuta += 1
                continue
            uscita = _importo(cella(colonne["uscita"]))
            entrata = _importo(cella(colonne["entrata"]))
        if uscita:
            tipo, importo = "uscita", abs(uscita)
        elif entrata:
            tipo, importo = "entrata", abs(entrata)
        elif uscita == 0 or entrata == 0:
            continue            # movimento da zero (un interesse di 0,00)
        else:
            illeggibili += 1
            continue

        mov = {
            "sezione": sezione_blocco,
            "conto": conto_corrente[0],
            "valuta": conto_corrente[1],
            "categoria_banca": cella(colonne["categoria"]).strip()[:40]
                               if colonne["categoria"] is not None
                               and colonne["categoria"] not in colonne["firmati"] else "",
            "data": quando.isoformat(),
            "tipo": tipo,
            "importo": round(importo, 2),
            "descrizione": re.sub(r"\s+", " ", cella(colonne["desc"])).strip()[:200],
        }
        if in_originale is not None:
            mov["importo_valuta"] = round(abs(in_originale), 2)
        impronta = _impronta_movimento(mov)
        n = viste.get(impronta, 0)
        viste[impronta] = n + 1
        mov["chiave"] = _chiave_movimento(mov, n)
        movimenti.append(mov)

    if not dettaglio:
        raise ValueError(
            "Non ho trovato nessun saldo di chiusura. È l'estratto conto "
            "consolidato di Revolut (Excel o CSV)?")

    conto = round(sum(d["saldo"] for d in dettaglio if d["sezione"] == "conto"), 2)
    risparmi = round(sum(d["saldo"] for d in dettaglio if d["sezione"] == "risparmi"), 2)

    # Il controllo che rende i movimenti affidabili: per ogni conto in
    # euro, apertura + entrate − uscite deve dare la chiusura dichiarata.
    # E' la stessa verifica che sul conto WeBank ha trovato 829,78 € di
    # scarto dopo diciotto mesi: qui si fa prima di salvare, riga per riga
    # di conto, e non dopo.
    quadrature = []
    for d in dettaglio:
        chiave = (d["sezione"], d["nome"])
        propri = [m for m in movimenti
                  if (m["sezione"], m["conto"]) == chiave]
        if not propri and chiave not in aperture:
            continue
        entrate = round(sum(m["importo"] for m in propri if m["tipo"] == "entrata"), 2)
        uscite = round(sum(m["importo"] for m in propri if m["tipo"] == "uscita"), 2)
        apertura = aperture.get(chiave)
        nota = None
        if chiave in blocchi_interessi:
            # Il deposito, nell'estratto, elenca SOLO gli interessi: i
            # versamenti e i prelievi compaiono dall'altra parte (sul conto
            # corrente, «A EUR Casa», «Da EUR Vacanze»). La quadratura non
            # si puo' fare, e dire «non torna» sarebbe un falso allarme.
            apertura, nota = None, "l'estratto elenca solo gli interessi del deposito"
        calcolato = (round(apertura + entrate - uscite, 2)
                     if apertura is not None else None)
        scarto = (round(d["saldo"] - calcolato, 2)
                  if calcolato is not None else None)
        # Sui conti in valuta i movimenti sono al controvalore del giorno,
        # la chiusura al cambio di fine periodo: qualche euro di differenza
        # e' il cambio, non una riga che manca.
        tolleranza = 0.01 if d["valuta"] == "EUR" else 5.0
        if d["valuta"] != "EUR" and nota is None:
            nota = f'conto in {d["valuta"]}: movimenti al controvalore in euro'
        quadrature.append({
            "sezione": d["sezione"], "nome": d["nome"], "valuta": d["valuta"],
            "apertura": apertura, "entrate": entrate, "uscite": uscite,
            "movimenti": len(propri), "chiusura": d["saldo"],
            "calcolato": calcolato, "scarto": scarto, "nota": nota,
            "ok": scarto is not None and abs(scarto) < tolleranza,
        })

    if investimenti_trovati:
        avvisi.append(
            "L'estratto ha la sezione investimenti ma non ne dichiara il valore: "
            "riporta solo dividendi, vendite e PnL del periodo, nessuna "
            "valorizzazione delle posizioni. Il valore del portafoglio va scritto "
            "a mano qui sotto.")
    if risparmi > 0 and not any(_chiave_salvadanaio(d["nome"])
                                for d in dettaglio if d["sezione"] == "risparmi"):
        avvisi.append(
            "I salvadanai stanno dentro un unico conto deposito e l'estratto ne "
            f"dà solo il totale (€ {eur(risparmi)}). La ripartizione fra Emergenze, "
            "Fondo casa, Vacanze, Regali e Altro va scritta a mano.")
    if in_valuta:
        avvisi.append(
            f"{in_valuta} movimenti stanno su conti in valuta diversa dall'euro e "
            "non sono stati letti: la riga non porta il controvalore, e sommarli "
            "agli euro darebbe un saldo sbagliato.")
    if illeggibili:
        avvisi.append(
            f"{illeggibili} righe con una data ma senza un importo leggibile "
            "sono state saltate.")
    storte = [q for q in quadrature if q["scarto"] is not None and not q["ok"]]
    in_valuta_letti = sorted({m["valuta"] for m in movimenti if m.get("valuta") != "EUR"})
    if in_valuta_letti:
        avvisi.append(
            "Movimenti su conti in " + ", ".join(in_valuta_letti) + ": letti al "
            "controvalore in euro che la banca ha applicato quel giorno.")
    if storte:
        avvisi.append(
            "I movimenti letti non tornano con il saldo dichiarato su "
            + ", ".join(f'«{q["nome"]}» (scarto € {eur(q["scarto"])})' for q in storte)
            + ". Manca qualche riga, o il file ha un formato che il lettore non "
              "conosce: meglio non salvare i movimenti finché non torna.")

    return {
        "data": _data_estratto(righe, nome_file).isoformat(),
        "conto": conto,
        "risparmi": risparmi,
        "dettaglio": dettaglio,
        "movimenti": movimenti,
        "quadrature": quadrature,
        "investimenti_nel_file": investimenti_trovati,
        "avvisi": avvisi,
    }


def _salvadanaio_da_descrizione(desc: str) -> str | None:
    """
    La chiave del salvadanaio nominato in una descrizione del deposito:
    «A EUR Casa», «Da EUR Vacanze», «Interessi netti pagati nel conto
    "Emergenze"…». None se non ne nomina nessuno.
    """
    m = (re.search(r'nel conto\s+"([^"]+)"', desc or "", re.I)
         or re.search(r"^\s*(?:a|da)\s+eur\s+(.+?)\s*$", desc or "", re.I)
         or re.search(r"accredita\s+eur\s+(.+?)\s+da\s+eur", desc or "", re.I))
    return _chiave_salvadanaio(m.group(1)) if m else None


def parse_movimenti_revolut(righe: list[list[str]], nome_file: str = "") -> dict:
    """
    Legge l'export dei movimenti di Revolut («account-statement», una riga
    per operazione: Tipo, Prodotto, Data di inizio, Data di completamento,
    Descrizione, Importo, Costo, Valuta, State, Saldo) e restituisce la
    stessa forma di `parse_estratto`.

    E' il formato PIU' COMPLETO: il consolidato del deposito elenca solo
    gli interessi, questo anche i versamenti e i prelievi («A EUR Casa»,
    «Da EUR Vacanze»). Con quelli il saldo del deposito torna al centesimo
    e i salvadanai si ricostruiscono dai movimenti, senza scriverli a mano.

    Tre cose che il formato non dice e che qui si ricavano:
      * l'importo e' lordo: il netto e' Importo − Costo (la ritenuta sugli
        interessi, la commissione sul versamento al conto investimenti);
      * i conti in valuta non hanno il controvalore in euro: si usa il
        cambio che Revolut ha applicato davvero, ricavato dalle conversioni
        dello stesso file («Conversione in JPY»: −161,80 € e +26.335 ¥
        con lo stesso orario);
      * le operazioni annullate non sono movimenti: si saltano.
    """
    import csv as _csv
    testa = [c.strip().lower() for c in righe[0]]
    col = {n: testa.index(n) for n in ("tipo", "prodotto", "data di inizio",
                                        "data di completamento", "descrizione",
                                        "importo", "costo", "valuta", "state", "saldo")
           if n in testa}
    if "importo" not in col or "descrizione" not in col:
        raise ValueError("Export dei movimenti Revolut senza le colonne attese.")

    def val(r, n):
        i = col.get(n)
        return r[i].strip() if i is not None and i < len(r) else ""

    def num(t):
        try:
            return float(t.replace(",", ".")) if t else 0.0
        except ValueError:
            return None

    grezze = []
    annullate = 0
    for r in righe[1:]:
        if not any(c.strip() for c in r):
            continue
        stato = val(r, "state").upper()
        if stato and stato != "COMPLETATO" and stato != "COMPLETED":
            annullate += 1
            continue
        quando = (val(r, "data di completamento") or val(r, "data di inizio"))[:10]
        imp, costo = num(val(r, "importo")), num(val(r, "costo"))
        if imp is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", quando):
            continue
        grezze.append({"r": r, "data": quando, "inizio": val(r, "data di inizio"),
                       "netto": round(imp - (costo or 0.0), 2),
                       "prodotto": val(r, "prodotto"), "valuta": val(r, "valuta") or "EUR",
                       "saldo": num(val(r, "saldo")), "tipo_banca": val(r, "tipo"),
                       "descrizione": re.sub(r"\s+", " ", val(r, "descrizione")).strip()})

    # Il cambio di ogni valuta dalle conversioni: stessa ora di inizio, una
    # riga in euro e una nella valuta, di segno opposto.
    per_ora: dict = {}
    for g in grezze:
        if g["tipo_banca"].lower().startswith("cambia"):
            per_ora.setdefault(g["inizio"], []).append(g)
    euro_per: dict = {}
    for gruppo in per_ora.values():
        eur = [g for g in gruppo if g["valuta"] == "EUR"]
        altre = [g for g in gruppo if g["valuta"] != "EUR"]
        for a in altre:
            for e in eur:
                if (a["netto"] > 0) != (e["netto"] > 0) and a["netto"] and e["netto"]:
                    t = euro_per.setdefault(a["valuta"], [0.0, 0.0])
                    t[0] += abs(e["netto"])
                    t[1] += abs(a["netto"])
                    break
    cambio = {v: e / f for v, (e, f) in euro_per.items() if f}

    movimenti, viste, avvisi = [], {}, []
    senza_cambio = 0
    sezioni = {"attuale": "conto", "current": "conto", "risparmi": "risparmi",
               "savings": "risparmi", "deposito": "risparmi", "deposit": "risparmi"}
    for g in grezze:
        prodotto = g["prodotto"].lower()
        sezione = sezioni.get(prodotto, "conto")
        netto = g["netto"]
        if g["valuta"] != "EUR":
            if g["valuta"] not in cambio:
                senza_cambio += 1
                continue
            netto = round(netto * cambio[g["valuta"]], 2)
        if not netto:
            continue
        nome = {"attuale": "Conto personale", "deposito": "Deposito senza vincoli",
                "risparmi": "Salvadanai"}.get(prodotto, g["prodotto"] or "Revolut")
        if g["valuta"] != "EUR":
            nome = f'{nome} ({g["valuta"]})'
        mov = {
            "sezione": sezione, "conto": nome, "valuta": g["valuta"],
            "categoria_banca": g["tipo_banca"][:40],
            "data": g["data"], "tipo": "entrata" if netto > 0 else "uscita",
            "importo": abs(netto), "descrizione": g["descrizione"][:200],
            "_prodotto": (g["prodotto"], g["valuta"]),
        }
        if g["valuta"] != "EUR":
            mov["importo_valuta"] = round(abs(g["netto"]), 2)
        impronta = _impronta_movimento(mov)
        n = viste.get(impronta, 0)
        viste[impronta] = n + 1
        mov["chiave"] = _chiave_movimento(mov, n)
        movimenti.append(mov)

    # La quadratura per prodotto e valuta, con il saldo progressivo che il
    # file porta su ogni riga: saldo prima della prima riga + movimenti =
    # saldo dopo l'ultima. I conti in valuta si controllano nella valuta.
    quadrature, chiusure = [], {}
    per_conto: dict = {}
    for g in grezze:
        per_conto.setdefault((g["prodotto"], g["valuta"]), []).append(g)
    for (prodotto, valuta), gg in per_conto.items():
        gg = [g for g in gg if g["saldo"] is not None]
        if not gg:
            continue
        apertura = round(gg[0]["saldo"] - gg[0]["netto"], 2)
        calcolato = round(apertura + sum(g["netto"] for g in gg), 2)
        chiusura = round(gg[-1]["saldo"], 2)
        chiusure[(prodotto, valuta)] = chiusura
        nome = {"Attuale": "Conto personale", "Deposito": "Deposito senza vincoli",
                "Risparmi": "Salvadanai"}.get(prodotto, prodotto)
        quadrature.append({
            "sezione": sezioni.get(prodotto.lower(), "conto"),
            "nome": nome if valuta == "EUR" else f"{nome} ({valuta})", "valuta": valuta,
            "apertura": apertura, "entrate": round(sum(g["netto"] for g in gg if g["netto"] > 0), 2),
            "uscite": round(-sum(g["netto"] for g in gg if g["netto"] < 0), 2),
            "movimenti": len(gg), "chiusura": chiusura, "calcolato": calcolato,
            "scarto": round(chiusura - calcolato, 2),
            "ok": abs(chiusura - calcolato) < 0.01,
            "nota": None if valuta == "EUR" else f"controllata in {valuta}",
        })

    conto = round(sum(v for (p, val_), v in chiusure.items()
                      if val_ == "EUR" and sezioni.get(p.lower(), "conto") == "conto"), 2)
    risparmi = round(sum(v for (p, val_), v in chiusure.items()
                         if val_ == "EUR" and sezioni.get(p.lower()) == "risparmi"), 2)

    # I salvadanai, dai movimenti del deposito: ogni versamento e ogni
    # interesse nomina il suo («A EUR Casa», «… nel conto "Emergenze"»).
    salvadanai: dict = {}
    for g in grezze:
        if g["prodotto"].lower() not in ("deposito", "deposit"):
            continue
        k = _salvadanaio_da_descrizione(g["descrizione"])
        if k:
            salvadanai[k] = round(salvadanai.get(k, 0.0) + g["netto"], 2)
    ripartiti = round(sum(salvadanai.values()), 2)
    deposito = chiusure.get(("Deposito", "EUR"))
    if salvadanai and deposito is not None and abs(ripartiti - deposito) >= 0.01:
        avvisi.append(f"I salvadanai ricostruiti dai movimenti sommano € {eur(ripartiti)} "
                      f"su € {eur(deposito)} del deposito: il resto non nomina un salvadanaio.")

    if cambio:
        avvisi.append("Movimenti in " + ", ".join(sorted(cambio)) + ": convertiti in euro al "
                      "cambio che Revolut ha applicato nelle conversioni dello stesso file.")
    if senza_cambio:
        avvisi.append(f"{senza_cambio} movimenti in valuta senza una conversione da cui "
                      "ricavare il cambio: non letti.")
    if annullate:
        avvisi.append(f"{annullate} operazioni annullate: saltate.")
    storte = [q for q in quadrature if not q["ok"]]
    if storte:
        avvisi.append("I movimenti non tornano con il saldo progressivo su "
                      + ", ".join(f'«{q["nome"]}» (scarto € {eur(q["scarto"])})' for q in storte)
                      + ": meglio non salvare finché non torna.")
    for m in movimenti:
        m.pop("_prodotto", None)
    quando = _data_estratto([], nome_file) if re.search(r"20\d{2}-?\d{2}-?\d{2}", nome_file or "") \
        else date.fromisoformat(max(m["data"] for m in movimenti)) if movimenti else date.today()
    return {
        "data": quando.isoformat(),
        "conto": conto,
        "risparmi": risparmi,
        "salvadanai": salvadanai,
        "dettaglio": [{"sezione": q["sezione"], "nome": q["nome"], "valuta": q["valuta"],
                       "saldo": q["chiusura"]} for q in quadrature if q["valuta"] == "EUR"],
        "movimenti": movimenti,
        "quadrature": quadrature,
        "investimenti_nel_file": False,
        "formato": "movimenti",
        "avvisi": avvisi,
    }


# ---------------------------------------------------------------------------
# Accesso ai dati
# ---------------------------------------------------------------------------

def saldo_revolut(client, al: str | None = None) -> dict:
    """
    L'ultimo saldo Revolut registrato a quella data (default: oggi).

    E' uno snapshot, non un saldo calcolato dai movimenti: Revolut non ha
    un'API qui dentro, i numeri arrivano dall'estratto. Per questo la
    risposta porta sempre `data` e `giorni`: un saldo di tre mesi fa non
    e' sbagliato, e' vecchio — e chi lo guarda deve poterlo distinguere.
    """
    al = al or date.today().isoformat()
    vuoto = {"al": al, "disponibile": False, "conto": 0.0, "risparmi": 0.0,
             "investimenti": 0.0, "saldo": 0.0, "salvadanai": {},
             "dopo": {"conto": 0.0, "risparmi": 0.0, "n": 0},
             "data": None, "giorni": None}
    try:
        r = (client.table(TABELLA).select("*")
             .lte("data", al).order("data", desc=True).limit(1).execute())
        righe = getattr(r, "data", None) or []
    except Exception:
        return vuoto
    if not righe:
        return vuoto

    s = righe[0]

    def num(chiave):
        try:
            return round(float(s.get(chiave) or 0), 2)
        except (TypeError, ValueError):
            return 0.0

    salvadanai = s.get("salvadanai") or {}
    if isinstance(salvadanai, str):
        try:
            salvadanai = json.loads(salvadanai)
        except ValueError:
            salvadanai = {}
    salvadanai = {k: round(float(v or 0), 2) for k, v in salvadanai.items()
                  if k in SALVADANAI_CHIAVI}

    conto, risparmi, investimenti = num("conto"), num("risparmi"), num("investimenti")
    quando = (s.get("data") or "")[:10]
    giorni = None
    try:
        giorni = (date.fromisoformat(al) - date.fromisoformat(quando)).days
    except ValueError:
        pass

    # Fotografia + movimenti registrati dopo: la stessa forma del saldo
    # del conto personale (apertura + movimenti), con la fotografia al
    # posto dell'apertura. `conto` e `risparmi` restano quelli della
    # fotografia, perche' chi li confronta con altro (i salvadanai, il
    # risparmio dichiarato) li confronta alla data della fotografia; il
    # movimento successivo sta in `dopo`, e il `saldo` li somma.
    from .revolut_movimenti import dopo_la_fotografia
    dopo = dopo_la_fotografia(client, quando, al) or {"conto": 0.0,
                                                      "risparmi": 0.0, "n": 0}

    return {
        "al": al,
        "disponibile": True,
        "data": quando,
        "giorni": giorni,
        "conto": conto,
        "risparmi": risparmi,
        "investimenti": investimenti,
        "dopo": dopo,
        "saldo": round(conto + risparmi + investimenti
                       + dopo["conto"] + dopo["risparmi"], 2),
        "salvadanai": salvadanai,
        "fonte": s.get("fonte") or "estratto",
        "note": s.get("note"),
    }


def storico(client, limite: int = 12) -> list[dict]:
    """Gli snapshot registrati, dal più recente."""
    try:
        r = (client.table(TABELLA).select("*")
             .order("data", desc=True).limit(limite).execute())
        return getattr(r, "data", None) or []
    except Exception:
        return []


def salva(client, s: dict) -> dict:
    """
    Registra uno snapshot. La chiave è la data: reimportare lo stesso
    estratto aggiorna la riga invece di aggiungerne una gemella.
    """
    quando = (s.get("data") or date.today().isoformat())[:10]
    try:
        date.fromisoformat(quando)
    except ValueError:
        return {"error": "data non valida"}

    def num(chiave):
        try:
            return round(abs(float(s.get(chiave) or 0)), 2)
        except (TypeError, ValueError):
            return 0.0

    salvadanai = {}
    for chiave, valore in (s.get("salvadanai") or {}).items():
        if chiave not in SALVADANAI_CHIAVI:
            continue
        try:
            salvadanai[chiave] = round(abs(float(valore or 0)), 2)
        except (TypeError, ValueError):
            continue

    riga = {
        "data": quando,
        "conto": num("conto"),
        "risparmi": num("risparmi"),
        "investimenti": num("investimenti"),
        "salvadanai": salvadanai,
        "fonte": "estratto" if s.get("fonte") == "estratto" else "manuale",
        "note": (s.get("note") or None),
    }
    try:
        r = client.table(TABELLA).upsert(riga, on_conflict="data").execute()
        return {"ok": True, "riga": (getattr(r, "data", None) or [riga])[0]}
    except Exception as e:
        msg = str(e)
        if "b2f_revolut" in msg and ("does not exist" in msg or "relation" in msg):
            return {"error": ("Manca la tabella b2f_revolut: esegui la migrazione "
                              "§8.10 documentata nel README.")}
        return {"error": msg[:200]}


def coerenza(client, rev: dict) -> dict | None:
    """
    Il confronto che chiude il cerchio: quanto hai dichiarato di aver
    risparmiato, contro quanto c'è davvero fra salvadanai e investimenti.

    Sono due misure indipendenti della stessa cosa — la prima la scrivi
    tu periodo per periodo su `risparmi_periodo`, la seconda arriva
    dall'estratto della banca (più il valore di mercato degli
    investimenti, scritto a mano). Il "reale" include gli investimenti e
    non solo i salvadanai: una parte del risparmio dichiarato può finire
    investita invece di restare liquida nel deposito, e quei soldi sono
    comunque usciti dal conto personale — escluderli genererebbe uno
    scarto negativo strutturale che non è un errore di registrazione, e
    che finirebbe per far ignorare l'avviso proprio quando servirebbe
    davvero. Il rovescio della medaglia, spiegato nel messaggio: una
    volta dentro, il valore degli investimenti si muove col mercato, e
    uno scarto può quindi comparire anche per una plus/minusvalenza, non
    solo per un periodo dimenticato.
    """
    if not rev.get("disponibile"):
        return None
    dichiarato = D.risparmio_totale(client, rev.get("data"))
    risparmi = float(rev.get("risparmi") or 0)
    investimenti = float(rev.get("investimenti") or 0)
    reale = round(risparmi + investimenti, 2)
    scarto = round(reale - dichiarato, 2)
    return {
        "dichiarato": dichiarato,
        "reale": reale,
        "risparmi": risparmi,
        "investimenti": investimenti,
        "scarto": scarto,
        # Sotto i 50 € non vale la pena allarmare: interessi maturati e
        # arrotondamenti bastano a spiegarli.
        "allineato": abs(scarto) <= 50,
    }


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

def _riquadro_coerenza(c: dict | None) -> str:
    """Il confronto fra risparmio dichiarato e reale (salvadanai + investimenti)."""
    if not c:
        return ""
    di_cui_inv = (f' (di cui € {eur(c["investimenti"])} investiti)'
                  if c.get("investimenti") else "")
    if c["allineato"]:
        cls, titolo = "ok", "I conti tornano"
        corpo = (f'Hai dichiarato di aver messo da parte € {eur(c["dichiarato"])} '
                 f'e fra salvadanai e investimenti ce ne sono € {eur(c["reale"])}'
                 f'{di_cui_inv}. Differenza € {eur(abs(c["scarto"]))}: interessi, '
                 f'arrotondamenti e oscillazioni di mercato.')
    else:
        cls = "warn"
        if c["scarto"] > 0:
            titolo = "Su Revolut c'è più di quanto risulti risparmiato"
            corpo = (f'Fra salvadanai e investimenti ci sono € {eur(c["reale"])}'
                     f'{di_cui_inv}, ma la pagina Risparmi ne ha registrati solo '
                     f'€ {eur(c["dichiarato"])}: mancano € {eur(c["scarto"])}. Può '
                     f'essere un periodo non registrato, oppure una plusvalenza '
                     f'sugli investimenti — quella non passa mai dal conto '
                     f'personale, quindi non risulta "dichiarata".')
        else:
            titolo = "Risulta risparmiato più di quanto ci sia"
            corpo = (f'Hai registrato € {eur(c["dichiarato"])} di risparmio ma fra '
                     f'salvadanai e investimenti ce ne sono € {eur(c["reale"])}'
                     f'{di_cui_inv}: € {eur(abs(c["scarto"]))} in meno. Può essere '
                     f'per aver ripreso soldi dai salvadanai, un periodo registrato '
                     f'con un importo più alto del reale, o una minusvalenza sugli '
                     f'investimenti.')
    return f'''
    <div class="notice {cls} mb-3">
      <strong>{titolo}.</strong><br>{corpo}
    </div>'''


def _card_movimenti(movimenti: list[dict] | None) -> str:
    """Gli ultimi movimenti, con i totali e il collegamento all'elenco."""
    if movimenti is None:
        return f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">Movimenti</div></div>
          {RM.avviso_migrazione()}
        </div>'''
    if not movimenti:
        return '''
        <div class="card">
          <div class="card-head"><div class="eyebrow">Movimenti</div>
            <span class="chip">nessuno</span></div>
          <p class="small muted">Nessun movimento registrato. Caricando l'estratto
            consolidato qui a fianco, oltre ai saldi leggo anche i movimenti: entrate
            e uscite con la loro categoria, come sugli altri due conti.</p>
          <a class="btn ghost block mt-3" href="/conti/revolut/movimenti/nuovo">Registra un movimento a mano</a>
        </div>'''
    t = RM.totali(movimenti)
    da_cat = (f'<a class="chip warn" href="/conti/revolut/movimenti?anno=0&amp;categoria=-">'
              f'{t["da_categorizzare"]} da categorizzare</a>'
              if t["da_categorizzare"] else "")
    ultimi = "".join(RM.riga_html(m) for m in reversed(movimenti[-8:]))
    return f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">Movimenti
          {info("Le entrate e le uscite di Revolut, lette dall&apos;estratto, con "
                "le stesse categorie del conto personale. Gli spostamenti fra "
                "liquidit&agrave; e deposito sono &laquo;Giroconto Revolut&raquo; e "
                "restano fuori da entrate e uscite: sono lo stesso euro visto due volte.")}</div>
        <span class="chip">{t["n"]}</span>
      </div>
      <div class="rows detail">
        <div class="row"><span class="t">Entrate
          <span class="sub">di cui € {eur(t["dal_webank"])} netti arrivati da WeBank
            · € {eur(t["interessi"])} di interessi</span></span>
          <span class="v tnum pos">€ {eur(t["entrate"])}</span></div>
        <div class="row"><span class="t">Uscite</span>
          <span class="v tnum neg">€ {eur(t["uscite"])}</span></div>
      </div>
      {f'<div class="mt-2">{da_cat}</div>' if da_cat else ""}
      <div class="list mt-3">{ultimi}</div>
      <a class="btn ghost block mt-3" href="/conti/revolut/movimenti">Tutti i movimenti ›</a>
    </div>'''


@spese_bp.get("/conti/revolut")
def revolut_pagina():
    breadcrumb = [("Conti", "/conti"), ("Revolut", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb)

    # Le letture indipendenti partono insieme (vedi app._in_parallelo).
    from shared.parallelo import in_parallelo as _in_parallelo
    rev, passato, movimenti = _in_parallelo(lambda: saldo_revolut(client),
                                            lambda: storico(client),
                                            lambda: RM.tutti(client))
    passato = passato or []
    rev = rev or saldo_revolut(client)

    if not rev["disponibile"]:
        corpo = f'''<div class="empty">{icon("wallet")}
          <div class="t">Nessun saldo registrato</div>
          <div class="s">Carica l'estratto conto consolidato che scarichi da
            Revolut (Menu → Estratti conto → Consolidato, formato Excel) e
            conferma i numeri: da lì in poi Revolut compare accanto agli
            altri due conti.</div></div>'''
        kpi = ""
    else:
        kpi = ""
        corpo = ""

    # --- KPI, come sugli altri conti ------------------------------------
    dopo = rev.get("dopo") or {}
    if dopo.get("n"):
        hint_totale = (f'fotografia del {data_it(rev["data"])} + {dopo["n"]} '
                       f'moviment{"o" if dopo["n"] == 1 else "i"} registrati dopo')
    else:
        hint_totale = f'fotografia del {data_it(rev["data"])}, non un saldo dal vivo'
    if rev["disponibile"]:
        giorni = rev.get("giorni") or 0
        eta = (f'<span class="chip warn">fermo da {giorni} giorni</span>'
               if giorni > 45 else
               f'<span class="chip">al {data_it(rev["data"])}</span>')
        kpi = f'''
        <div class="grid kpi lead mb-3">
          <div class="card"><div class="stat">
            <div class="val tnum accent">€ {eur(rev["saldo"])}</div>
            <div class="lbl">Totale su Revolut</div>
            <div class="hint">{hint_totale}
              {info("Gli altri due conti si calcolano dai movimenti, quindi "
                    "valgono <strong>a oggi</strong>. Questo no: &egrave; il saldo "
                    "che l&apos;estratto dichiarava il giorno in cui l&apos;hai "
                    "caricato. Fra quel giorno e adesso il conto si &egrave; "
                    "mosso, e uno scarto contro l&apos;app di Revolut non &egrave; "
                    "un errore dell&apos;app.")}</div>
          </div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum">€ {eur(rev["conto"] + float(dopo.get("conto") or 0))}</div>
            <div class="lbl">Liquidità</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum pos">€ {eur(rev["risparmi"] + float(dopo.get("risparmi") or 0))}</div>
            <div class="lbl">Risparmi</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum">€ {eur(rev["investimenti"])}</div>
            <div class="lbl">Investimenti</div>
            <div class="hint">scritto a mano
              {info("L&apos;estratto consolidato d&agrave; i redditi del periodo "
                    "(dividendi, vendite, PnL) ma <strong>nessuna "
                    "valorizzazione delle posizioni</strong>: questo numero si "
                    "prende dall&apos;app di Revolut e si scrive qui.")}</div>
          </div></div>
        </div>
        <div class="mb-3">{eta}</div>'''

        # --- La composizione, che deve quadrare -------------------------
        # Stessa disciplina della pagina Risparmi: le parti stanno sotto
        # il totale che le raccoglie, e una riga residua chiude sempre la
        # differenza. Senza, la somma dei secchielli non tornava al
        # totale del deposito e non c'era modo di vedere di quanto.
        reali = rev.get("salvadanai") or {}
        righe_sv = ""
        somma_sv = 0.0
        for chiave, _nome_rev, nome_app, _perc, _col, _alias in SALVADANAI:
            v = float(reali.get(chiave) or 0)
            somma_sv += v
            if not v:
                continue
            righe_sv += f'''
          <div class="row voce">
            <span class="t">{nome_app}</span>
            <span class="v tnum">€ {eur(v)}</span>
          </div>'''
        residuo = round(float(rev["risparmi"]) - somma_sv, 2)
        if abs(residuo) >= 0.01 or not righe_sv:
            righe_sv += f'''
          <div class="row voce">
            <span class="t">Non ripartiti
              <span class="sub">{"nel deposito ma non assegnati a un secchiello"
                if residuo > 0 else "i secchielli sommano più del deposito: "
                "uno dei due numeri è vecchio"}</span></span>
            <span class="v tnum {"" if residuo >= 0 else "neg"}">€ {eur(residuo)}</span>
          </div>'''

        riga_dopo = ""
        if dopo.get("n"):
            netto = round(float(dopo.get("conto") or 0) + float(dopo.get("risparmi") or 0), 2)
            riga_dopo = f'''
            <div class="row">
              <span class="t">Movimenti dopo il {data_it(rev["data"])}
                <span class="sub">{dopo["n"]} registrati dopo la fotografia: il saldo
                  non è più fermo al giorno dell'estratto</span></span>
              <span class="v tnum">{eur_segno(netto)}</span>
            </div>'''
        corpo = f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Com'è composto</div>
            <span class="chip">€ {eur(rev["saldo"], 0)}</span>
          </div>
          <div class="rows detail">
            <div class="row">
              <span class="t">Liquidità
                <span class="sub">il conto corrente Revolut</span></span>
              <span class="v tnum">€ {eur(rev["conto"])}</span>
            </div>
            <div class="row">
              <span class="t">Risparmi
                <span class="sub">il «Deposito senza vincoli», che dal 15 aprile 2026
                  contiene tutti i salvadanai insieme</span></span>
              <span class="v tnum pos">€ {eur(rev["risparmi"])}</span>
            </div>
            {righe_sv}
            <div class="row">
              <span class="t">Investimenti
                <span class="sub">valore del portafoglio, scritto a mano</span></span>
              <span class="v tnum">€ {eur(rev["investimenti"])}</span>
            </div>
            {riga_dopo}
            <div class="row tot">
              <span class="t">Totale su Revolut</span>
              <span class="v tnum">€ {eur(rev["saldo"])}</span>
            </div>
          </div>
        </div>'''

    dati_coer, dati_ponte = _in_parallelo(
        lambda: coerenza(client, rev),
        lambda: RM.ponte(client, movimenti) if movimenti else None)
    coer = _riquadro_coerenza(dati_coer)

    # --- I movimenti ----------------------------------------------------
    blocco_mov = _card_movimenti(movimenti)
    blocco_ponte = RM.card_ponte(dati_ponte) if dati_ponte else ""
    righe_storico = "".join(f'''
      <div class="row">
        <span class="k">{data_it(s.get("data"))}</span>
        <span class="t">{"da estratto" if s.get("fonte") == "estratto" else "scritto a mano"}
          <span class="sub">liquidità € {eur(s.get("conto"))} · risparmi
            € {eur(s.get("risparmi"))} · investimenti € {eur(s.get("investimenti"))}</span></span>
        <span class="v tnum">€ {eur(float(s.get("conto") or 0)
                                     + float(s.get("risparmi") or 0)
                                     + float(s.get("investimenti") or 0))}</span>
      </div>''' for s in passato)
    blocco_storico = (f'''
      <div class="card">
        <div class="card-head">
          <div class="eyebrow">Letture registrate</div>
          <span class="chip">{len(passato)}</span>
        </div>
        <div class="rows detail">{righe_storico}</div>
        <p class="small muted mt-3">Ogni riga è una fotografia del conto a
          quel giorno. La chiave è la data: salvando con una data che c'è
          già, quella lettura viene sostituita.</p>
      </div>''' if righe_storico else "")

    body = f'''
    {kpi}{coer}
    <div class="grid split">
      <div class="stack">
        {corpo}
        {blocco_storico}
      </div>
      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Aggiorna da estratto</div></div>
          <p class="small muted">Carica l'estratto consolidato di Revolut: legge i
            saldi (la nuova fotografia) e tutti i movimenti, con le categorie
            proposte dallo storico. Stessa procedura dell'import WeBank.</p>
          <a class="btn block mt-3" href="/conti/revolut/importa">{icon("download")}Importa l'estratto</a>
        </div>
        {blocco_mov}
        {blocco_ponte}
      </div>
    </div>'''
    return _render(body, breadcrumb)


@spese_bp.get("/conti/revolut/importa")
def revolut_importa():
    """
    L'import dell'estratto consolidato: la stessa pagina degli altri conti
    (carica → revisione comune di shared/importazione.py), piu' la card
    che e' solo di Revolut — la fotografia dei saldi, con la quadratura
    dei movimenti letti e la ripartizione dei salvadanai scritta a mano.
    """
    breadcrumb = [("Conti", "/conti"), ("Revolut", "/conti/revolut"),
                  ("Importa l'estratto", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb)
    from shared import importazione as IM
    from .importa import pagina_upload

    rev = saldo_revolut(client)
    passato = storico(client)
    oggi = date.today().isoformat()
    movimenti_ok = RM.tutti(client) is not None
    date_note = json.dumps([str(x.get("data") or "")[:10] for x in passato])
    correnti = rev.get("salvadanai") or {}
    campi_salvadanai = "".join(f'''
      <div class="field">
        <label>{lbl}</label>
        <input type="number" step="0.01" min="0" inputmode="decimal"
               id="sv_{chiave}" value="{correnti.get(chiave, "")}">
      </div>''' for chiave, _r, lbl, _p, _c, _a in SALVADANAI)

    # La fotografia: si compila da sola alla lettura del file, e si puo'
    # anche scrivere a mano (una lettura dall'app di Revolut, senza file).
    saldi = f'''
    <div class="card mb-3" id="cardSaldi">
      <div class="card-head">
        <div class="eyebrow">2 · la fotografia dei saldi</div>
        <span class="chip" id="chipSaldi">a mano</span>
      </div>
      <div class="rows detail" id="dettaglioImport"></div>
      <div class="rows detail mt-2" id="quadrature"></div>
      <div class="field-group mt-3">
        <div class="field"><label>Data della lettura</label>
          <input type="date" id="f_data" value="{oggi}" onchange="controllaData()"></div>
        <div class="field"><label>Liquidità (€)</label>
          <input type="number" step="0.01" inputmode="decimal" id="f_conto"
                 value="{rev.get("conto") or 0}"></div>
        <div class="field"><label>Risparmi (€)</label>
          <input type="number" step="0.01" inputmode="decimal" id="f_risparmi"
                 value="{rev.get("risparmi") or 0}"></div>
        <div class="field"><label>Investimenti (€)</label>
          <input type="number" step="0.01" inputmode="decimal" id="f_investimenti"
                 value="{rev.get("investimenti") or 0}"></div>
      </div>
      <div class="notice warn mt-2" id="avvisoData" style="display:none"></div>
      <details class="explain mt-3">
        <summary>Come sono divisi i risparmi (facoltativo)</summary>
        <p class="small muted">Dal 15 aprile 2026 i salvadanai vivono dentro un
          unico «Deposito senza vincoli». L'estratto consolidato ne dà solo il
          totale; l'export dei movimenti li ricostruisce e li scrive qui. Servono alla pagina Risparmi per dire, secchiello per
          secchiello, quanto c'è contro quanto dovrebbe esserci.</p>
        <div class="field-group mt-2">{campi_salvadanai}</div>
        <div class="small muted mt-2" id="sommaSalvadanai"></div>
      </details>
      <div class="actions mt-3">
        <button type="button" class="btn" onclick="onSalvaSaldi()">Salva la fotografia</button>
      </div>
    </div>
    <script>
      const SALVADANAI = {json.dumps([[x[0], x[2]] for x in SALVADANAI], ensure_ascii=False)};
      const DATE_NOTE = {date_note};
      let DA_ESTRATTO = false;
      function euroS(v) {{
        return new Intl.NumberFormat('it-IT', {{minimumFractionDigits:2, maximumFractionDigits:2}}).format(Number(v) || 0);
      }}
      function escS(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }}
      function dataIt(iso) {{ if (!iso) return ''; const [y, m, g] = iso.slice(0, 10).split('-'); return g + '/' + m + '/' + y; }}
      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 3000);
      }}
      // Salvare con una data gia' presente SOSTITUISCE quella lettura:
      // `salva()` fa un upsert sulla data.
      function controllaData() {{
        const d = document.getElementById('f_data');
        const box = document.getElementById('avvisoData');
        if (DATE_NOTE.indexOf(d.value) >= 0) {{
          box.innerHTML = "<strong>C&apos;è già una lettura del " + dataIt(d.value) +
            ".</strong> Salvando la sostituisci: quella di prima non resta da nessuna parte.";
          box.style.display = '';
        }} else {{ box.style.display = 'none'; }}
      }}
      function sommaSalvadanai() {{
        let s = 0;
        for (const [k] of SALVADANAI) s += Number(document.getElementById('sv_'+k).value || 0);
        const box = document.getElementById('sommaSalvadanai');
        const tot = Number(document.getElementById('f_risparmi').value || 0);
        if (!s) {{ box.textContent = ''; return; }}
        const d = Math.round((s - tot) * 100) / 100;
        box.textContent = 'Somma dei secchielli € ' + euroS(s) + ' su € ' + euroS(tot)
          + (Math.abs(d) < 0.01 ? ' — combaciano.'
             : (d < 0 ? ' — ne restano € ' + euroS(-d) + ' non ripartiti.'
                      : ' — € ' + euroS(d) + ' in più del deposito.'));
      }}
      for (const [k] of SALVADANAI) document.getElementById('sv_'+k).addEventListener('input', sommaSalvadanai);
      document.getElementById('f_risparmi').addEventListener('input', sommaSalvadanai);
      sommaSalvadanai(); controllaData();

      function mostraSaldi(j) {{
        DA_ESTRATTO = true;
        document.getElementById('chipSaldi').textContent = 'dall\u2019estratto';
        document.getElementById('f_data').value = j.data;
        document.getElementById('f_conto').value = j.conto;
        document.getElementById('f_risparmi').value = j.risparmi;
        // L'export dei movimenti ricostruisce i salvadanai dalle
        // descrizioni del deposito: li scrive nei campi e apre il riquadro.
        const sv = j.salvadanai || {{}};
        if (Object.keys(sv).length) {{
          for (const [k] of SALVADANAI) document.getElementById('sv_'+k).value = sv[k] != null ? sv[k] : '';
          document.getElementById('sommaSalvadanai').closest('details').open = true;
        }}
        sommaSalvadanai(); controllaData();
        document.getElementById('dettaglioImport').innerHTML = (j.dettaglio || []).map(d =>
          '<div class="row"><span class="t">' + escS(d.nome) + '<span class="sub">' +
          (d.sezione === 'risparmi' ? 'deposito' : 'conto corrente') + ' · ' + escS(d.valuta) +
          '</span></span><span class="v tnum">€ ' + euroS(d.saldo) + '</span></div>').join('');
        // Per ogni conto: apertura + entrate − uscite deve dare la
        // chiusura dichiarata. Se torna, nel file non manca nessuna riga.
        document.getElementById('quadrature').innerHTML = (j.quadrature || []).map(q =>
          '<div class="row"><span class="t">Quadratura · ' + escS(q.nome) + '<span class="sub">' +
          (q.apertura === null ? q.movimenti + ' movimenti · saldo di apertura non trovato'
            : 'apertura € ' + euroS(q.apertura) + ' + entrate € ' + euroS(q.entrate) +
              ' − uscite € ' + euroS(q.uscite) + ' = € ' + euroS(q.calcolato) +
              ' · la banca dichiara € ' + euroS(q.chiusura)) +
          '</span></span><span class="v tnum ' + (q.ok ? 'pos' : (q.scarto === null ? '' : 'neg')) + '">' +
          (q.ok ? '✓ torna' : (q.scarto === null ? '—' : 'scarto € ' + euroS(q.scarto))) + '</span></div>').join('');
      }}

      async function onSalvaSaldi() {{
        const salvadanai = {{}};
        for (const [k] of SALVADANAI) {{
          const v = Number(document.getElementById('sv_'+k).value || 0);
          if (v) salvadanai[k] = v;
        }}
        const quando = document.getElementById('f_data').value;
        if (!quando) {{ toast('Manca la data della lettura', 'err'); return; }}
        if (DATE_NOTE.indexOf(quando) >= 0 &&
            !confirm('Esiste già una lettura del ' + dataIt(quando) + '. Salvando la sostituisci. Procedo?')) return;
        try {{
          const r = await fetch('/spese/api/revolut', {{
            method: 'POST', headers: {{'Content-Type':'application/json'}},
            body: JSON.stringify({{
              data: quando,
              conto: Number(document.getElementById('f_conto').value || 0),
              risparmi: Number(document.getElementById('f_risparmi').value || 0),
              investimenti: Number(document.getElementById('f_investimenti').value || 0),
              salvadanai, fonte: DA_ESTRATTO ? 'estratto' : 'manuale',
            }}),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          if (DATE_NOTE.indexOf(quando) < 0) DATE_NOTE.push(quando);
          toast('Fotografia salvata', 'ok');
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}
    </script>'''

    body = pagina_upload(
        "1 · l'estratto consolidato",
        "Da Revolut: Menu → Estratti conto → Consolidato, formato Excel. Dallo "
        "stesso file leggo i saldi di chiusura e tutti i movimenti.",
        ".xlsx", "/spese/api/revolut/leggi",
        extra_html=saldi, dopo_lettura_js="mostraSaldi(j);")
    if movimenti_ok:
        body += IM.pannello(RM.voci_pannello(client), "/spese/api/revolut/movimenti/importa",
                            obbligatoria=False)
    else:
        body += RM.avviso_migrazione()
    body += '<div id="toast" class="toast"></div>'
    return _render(body, breadcrumb)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@spese_bp.post("/spese/api/revolut/leggi")
def api_revolut_leggi():
    """Legge l'estratto e restituisce saldi e movimenti. Non scrive niente."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "nessun file caricato"}), 400
    try:
        letto = parse_estratto(f.read(), f.filename)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"file non leggibile: {str(e)[:200]}"}), 400
    # Le categorie proposte e i doppioni chiedono il database; se non
    # risponde (o manca la tabella) i saldi si leggono lo stesso.
    client = D.sb()
    avvisi = [{"testo": a, "classe": "warn" if "non tornano" in a else "info"}
              for a in letto.get("avvisi") or []]
    try:
        if client is not None:
            letto["movimenti"], altri = RM.prepara_import(client, letto["movimenti"])
            avvisi += altri
    except Exception:
        pass
    letto["avvisi"] = avvisi
    return jsonify(letto)


@spese_bp.get("/spese/api/revolut")
def api_revolut_get():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    return jsonify(saldo_revolut(client))


@spese_bp.post("/spese/api/revolut")
def api_revolut_salva():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    esito = salva(client, request.get_json(silent=True) or {})
    return (jsonify(esito), 400) if esito.get("error") else jsonify(esito)


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="conti-revolut", eyebrow="Revolut",
                                title_html='Il conto <em>Revolut</em>',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
