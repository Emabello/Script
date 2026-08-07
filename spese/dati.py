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

from shared.supabase_client import get_client, is_configured


TIPI = (
    ("entrata",   "Entrata"),
    ("uscita",    "Uscita"),
    ("giroconto", "Giroconto"),
)
TIPI_CHIAVI = tuple(k for k, _ in TIPI)
TIPI_LABEL = dict(TIPI)

# Segno con cui ogni tipo entra nel saldo. Il giroconto e' un
# trasferimento fra conti tuoi: qui *arriva*, quindi somma. Sul lato
# P.IVA la stessa riga viene sottratta.
TIPI_SEGNO = {"entrata": 1, "uscita": -1, "giroconto": 1}

# Categoria su cui atterrano i giroconti dalla P.IVA.
CATEGORIA_GIROCONTO = "Giroconto P.IVA"

# La categoria che delimita i periodi in v_periodi_stipendio. Toccarla
# per sbaglio sfasa tutto lo storico dei risparmi.
CATEGORIA_STIPENDIO = "Stipendio"

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
             .select("id, ordine, categoria_id, sottocategoria_id,"
                     "cfg_categorie(nome, ordine, attiva),"
                     "cfg_sottocategorie(nome, ordine, attiva)")
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
            "ordine_cat":     cat.get("ordine") or 0,
            "ordine":         riga.get("ordine") or 0,
        })
    voci.sort(key=lambda v: (v["ordine_cat"], v["categoria"],
                             v["ordine"], v["sottocategoria"] or ""))
    return voci


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

def movimenti(client, anno=None, mese=None, tipo=None, categoria=None,
              cerca=None, limite=300) -> list[dict]:
    """
    Elenco movimenti, dal piu' recente.

    Legge da `v_spese` e non da `spese` perche' la vista porta gia' i
    nomi di categoria e sottocategoria: senza, ogni riga costerebbe due
    join a mano.
    """
    try:
        q = client.table("v_spese").select("*").order("data", desc=True)
        if anno:
            q = q.eq("anno", anno)
        if mese:
            q = q.eq("mese", mese)
        if tipo:
            q = q.eq("tipo", tipo)
        if categoria:
            q = q.eq("categoria", categoria)
        if cerca:
            q = q.ilike("descrizione", f"%{cerca}%")
        return _righe(q.limit(limite).execute())
    except Exception:
        return []


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


def collegato_a_fattura(client, mid: int):
    """
    Numero della fattura il cui giroconto ha prodotto questo movimento.

    Serve a impedire che si cancelli a mano meta' di uno spostamento:
    l'altra riga resterebbe sul conto P.IVA senza contropartita.
    """
    try:
        r = (client.table("b2f_fatture").select("id, numero")
             .eq("giroconto_personale_id", mid).limit(1).execute())
        righe = _righe(r)
        return righe[0] if righe else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Totali
# ---------------------------------------------------------------------------

def totali(righe: list[dict]) -> dict:
    """Entrate, uscite, giroconti e saldo di un insieme di movimenti."""
    t = {"entrate": 0.0, "uscite": 0.0, "giroconti": 0.0, "n": len(righe)}
    for r in righe:
        imp = abs(float(r.get("importo") or 0))
        tipo = r.get("tipo")
        if tipo == "entrata":
            t["entrate"] += imp
        elif tipo == "uscita":
            t["uscite"] += imp
        elif tipo == "giroconto":
            t["giroconti"] += imp
    t["saldo"] = round(t["entrate"] + t["giroconti"] - t["uscite"], 2)
    for k in ("entrate", "uscite", "giroconti"):
        t[k] = round(t[k], 2)
    return t


def per_categoria(righe: list[dict], tipo: str = "uscita") -> list[dict]:
    """Ripartizione per categoria, dalla piu' pesante."""
    agg: dict[str, float] = {}
    for r in righe:
        if r.get("tipo") != tipo:
            continue
        nome = r.get("categoria") or "Senza categoria"
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
