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

Rotte HTML:
  GET  /spese/revolut

Rotte JSON:
  GET  /spese/api/revolut                 -> ultimo saldo registrato
  POST /spese/api/revolut/leggi           -> (multipart) legge l'estratto, non scrive
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
from shared.fmt import eur, data_it
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
    t = (s or "").replace("\xa0", " ").strip()
    t = re.sub(r"[€$£¥]|EUR", "", t).strip()
    if not re.fullmatch(r"-?[\d.]*,?\d*", t) or not re.search(r"\d", t):
        return None
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return None


_MESI = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
         "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12}


def _data(s: str):
    """"12 ago 2026" o "20/04/26" -> date. None se non e' una data."""
    t = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s+([a-zà-ú]{3})[a-zà-ú]*\.?\s+(\d{4})", t, re.I)
    if m and m.group(2).lower() in _MESI:
        try:
            return date(int(m.group(3)), _MESI[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", t)
    if m:
        try:
            return date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
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
    date_nome = re.findall(r"(20\d{6})", nome_file or "")
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


def parse_estratto(file_bytes: bytes, nome_file: str = "") -> dict:
    """
    Legge l'estratto conto consolidato di Revolut.

    Ritorna i saldi di chiusura, divisi fra liquidità (conti correnti) e
    risparmi (conti deposito), più l'elenco dei conti trovati così chi
    guarda può controllare che il totale sia la somma di quello che si
    aspetta. Non scrive niente.

    Struttura del file: sezioni "<qualcosa> Riepiloghi" con dentro un
    blocco per conto ("Conto personale (EUR)", "Deposito senza vincoli
    (EUR)", …), ognuno con la sua riga "Saldo di chiusura". Le sezioni
    degli estratti dei movimenti vengono dopo e qui non servono: si
    smette di raccogliere saldi appena iniziano.
    """
    righe = _righe_csv(file_bytes)
    if not righe:
        raise ValueError("Il file è vuoto.")

    sezione = None          # 'conto' | 'risparmi' | 'investimenti' | None
    conto_corrente = None   # nome del blocco in corso
    dettaglio: list[dict] = []
    investimenti_trovati = False
    avvisi: list[str] = []

    for r in righe:
        celle = [c.strip() for c in r]
        piene = [c for c in celle if c]
        if not piene:
            continue
        testa = piene[0]

        # Cambio di macro-sezione. Gli "Estratti conto"/"Transaction
        # Statements" sono i movimenti: da lì in poi niente più saldi.
        if len(piene) == 1 and testa.endswith(("Riepiloghi", "Riepilogo")):
            basso = testa.lower()
            if "deposito" in basso:
                sezione = "risparmi"
            elif "investment" in basso or "investiment" in basso:
                sezione = "investimenti"
                investimenti_trovati = True
            elif "conti correnti" in basso:
                sezione = "conto"
            else:
                sezione = None
            conto_corrente = None
            continue
        if len(piene) == 1 and ("Estratti conto" in testa
                                or "Transaction Statements" in testa):
            sezione = None
            conto_corrente = None
            continue

        if sezione in (None, "investimenti"):
            continue

        # Nome del conto: unica cella piena, nella forma "Qualcosa (EUR)".
        if len(piene) == 1:
            m = re.fullmatch(r"(.+?)\s*\(([A-Z]{3})\)", testa)
            if m:
                conto_corrente = (re.sub(r"\s+", " ", m.group(1)).strip(), m.group(2))
            continue

        if testa.lower().startswith("saldo di chiusura") and conto_corrente:
            # Su un conto in valuta la riga porta prima l'importo nella
            # valuta del conto e poi il controvalore in euro: l'ultimo
            # numero della riga e' sempre quello in euro.
            importi = [v for v in (_importo(c) for c in piene[1:]) if v is not None]
            if importi:
                dettaglio.append({
                    "sezione": sezione,
                    "nome": conto_corrente[0],
                    "valuta": conto_corrente[1],
                    "saldo": round(importi[-1], 2),
                })
            conto_corrente = None

    if not dettaglio:
        raise ValueError(
            "Non ho trovato nessun saldo di chiusura. È l'estratto conto "
            "consolidato di Revolut in formato Excel?")

    conto = round(sum(d["saldo"] for d in dettaglio if d["sezione"] == "conto"), 2)
    risparmi = round(sum(d["saldo"] for d in dettaglio if d["sezione"] == "risparmi"), 2)

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

    return {
        "data": _data_estratto(righe, nome_file).isoformat(),
        "conto": conto,
        "risparmi": risparmi,
        "dettaglio": dettaglio,
        "investimenti_nel_file": investimenti_trovati,
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

    return {
        "al": al,
        "disponibile": True,
        "data": quando,
        "giorni": giorni,
        "conto": conto,
        "risparmi": risparmi,
        "investimenti": investimenti,
        "saldo": round(conto + risparmi + investimenti, 2),
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


@spese_bp.get("/revolut")
def revolut_pagina():
    breadcrumb = [("Spese", "/spese"), ("Revolut", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb)

    rev = saldo_revolut(client)
    passato = storico(client)

    if rev["disponibile"]:
        eta = ""
        if rev.get("giorni") is not None and rev["giorni"] > 0:
            cls = "warn" if rev["giorni"] > 45 else ""
            eta = (f'<span class="chip {cls}">{rev["giorni"]} giorni fa</span>')
        kpi = f'''
        <div class="grid kpi lead mb-3">
          <div class="card"><div class="stat">
            <div class="val tnum accent">€ {eur(rev["saldo"])}</div>
            <div class="lbl">Totale su Revolut</div>
            <div class="hint">al {data_it(rev["data"])}</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum">€ {eur(rev["conto"])}</div>
            <div class="lbl">Liquidità</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum pos">€ {eur(rev["risparmi"])}</div>
            <div class="lbl">Risparmi</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum">€ {eur(rev["investimenti"])}</div>
            <div class="lbl">Investimenti</div>
            <div class="hint">inserito a mano</div></div></div>
        </div>
        <div class="mb-3">{eta}</div>'''
        avviso_vuoto = ""
    else:
        kpi = ""
        avviso_vuoto = '''<div class="notice info mb-3">
          Nessun saldo registrato. Carica l'estratto conto consolidato che
          scarichi da Revolut (Menu → Estratti conto → Consolidato, formato
          Excel) e conferma i numeri: da lì in poi Revolut compare in home
          accanto agli altri due conti.
        </div>'''

    coer = _riquadro_coerenza(coerenza(client, rev))

    # Salvadanai: valori correnti come default del form.
    correnti = rev.get("salvadanai") or {}
    campi_salvadanai = "".join(f'''
      <div class="field">
        <label>{lbl}</label>
        <input type="number" step="0.01" min="0" inputmode="decimal"
               id="sv_{chiave}" value="{correnti.get(chiave, "")}">
      </div>''' for chiave, lbl, _, _, _, _ in SALVADANAI)

    righe_storico = "".join(f'''
      <div class="row">
        <span class="k">{data_it(s.get("data"))}</span>
        <span class="t">{"da estratto" if s.get("fonte") == "estratto" else "a mano"}
          <span class="sub">liquidità € {eur(s.get("conto"))} · risparmi
            € {eur(s.get("risparmi"))} · investimenti € {eur(s.get("investimenti"))}</span></span>
        <span class="v tnum">€ {eur(float(s.get("conto") or 0)
                                     + float(s.get("risparmi") or 0)
                                     + float(s.get("investimenti") or 0))}</span>
      </div>''' for s in passato)
    blocco_storico = (f'''
      <div class="card">
        <div class="card-head"><div class="eyebrow">Snapshot registrati</div></div>
        <div class="rows detail">{righe_storico}</div>
      </div>''' if righe_storico else "")

    body = f'''
    {avviso_vuoto}{coer}{kpi}
    <div class="grid split">
      <div class="stack">
        <div class="card" id="cardImport">
          <div class="card-head"><div class="eyebrow">Aggiorna dall'estratto</div></div>
          <p class="small muted">
            Carica l'estratto conto consolidato .xlsx di Revolut. Non scrive
            niente: legge i saldi di chiusura, te li mostra, e salvi tu.
          </p>
          <div class="field mt-4">
            <label>Estratto consolidato (.xlsx)</label>
            <input type="file" id="f_file" class="input" accept=".xlsx">
          </div>
          <div class="actions">
            <button type="button" class="btn" onclick="onLeggi()">Leggi il file</button>
          </div>
          <div class="notice err mt-3" id="errImport" style="display:none"></div>
        </div>

        <div class="card" id="cardConferma" style="display:none">
          <div class="card-head"><div class="eyebrow">Cosa ho trovato</div></div>
          <div id="avvisiImport"></div>
          <div class="rows detail" id="dettaglioImport"></div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><div class="eyebrow">Saldi</div></div>
          <div class="field-group">
            <div class="field"><label>Data dei saldi</label>
              <input type="date" id="f_data" value="{rev.get("data") or date.today().isoformat()}"></div>
            <div class="field"><label>Liquidità (€)</label>
              <input type="number" step="0.01" inputmode="decimal" id="f_conto"
                     value="{rev.get("conto") or 0}"></div>
          </div>
          <div class="field-group">
            <div class="field"><label>Risparmi (€)</label>
              <input type="number" step="0.01" inputmode="decimal" id="f_risparmi"
                     value="{rev.get("risparmi") or 0}"></div>
            <div class="field"><label>Investimenti (€)</label>
              <input type="number" step="0.01" inputmode="decimal" id="f_investimenti"
                     value="{rev.get("investimenti") or 0}">
              <div class="hint">Non è nell'estratto: prendilo dall'app.</div></div>
          </div>
          <div class="actions">
            <button type="button" class="btn" onclick="onSalva()">Salva i saldi</button>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="eyebrow">Come sono divisi i risparmi</div></div>
          <p class="small muted">
            Facoltativo, e da scrivere a mano: l'estratto dà solo il totale del
            deposito. Servono alla pagina Risparmi per dire, secchiello per
            secchiello, quanto c'è contro quanto dovrebbe esserci.
          </p>
          <div class="mt-4">{campi_salvadanai}</div>
          <div class="small muted" id="sommaSalvadanai"></div>
        </div>

        {blocco_storico}
      </div>
    </div>

    <div id="toast" class="toast"></div>
    <script>
      const SALVADANAI = {json.dumps([[s[0], s[1]] for s in SALVADANAI], ensure_ascii=False)};

      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 3000);
      }}
      function euro(v) {{
        return new Intl.NumberFormat('it-IT',
          {{minimumFractionDigits:2, maximumFractionDigits:2}}).format(Number(v) || 0);
      }}
      function esc(s) {{
        const d = document.createElement('div'); d.textContent = s == null ? '' : s;
        return d.innerHTML;
      }}

      function sommaSalvadanai() {{
        let s = 0;
        for (const [k] of SALVADANAI) s += Number(document.getElementById('sv_'+k).value || 0);
        const box = document.getElementById('sommaSalvadanai');
        const tot = Number(document.getElementById('f_risparmi').value || 0);
        if (!s) {{ box.textContent = ''; return; }}
        const d = Math.round((s - tot) * 100) / 100;
        box.textContent = 'Somma dei salvadanai € ' + euro(s) + ' · totale risparmi € '
          + euro(tot) + (Math.abs(d) < 0.01 ? ' — combaciano.'
                         : ' — differenza € ' + euro(Math.abs(d)) + '.');
      }}
      for (const [k] of SALVADANAI) {{
        document.getElementById('sv_'+k).addEventListener('input', sommaSalvadanai);
      }}
      document.getElementById('f_risparmi').addEventListener('input', sommaSalvadanai);
      sommaSalvadanai();

      async function onLeggi() {{
        const inp = document.getElementById('f_file');
        const err = document.getElementById('errImport');
        err.style.display = 'none';
        if (!inp.files.length) {{ toast('Scegli il file', 'err'); return; }}
        const fd = new FormData();
        fd.append('file', inp.files[0]);
        try {{
          const r = await fetch('/spese/api/revolut/leggi', {{method:'POST', body: fd}});
          const j = await r.json();
          if (!r.ok) {{ err.textContent = j.error || 'Errore'; err.style.display = 'block'; return; }}

          document.getElementById('f_data').value = j.data;
          document.getElementById('f_conto').value = j.conto;
          document.getElementById('f_risparmi').value = j.risparmi;
          sommaSalvadanai();

          document.getElementById('avvisiImport').innerHTML =
            (j.avvisi || []).map(a => '<div class="notice info small mb-2">' + esc(a) + '</div>').join('');
          document.getElementById('dettaglioImport').innerHTML =
            (j.dettaglio || []).map(d =>
              '<div class="row"><span class="t">' + esc(d.nome) +
              '<span class="sub">' + (d.sezione === 'risparmi' ? 'deposito' : 'conto corrente') +
              ' · ' + esc(d.valuta) + '</span></span>' +
              '<span class="v tnum">€ ' + euro(d.saldo) + '</span></div>').join('');
          document.getElementById('cardConferma').style.display = 'block';
          toast('Letto: liquidità € ' + euro(j.conto) + ', risparmi € ' + euro(j.risparmi), 'ok');
        }} catch (e) {{
          err.textContent = 'Errore rete: ' + e.message; err.style.display = 'block';
        }}
      }}

      async function onSalva() {{
        const salvadanai = {{}};
        for (const [k] of SALVADANAI) {{
          const v = Number(document.getElementById('sv_'+k).value || 0);
          if (v) salvadanai[k] = v;
        }}
        const body = {{
          data: document.getElementById('f_data').value,
          conto: Number(document.getElementById('f_conto').value || 0),
          risparmi: Number(document.getElementById('f_risparmi').value || 0),
          investimenti: Number(document.getElementById('f_investimenti').value || 0),
          salvadanai,
          fonte: document.getElementById('cardConferma').style.display === 'block'
                 ? 'estratto' : 'manuale',
        }};
        try {{
          const r = await fetch('/spese/api/revolut', {{
            method: 'POST', headers: {{'Content-Type':'application/json'}},
            body: JSON.stringify(body),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Saldi salvati', 'ok');
          setTimeout(()=>location.reload(), 700);
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}
    </script>'''

    return _render(body, breadcrumb)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@spese_bp.post("/api/revolut/leggi")
def api_revolut_leggi():
    """Legge l'estratto e restituisce i saldi. Non scrive niente."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "nessun file caricato"}), 400
    try:
        return jsonify(parse_estratto(f.read(), f.filename))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"file non leggibile: {str(e)[:200]}"}), 400


@spese_bp.get("/api/revolut")
def api_revolut_get():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    return jsonify(saldo_revolut(client))


@spese_bp.post("/api/revolut")
def api_revolut_salva():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    esito = salva(client, request.get_json(silent=True) or {})
    return (jsonify(esito), 400) if esito.get("error") else jsonify(esito)


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="spese", eyebrow="Revolut",
                                title_html='I miei <em>risparmi</em> su Revolut',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
