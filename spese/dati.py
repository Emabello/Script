"""
spese/dati.py — Accesso ai dati del conto personale.

LE TABELLE, E PERCHE' NON SI SCRIVE A MANO
------------------------------------------
Il conto personale ha uno schema tutto suo, nato prima di questa app:

  spese                        i movimenti
  cfg_categorie                le categorie
  cfg_sottocategorie           le sottocategorie
  cfg_categoria_sottocategoria gli accoppiamenti ammessi fra le due
  impostazioni                 saldo iniziale e quote di risparmio
  risparmi_periodo             quanto hai messo via davvero
  v_spese                      i movimenti con i nomi delle categorie
  v_periodi_stipendio          i periodi, delimitati dai bonifici
  v_risparmi_mese              il conto di ogni periodo

Tre cose vanno rispettate, e sono tutte trappole silenziose:

1. `spese.mese` e `spese.anno` sono NOT NULL e non hanno default. Sono
   ridondanti rispetto a `data`, ma le viste ci si appoggiano: vanno
   ricavati dalla data a ogni scrittura, o l'insert fallisce.

2. La categoria non e' un testo ma un rimando a
   `cfg_categoria_sottocategoria`, che tiene le coppie valide. Una
   categoria senza sottocategoria ha comunque la sua riga, con
   sottocategoria_id a NULL.

3. Gli id si assegnano col primo libero, non col prossimo della
   sequenza: e' quello che fa la funzione `insert_spesa_first_free_id`
   gia' nel database, che prende anche un lock per non correre.
"""
from datetime import date

from shared.ordina import ordina, ordina_coppie
from shared.supabase_client import get_client, is_configured


TIPI = tuple(ordina_coppie([
    ("entrata",   "Entrata"),
    ("uscita",    "Uscita"),
]))
TIPI_CHIAVI = tuple(k for k, _ in TIPI)
TIPI_LABEL = dict(TIPI)

# I metodi di pagamento suggeriti nel form (una `datalist`, quindi il
# campo resta libero: questi sono solo i suggerimenti). Stavano scritti a
# mano nell'HTML, in ordine di comodita' di chi li aveva elencati.
METODI_PAGAMENTO = tuple(ordina([
    "Bancomat", "Carta di credito", "Contanti", "Bonifico",
    "Giroconto", "Addebito diretto",
]))

# Segno con cui ogni tipo entra nel saldo. "giroconto" non e' piu' una
# scelta del form (era una seconda via, indipendente dalla categoria,
# per dire "e' un trasferimento" — la stessa cosa che gia' fa la
# categoria "Giroconto P.IVA"; le due si erano disallineate: 4 righe
# reali con tipo=giroconto restavano invisibili a v_risparmi_mese, che
# controlla solo tipo=entrata — vedi migrazione 8.9). La chiave resta
# qui solo come compatibilita' di lettura per righe non ancora
# migrate: non e' piu' scrivibile da nessun form ne' dall'API
# (TIPI_CHIAVI non la contiene).
TIPI_SEGNO = {"entrata": 1, "uscita": -1, "giroconto": 1}

# Categoria su cui atterrano i giroconti dalla P.IVA.
CATEGORIA_GIROCONTO = "Giroconto P.IVA"

# La categoria che delimita i periodi in v_periodi_stipendio. Toccarla
# per sbaglio sfasa tutto lo storico dei risparmi.
CATEGORIA_STIPENDIO = "Stipendio"

# Categoria dei trasferimenti verso i salvadanai (Revolut): sono uscite
# vere dal conto, con la data vera del bonifico. Prima di README §8.11
# quel denaro usciva dal saldo tramite `risparmi_periodo`, un numero
# scritto a mano che sostituiva il movimento bancario: le due strade
# convivevano senza che nulla dicesse quale valesse per quale bonifico,
# e un anno di scarti si e' accumulato in silenzio (vedi il log
# funzionale, voce chiusa il 25/08/2026). Adesso il saldo del conto si
# calcola SOLO dai movimenti del conto, come quello della banca.
CATEGORIA_RISPARMIO = "Risparmi"

CAMPI_SCRITTURA = ("data", "descrizione", "importo", "tipo",
                   "metodo_pagamento", "categoria_link_id")


def sb():
    """Client Supabase, o None se non configurato."""
    return get_client() if is_configured() else None


def _righe(r):
    d = getattr(r, "data", None)
    if d is None:
        return []
    return d if isinstance(d, list) else [d]


# ---------------------------------------------------------------------------
# Categorie
# ---------------------------------------------------------------------------

def voci_categoria(client) -> list[dict]:
    """
    Gli accoppiamenti categoria/sottocategoria selezionabili.

    Ritorna una riga per accoppiamento, con l'id del legame — che e' il
    valore da scrivere in `spese.categoria_link_id` — e i due nomi.
    """
    try:
        r = (client.table("cfg_categoria_sottocategoria")
             .select("id, categoria_id, sottocategoria_id,"
                     "cfg_categorie(nome, attiva),"
                     "cfg_sottocategorie(nome, attiva)")
             .eq("attiva", True).execute())
    except Exception:
        return []

    voci = []
    for riga in _righe(r):
        cat = riga.get("cfg_categorie") or {}
        sub = riga.get("cfg_sottocategorie") or {}
        if cat.get("attiva") is False:
            continue
        voci.append({
            "link_id":        riga.get("id"),
            "categoria_id":   riga.get("categoria_id"),
            "categoria":      cat.get("nome") or "—",
            "sottocategoria": sub.get("nome"),
        })
    # Alfabetico per il nome mostrato, non per le colonne `ordine` del
    # database: sono la vecchia disposizione manuale di un'app che aveva
    # un solo elenco, e con una cinquantina di accoppiamenti nei menu
    # produceva un ordine che solo chi l'ha scritto sa ricostruire.
    # Questa e' l'unica funzione che alimenta tutti i menu categoria/
    # sottocategoria dell'area Spese (filtri, form, import da banca).
    return ordina(ordina(voci, per=lambda v: v["sottocategoria"] or ""),
                  per=lambda v: v["categoria"])


def albero_categorie(client) -> list[dict]:
    """Le stesse voci raggruppate per categoria, per i due menu a tendina."""
    gruppi: dict[str, dict] = {}
    for v in voci_categoria(client):
        g = gruppi.setdefault(v["categoria"], {
            "categoria": v["categoria"],
            "categoria_id": v["categoria_id"],
            "voci": [],
        })
        g["voci"].append({"link_id": v["link_id"],
                          "sottocategoria": v["sottocategoria"]})
    return list(gruppi.values())


def link_categoria(client, categoria: str, sottocategoria: str | None = None):
    """id del legame per una coppia di nomi. None se non esiste."""
    for v in voci_categoria(client):
        if v["categoria"] == categoria and v["sottocategoria"] == sottocategoria:
            return v["link_id"]
    return None


# ---------------------------------------------------------------------------
# Movimenti
# ---------------------------------------------------------------------------

def _query_movimenti(client, anno=None, mese=None, tipo=None, categoria=None,
                     sottocategoria=None, metodo=None, importo_min=None,
                     importo_max=None, cerca=None):
    """
    Query filtrata su `v_spese`, senza `limit`/`range`: li aggiunge chi
    chiama, a seconda che serva una pagina per la lista o tutte le righe
    per un totale. Condivisa da `movimenti()` e `totali_periodo()` cosi'
    i filtri restano uno solo, non due copie da tenere allineate.
    """
    q = client.table("v_spese").select("*").order("data", desc=True)
    if anno:
        q = q.eq("anno", anno)
    if mese:
        q = q.eq("mese", mese)
    if tipo:
        q = q.eq("tipo", tipo)
    if categoria:
        q = q.eq("categoria", categoria)
    if sottocategoria:
        q = q.eq("sottocategoria", sottocategoria)
    if metodo:
        q = q.ilike("metodo_pagamento", f"%{metodo}%")
    if importo_min is not None:
        q = q.gte("importo", importo_min)
    if importo_max is not None:
        q = q.lte("importo", importo_max)
    if cerca:
        q = q.ilike("descrizione", f"%{cerca}%")
    return q


def movimenti(client, anno=None, mese=None, tipo=None, categoria=None,
              sottocategoria=None, metodo=None, importo_min=None,
              importo_max=None, cerca=None, limite=300) -> list[dict]:
    """
    Elenco movimenti per la lista, dal piu' recente, fino a `limite`.

    Legge da `v_spese` e non da `spese` perche' la vista porta gia' i
    nomi di categoria e sottocategoria: senza, ogni riga costerebbe due
    join a mano.

    **Non usare questa funzione per i totali di un periodo**: un anno
    pieno puo' avere piu' righe di `limite`, e sommare solo le piu'
    recenti darebbe un saldo sbagliato. Per quello c'e'
    `totali_periodo()`, che non tronca mai.
    """
    try:
        q = _query_movimenti(client, anno, mese, tipo, categoria,
                             sottocategoria, metodo, importo_min,
                             importo_max, cerca)
        return _righe(q.limit(limite).execute())
    except Exception:
        return []


def righe_periodo(client, anno=None, mese=None, tipo=None,
                  categoria=None, sottocategoria=None, metodo=None,
                  importo_min=None, importo_max=None,
                  cerca=None) -> list[dict]:
    """
    Come `movimenti()`, ma senza limite: pagina con `.range()` finche' i
    risultati non finiscono. Serve perche' PostgREST tronca comunque a un
    tetto per richiesta (di solito 1000 righe) — un `.limit()` alto da
    solo non basta a garantire tutte le righe di un anno che ne ha di
    piu'; qui si prendono a blocchi finche' un blocco torna incompleto.

    Pubblica (non `_privata`) perche' oltre a `totali_periodo()` la usa
    anche il "come viene calcolato" di `spese/movimenti.py`: la stessa
    lista completa alimenta sia i totali sia il dettaglio riga per riga,
    cosi' non possono disallinearsi fra loro.
    """
    out: list[dict] = []
    offset = 0
    passo = 1000
    while True:
        try:
            q = _query_movimenti(client, anno, mese, tipo, categoria,
                                 sottocategoria, metodo, importo_min,
                                 importo_max, cerca)
            pagina = _righe(q.range(offset, offset + passo - 1).execute())
        except Exception:
            break
        out.extend(pagina)
        if len(pagina) < passo:
            break
        offset += passo
    return out


def totali_periodo(client, anno=None, mese=None, tipo=None, categoria=None,
                   sottocategoria=None, metodo=None, importo_min=None,
                   importo_max=None, cerca=None) -> dict:
    """
    Entrate/uscite/saldo/quota-P.IVA su **tutte** le righe che rispettano
    i filtri, non solo le prime mostrate in lista. Usare questa per i KPI
    di riepilogo, mai `totali(movimenti(...))` — quest'ultimo tronca a
    `limite` e su un anno pieno da' un saldo sbagliato per difetto.
    """
    righe = righe_periodo(client, anno, mese, tipo, categoria,
                                     sottocategoria, metodo, importo_min,
                                     importo_max, cerca)
    return totali(righe)


def apertura(client) -> dict:
    """
    Il punto di partenza del conto: quanto c'era, e **a che data**.

    Si prende la riga con `valido_dal` **piu' vecchia**, non la piu'
    recente: e' il saldo di apertura, il punto da cui i movimenti
    iniziano a contare. Le righe successive esistono per far cambiare le
    percentuali di risparmio nel tempo (e' cosi' che le usa
    v_risparmi_mese), non per ridefinire l'apertura.

    La data conta quanto l'importo. Finche' `valido_dal` diceva
    2000-01-01 su un saldo che era invece quello del 26/02/2025, chi
    avesse importato i movimenti dell'anno prima li avrebbe sommati
    sopra un'apertura che li conteneva gia': il saldo sarebbe saltato di
    un migliaio di euro senza un errore, senza niente da guardare.
    Restituendo anche la data, `saldo_conto()` puo' contare solo i
    movimenti che vengono dopo.
    """
    vuoto = {"saldo": 0.0, "dal": None}
    try:
        r = (client.table("impostazioni").select("saldo_iniziale,valido_dal")
             .order("valido_dal", desc=False).limit(1).execute())
        righe = _righe(r)
    except Exception:
        return vuoto
    if not righe:
        return vuoto
    try:
        v = round(float(righe[0].get("saldo_iniziale") or 0), 2)
    except (TypeError, ValueError):
        return vuoto
    return {"saldo": v, "dal": (righe[0].get("valido_dal") or "")[:10] or None}


def saldo_iniziale(client) -> float:
    """Solo l'importo dell'apertura. Vedi `apertura()` per la data."""
    return apertura(client)["saldo"]


def risparmio_totale(client, al: str | None = None) -> float:
    """
    Quanto e' finito nei salvadanai in tutto, fino a `al`, **al netto
    dei rientri**.

    Si legge dai movimenti, non da una dichiarazione: sono le righe di
    `spese` con categoria "Risparmi", cioe' i bonifici verso Revolut
    con la loro data vera, piu' le entrate della stessa categoria per i
    soldi tornati indietro (il 27/05/2026 sono usciti 430,17 e rientrati
    lo stesso giorno: contarli solo in uscita direbbe che sono stati
    risparmiati, e non e' vero).

    **Non entra piu' nel saldo del conto** — quelle uscite sono gia'
    dentro `uscite`, come ogni altro movimento. Serve alla pagina
    Risparmi e al confronto con i saldi Revolut.
    """
    al = al or date.today().isoformat()
    tot = 0.0
    offset, passo = 0, 1000
    while True:
        try:
            pagina = _righe(client.table("v_spese").select("importo,tipo,data,categoria")
                            .eq("categoria", CATEGORIA_RISPARMIO).lte("data", al)
                            .order("data", desc=False)
                            .range(offset, offset + passo - 1).execute())
        except Exception:
            return round(tot, 2)
        for riga in pagina:
            try:
                imp = abs(float(riga.get("importo") or 0))
            except (TypeError, ValueError):
                continue
            tot += imp if TIPI_SEGNO.get(riga.get("tipo"), 0) < 0 else -imp
        if len(pagina) < passo:
            break
        offset += passo
    return round(tot, 2)


def saldo_conto(client, al: str | None = None) -> dict:
    """
    Saldo reale del conto personale a una data (default: oggi).

        saldo = apertura + entrate - uscite

    Nient'altro. E' la stessa formula con cui la banca calcola il suo, e
    questo non e' un dettaglio: **il saldo di un conto si calcola solo
    dai movimenti di quel conto**. Ogni volta che un euro esce senza
    lasciare una riga qui dentro, il saldo mente e nessuno se ne accorge.

    Fino al 25/08/2026 c'era un quarto termine, `- risparmio_messo_via`,
    che toglieva i bonifici verso i salvadanai Revolut leggendoli da
    `risparmi_periodo` — un numero digitato a mano al posto del
    movimento bancario. Le due strade convivevano: alcuni bonifici erano
    registrati come uscite (tolti una volta), altri solo dichiarati
    (tolti una volta), qualcuno tutti e due (tolti **due** volte),
    qualcuno nessuno dei due (**mai** tolti). In diciotto mesi lo scarto
    contro l'estratto era arrivato a 829,78 euro, in due direzioni
    opposte che si mascheravano a vicenda. Ora quei bonifici sono righe
    di `spese` come tutte le altre, categoria "Risparmi", con la data
    vera del bonifico (README §8.11): una sola strada, una sola verita'.

    Due dettagli che sembrano piccoli e non lo sono:

    * si parte **dalla data dell'apertura**, non dall'inizio dei tempi.
      Il saldo di apertura fotografa un conto a un giorno preciso: un
      movimento anteriore a quel giorno e' gia' dentro quel numero, e
      sommarlo lo conterebbe due volte. Finche' `valido_dal` diceva
      2000-01-01 la cosa non si poteva nemmeno vedere.
    * i movimenti con data futura restano fuori: sono previsti, non
      ancora accaduti.

    Legge `spese` a blocchi finche' non finiscono. PostgREST tronca ogni
    richiesta a un tetto (di solito 1000 righe) e la tabella ne ha gia'
    di piu': una singola select darebbe un saldo sbagliato per difetto
    senza nessun errore visibile. Se una pagina fallisce si torna
    `disponibile: False` invece di un numero a meta', che sarebbe peggio
    di nessun numero.
    """
    al = al or date.today().isoformat()
    vuoto = {"al": al, "disponibile": False, "saldo": 0.0, "entrate": 0.0,
             "uscite": 0.0, "saldo_iniziale": 0.0, "dal": None,
             "risparmiato": 0.0, "movimenti": 0}

    ap = apertura(client)
    dal = ap["dal"]

    entrate = uscite = 0.0
    n = 0
    offset, passo = 0, 1000
    while True:
        try:
            q = (client.table("spese").select("importo,tipo,data")
                 .lte("data", al))
            if dal:
                q = q.gt("data", dal)
            pagina = _righe(q.order("data", desc=False)
                            .range(offset, offset + passo - 1).execute())
        except Exception:
            return vuoto
        for r in pagina:
            imp = abs(float(r.get("importo") or 0))
            # TIPI_SEGNO e non TIPI_CHIAVI: le righe storiche con
            # tipo=giroconto (migrazione README 8.9) sono entrate.
            segno = TIPI_SEGNO.get(r.get("tipo"), 0)
            if segno > 0:
                entrate += imp
            elif segno < 0:
                uscite += imp
            n += 1
        if len(pagina) < passo:
            break
        offset += passo

    return {
        "al": al,
        "disponibile": True,
        "saldo_iniziale": ap["saldo"],
        "dal": dal,
        "entrate": round(entrate, 2),
        "uscite": round(uscite, 2),
        # Non entra piu' nel saldo: e' gia' dentro `uscite`. Resta qui
        # perche' la home e /spese lo mostrano come "di cui finito nei
        # salvadanai", che e' un'informazione, non una correzione.
        "risparmiato": risparmio_totale(client, al),
        "saldo": round(ap["saldo"] + entrate - uscite, 2),
        "movimenti": n,
    }


def movimento(client, mid: int) -> dict | None:
    try:
        r = client.table("v_spese").select("*").eq("id", mid).limit(1).execute()
        righe = _righe(r)
        return righe[0] if righe else None
    except Exception:
        return None


def _normalizza(dati: dict) -> dict:
    """Ripulisce e completa i campi in arrivo dal form."""
    out = {}
    for k in CAMPI_SCRITTURA:
        if k not in dati:
            continue
        v = dati[k]
        if isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    if out.get("importo") is not None:
        # Sempre positivo: la direzione la da' `tipo`, non il segno. Due
        # convenzioni sovrapposte si annullerebbero a vicenda.
        out["importo"] = round(abs(float(out["importo"])), 2)
    return out


def crea(client, dati: dict) -> dict:
    """
    Registra un movimento. Ritorna {"id": ...} o {"error": ...}.

    Passa dalla funzione del database, che assegna il primo id libero
    sotto lock. Se non risponde ripiega sull'insert diretto: `spese.id`
    e' IDENTITY e si genera comunque.
    """
    d = _normalizza(dati)
    quando = d.get("data") or date.today().isoformat()
    d["data"] = quando
    d["mese"] = int(quando[5:7])
    d["anno"] = int(quando[:4])

    if not d.get("tipo") or d["tipo"] not in TIPI_CHIAVI:
        return {"error": "tipo non valido"}
    if d.get("importo") in (None, 0):
        return {"error": "importo mancante"}

    try:
        r = client.rpc("insert_spesa_first_free_id", {
            "p_data":              d["data"],
            "p_importo":           d["importo"],
            "p_tipo":              d["tipo"],
            "p_mese":              d["mese"],
            "p_anno":              d["anno"],
            "p_descrizione":       d.get("descrizione"),
            "p_metodo_pagamento":  d.get("metodo_pagamento"),
            "p_categoria_link_id": d.get("categoria_link_id"),
        }).execute()
        dato = r.data
        if isinstance(dato, list):
            dato = dato[0] if dato else {}
        if isinstance(dato, dict) and dato.get("id"):
            return {"id": dato["id"]}
    except Exception:
        pass

    try:
        r = client.table("spese").insert(d).execute()
        righe = _righe(r)
        return {"id": righe[0].get("id") if righe else None}
    except Exception as e:
        return {"error": str(e)[:200]}


def aggiorna(client, mid: int, dati: dict) -> dict:
    """Modifica un movimento. Cambiando la data risistema mese e anno."""
    d = _normalizza(dati)
    if not d:
        return {"error": "nessun campo da aggiornare"}
    if d.get("tipo") and d["tipo"] not in TIPI_CHIAVI:
        return {"error": "tipo non valido"}
    if d.get("data"):
        d["mese"] = int(str(d["data"])[5:7])
        d["anno"] = int(str(d["data"])[:4])
    try:
        client.table("spese").update(d).eq("id", mid).execute()
        return {"id": mid}
    except Exception as e:
        return {"error": str(e)[:200]}


def elimina(client, mid: int) -> dict:
    try:
        client.table("spese").delete().eq("id", mid).execute()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)[:200]}


def collegato(client, mid: int) -> dict | None:
    """
    Origine del giroconto che ha prodotto questo movimento, se ce n'e'
    una: la ripartizione automatica di una fattura, o un giroconto
    registrato a mano dalla sezione Spese P.IVA.

    Serve a impedire che si cancelli o alteri a meta' uno spostamento fra
    conti: l'altra riga resterebbe senza contropartita.
    """
    # Nota: le righe di ritorno hanno gia' un campo `tipo` proprio
    # (entrata/uscita/giroconto): il discriminante qui si chiama `origine`
    # apposta, per non finire sovrascritto dallo spread della riga.
    try:
        r = (client.table("b2f_fatture").select("id, numero")
             .eq("giroconto_personale_id", mid).limit(1).execute())
        righe = _righe(r)
        if righe:
            return {"origine": "fattura", "id": righe[0].get("id"),
                    "numero": righe[0].get("numero")}
    except Exception:
        pass
    try:
        r = (client.table("b2f_spese_piva").select("id, descrizione")
             .eq("giroconto_personale_id", mid).limit(1).execute())
        righe = _righe(r)
        if righe:
            return {"origine": "piva", "id": righe[0].get("id"),
                    "descrizione": righe[0].get("descrizione")}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Totali
# ---------------------------------------------------------------------------

def totali(righe: list[dict]) -> dict:
    """
    Entrate, uscite, quota delle entrate arrivata dalla P.IVA, e saldo.

    Il giroconto dalla P.IVA arriva come riga `tipo=entrata`, categoria
    "Giroconto P.IVA" — apposta, cosi' v_risparmi_mese lo conta nel
    budget (vedi fatture/giroconto.py). "giroconti" qui NON e' quindi un
    terzo bucket da sommare al saldo: e' un sotto-totale di "entrate",
    solo per mostrarlo separato. Il vecchio codice cercava `tipo ==
    "giroconto"`, un valore che i giroconti automatici P.IVA->personale
    non usano mai: "Dalla P.IVA" risultava sempre zero anche quando il
    denaro era arrivato (e gia' contato, correttamente, in "entrate").

    Resta comunque gestito anche `tipo == "giroconto"`, per compatibilita'
    con righe storiche non ancora passate dalla migrazione 8.9 (il form
    non offre piu' questa scelta, era un secondo modo — indipendente
    dalla categoria — di dire "e' un trasferimento", che restava invisibile
    a v_risparmi_mese).
    """
    t = {"entrate": 0.0, "uscite": 0.0, "giroconti": 0.0, "n": len(righe)}
    for r in righe:
        imp = abs(float(r.get("importo") or 0))
        tipo = r.get("tipo")
        if tipo == "entrata":
            t["entrate"] += imp
            if r.get("categoria") == CATEGORIA_GIROCONTO:
                t["giroconti"] += imp
        elif tipo == "uscita":
            t["uscite"] += imp
        elif tipo == "giroconto":
            t["entrate"] += imp
            t["giroconti"] += imp
    t["saldo"] = round(t["entrate"] - t["uscite"], 2)
    for k in ("entrate", "uscite", "giroconti"):
        t[k] = round(t[k], 2)
    return t


def per_categoria(righe: list[dict], tipo: str = "uscita",
                  campo: str = "categoria") -> list[dict]:
    """
    Ripartizione per categoria (o sottocategoria, con `campo`), dalla
    piu' pesante. Con `campo="sottocategoria"` serve per il drill-down:
    quando la lista e' gia' filtrata su una categoria, ripartirla di
    nuovo per la stessa categoria darebbe sempre "100%, una riga sola" —
    un solo numero che non dice niente. La sottocategoria invece si.
    """
    vuoto = "Senza categoria" if campo == "categoria" else "Senza sottocategoria"
    agg: dict[str, float] = {}
    for r in righe:
        if r.get("tipo") != tipo:
            continue
        nome = r.get(campo) or vuoto
        agg[nome] = agg.get(nome, 0.0) + abs(float(r.get("importo") or 0))
    tot = sum(agg.values()) or 1.0
    out = [{"categoria": k, "importo": round(v, 2), "quota": v / tot}
           for k, v in agg.items()]
    out.sort(key=lambda x: -x["importo"])
    return out


# ---------------------------------------------------------------------------
# Risparmi
# ---------------------------------------------------------------------------

def periodi_risparmio(client, limite=24) -> list[dict]:
    """
    Le righe di v_risparmi_mese, dal periodo piu' recente.

    I nomi delle colonne della vista hanno spazi e maiuscole; qui
    vengono tradotti in chiavi normali, cosi' il resto del codice non
    deve conoscerli.
    """
    try:
        r = (client.table("v_risparmi_mese").select("*")
             .order("Data bonifico", desc=True).limit(limite).execute())
    except Exception:
        return []

    mappa = {
        "Data bonifico":              "data_bonifico",
        "Data prossimo bonifico":     "prossimo_bonifico",
        "Mese":                       "mese",
        "Importo Bonifico":           "bonifico",
        "Importo Prima Del Bonifico": "saldo_iniziale",
        "Totale Fisso":               "fisso",
        "Totale Personale":           "personale",
        "Totale Benzina":             "benzina",
        "Totale Viaggi":              "viaggi",
        "Totale Speso":               "speso",
        "Totale Altre Entrate":       "altre_entrate",
        "Totale Rimanente":           "rimanente",
        "Risparmio consigliato (€)":  "risparmio_consigliato",
        "Risparmio effettivo (€)":    "risparmio_effettivo",
        "Totale Rimanente (finale)":  "rimanente_finale",
        "Quota Fondo Emergenze":      "quota_emergenze",
        "Quota Viaggi":               "quota_viaggi",
        "Quota Fondo Casa":           "quota_casa",
        "Quota Regali":               "quota_regali",
        "Quota Altro":                "quota_altro",
    }
    out = []
    for riga in _righe(r):
        out.append({nuovo: riga.get(vecchio) for vecchio, nuovo in mappa.items()})
    return out


def risparmio_effettivo(client, data_bonifico: str, importo: float) -> dict:
    """Registra quanto hai messo via davvero per un periodo."""
    try:
        client.table("risparmi_periodo").upsert({
            "data_bonifico": data_bonifico,
            "effettivo_risparmio": round(float(importo or 0), 2),
        }).execute()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)[:200]}


def registra_bonifico_risparmio(client, importo, quando: str | None = None,
                                descrizione: str | None = None,
                                metodo: str = "Bonifico") -> dict:
    """
    Il bonifico verso i salvadanai, come movimento vero.

    E' l'unica scrittura che chiude il cerchio della migrazione §8.11:
    prima il risparmio era un numero digitato su `risparmi_periodo` che
    *sostituiva* il movimento bancario, e per diciotto mesi il saldo
    calcolato e quello della banca sono scivolati via l'uno dall'altro
    di 829,78 €. Adesso mettere via denaro e' un'uscita dal conto come
    comprare la benzina — perche' e' esattamente quello che succede sul
    conto — e il saldo torna a essere `apertura + entrate − uscite`.

    Non spostiamo denaro noi: il bonifico lo fai tu dalla banca. Questa
    funzione registra che e' successo. La ripartizione fra i cinque
    secchielli non e' scritta qui riga per riga (sarebbero cinque
    movimenti dove la banca ne vede uno): sta nelle percentuali di
    `impostazioni`, e `v_risparmi_mese` la ricalcola per ogni periodo.
    """
    try:
        val = round(abs(float(importo or 0)), 2)
    except (TypeError, ValueError):
        return {"error": "importo non valido"}
    if val <= 0:
        return {"error": "importo mancante"}

    quando = quando or date.today().isoformat()
    link = link_categoria(client, CATEGORIA_RISPARMIO)
    if not link:
        return {"error": f'La categoria "{CATEGORIA_RISPARMIO}" non esiste: '
                         f'esegui la migrazione README §8.11 nell\'SQL Editor '
                         f'di Supabase.'}

    return crea(client, {
        "data": quando,
        "importo": val,
        # Uscita, non "giroconto": dal conto personale quel denaro esce
        # davvero, e la banca lo vede come un bonifico qualunque.
        "tipo": "uscita",
        "metodo_pagamento": metodo,
        "categoria_link_id": link,
        "descrizione": descrizione or "Bonifico ai salvadanai",
    })


def risparmio_del_periodo(client, dal: str, al: str | None = None) -> float:
    """
    Quanto e' gia' stato messo via **dentro un periodo**, al netto dei
    rientri. Serve a sapere se la procedura di fine periodo e' gia' stata
    fatta: `v_risparmi_mese` lo espone gia', ma solo per i periodi che la
    vista conosce — e il periodo aperto in questo momento e' l'unico che
    conta per decidere se mostrare l'avviso.

    **Senza `al` non c'e' tetto superiore, nemmeno oggi**, ed e' voluto:
    la domanda qui non e' "quanto e' gia' uscito dal conto" (quella la
    fa `saldo_conto`, che i movimenti futuri li esclude apposta) ma "il
    bonifico di questo periodo l'ho gia' registrato?". Un bonifico
    datato domani e' registrato: fermarsi a oggi direbbe di no, e la
    procedura lo farebbe registrare una seconda volta.
    """
    tot = 0.0
    try:
        q = (client.table("v_spese").select("importo,tipo,data,categoria")
             .eq("categoria", CATEGORIA_RISPARMIO).gte("data", dal))
        if al:
            q = q.lte("data", al)
        righe = _righe(q.execute())
    except Exception:
        return 0.0
    for riga in righe:
        try:
            imp = abs(float(riga.get("importo") or 0))
        except (TypeError, ValueError):
            continue
        tot += imp if TIPI_SEGNO.get(riga.get("tipo"), 0) < 0 else -imp
    return round(tot, 2)


def avviso_risparmio(client) -> dict | None:
    """
    "E' arrivato lo stipendio e non hai ancora messo via niente."

    Ritorna None quando non c'e' niente da dire — ed e' la maggior parte
    delle volte: solo un periodo **aperto**, con un consigliato sopra
    zero e nessuna uscita verso i salvadanai, merita di comparire in
    home. Un avviso che c'e' sempre non lo legge piu' nessuno.

    Il periodo si apre con il bonifico dello stipendio o il giroconto
    dalla P.IVA (v_periodi_stipendio, README §8.7): e' quello il momento
    in cui la domanda "quanto ne metto via?" ha una risposta, perche'
    prima non si sa ancora quanto e' entrato.
    """
    try:
        periodi = periodi_risparmio(client, limite=1)
    except Exception:
        return None
    if not periodi:
        return None

    corrente = periodi[0]
    dal = str(corrente.get("data_bonifico") or "")[:10]
    if not dal:
        return None
    try:
        consigliato = round(float(corrente.get("risparmio_consigliato") or 0), 2)
    except (TypeError, ValueError):
        return None
    if consigliato <= 0:
        return None
    if risparmio_del_periodo(client, dal) > 0:
        return None

    return {"dal": dal, "consigliato": consigliato,
            "speso": corrente.get("speso"), "rimanente": corrente.get("rimanente")}


def impostazioni(client) -> dict:
    """Le impostazioni in vigore piu' recenti."""
    try:
        r = (client.table("impostazioni").select("*")
             .order("valido_dal", desc=True).limit(1).execute())
        righe = _righe(r)
        return righe[0] if righe else {}
    except Exception:
        return {}


def anni_disponibili(client) -> list[int]:
    """Anni con almeno un movimento, dal piu' recente."""
    try:
        r = (client.table("spese").select("anno")
             .order("anno", desc=True).limit(2000).execute())
        anni = sorted({int(x["anno"]) for x in _righe(r) if x.get("anno")},
                      reverse=True)
        return anni or [date.today().year]
    except Exception:
        return [date.today().year]


# ---------------------------------------------------------------------------
# Verifica contro l'estratto conto
# ---------------------------------------------------------------------------

# Sotto questa soglia lo scarto non vale un allarme: arrotondamenti e
# operazioni contabilizzate a cavallo del giorno del controllo.
TOLLERANZA_VERIFICA = 1.00


def ultima_verifica(client, conto: str) -> dict | None:
    """
    L'ultimo saldo dichiarato dalla banca per questo conto, se registrato.

    E' l'unico punto in cui entra un numero di **fonte esterna** con cui
    confrontarsi. Senza, un errore nei movimenti resta invisibile finche'
    qualcuno non apre l'app della banca e fa il confronto a mente: e'
    esattamente cosi' che uno scarto di 829,78 euro e' cresciuto per
    diciotto mesi senza che niente lo segnalasse.
    """
    try:
        r = (client.table("b2f_saldi_verifica")
             .select("data,conto,saldo_banca,note")
             .eq("conto", conto).order("data", desc=True).limit(1).execute())
        righe = _righe(r)
    except Exception:
        return None
    if not righe:
        return None
    v = righe[0]
    try:
        return {"data": (v.get("data") or "")[:10],
                "saldo_banca": round(float(v.get("saldo_banca") or 0), 2),
                "note": v.get("note")}
    except (TypeError, ValueError):
        return None


def verifica_saldo(client, conto: str, saldo_calcolato: float,
                   saldo_al: str | None = None) -> dict | None:
    """
    Confronta il saldo calcolato dall'app con l'ultimo estratto registrato.

    Il confronto giusto e' **alla data dell'estratto**, non a oggi: fra
    quel giorno e adesso ci sono movimenti veri, e la differenza non
    sarebbe un errore. Chi chiama passa quindi il saldo ricalcolato a
    quella data (`saldo_al`), non quello di oggi.

    Ritorna None se non c'e' nessun controllo registrato — meglio non
    dire niente che dire "tutto a posto" senza aver confrontato nulla.
    """
    v = ultima_verifica(client, conto)
    if not v:
        return None
    scarto = round(float(saldo_calcolato or 0) - v["saldo_banca"], 2)
    giorni = None
    try:
        giorni = (date.today() - date.fromisoformat(v["data"])).days
    except (TypeError, ValueError):
        pass
    return {
        "data": v["data"],
        "saldo_banca": v["saldo_banca"],
        "saldo_app": round(float(saldo_calcolato or 0), 2),
        "scarto": scarto,
        "allineato": abs(scarto) <= TOLLERANZA_VERIFICA,
        "giorni": giorni,
        "saldo_al": saldo_al or v["data"],
        "note": v.get("note"),
    }


def registra_verifica(client, conto: str, data_estratto: str,
                      saldo_banca: float, note: str | None = None) -> dict:
    """Registra il saldo letto sull'estratto. Uno per conto per data."""
    try:
        client.table("b2f_saldi_verifica").upsert({
            "conto": conto,
            "data": data_estratto,
            "saldo_banca": round(float(saldo_banca or 0), 2),
            "note": note,
        }, on_conflict="conto,data").execute()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)[:200]}
