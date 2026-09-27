"""
shared/registro.py — I movimenti dei tre conti, in una forma sola.

PERCHE' ESISTE
--------------
I tre conti hanno tre tabelle, nate in tre momenti diversi:

  spese                   WeBank personale — categorie in `cfg_*`
  b2f_spese_piva          WeBank P.IVA — categorie come chiavi di testo
                          (`fatture/costanti.py`), e un terzo tipo,
                          «giroconto», per la quota che passa al personale
  b2f_revolut_movimenti   Revolut — categorie in `cfg_*`, come il personale

Le convenzioni pero' sono gia' le stesse — importo sempre positivo, la
direzione la da' il tipo, i trasferimenti si riconoscono dalla categoria —
e questo modulo e' il punto in cui lo diventano anche nella forma: una
riga per movimento, con gli stessi campi qualunque sia il conto.

    conto          'personale' | 'piva' | 'revolut'
    data, descrizione, importo (positivo)
    tipo           'entrata' | 'uscita' — il «giroconto» della P.IVA e'
                   un'uscita: dal conto P.IVA quei soldi escono
    segno          +1 / −1, gia' calcolato
    categoria, sottocategoria   i nomi, non le chiavi
    trasferimento  True se e' denaro che passa fra due conti tuoi: non e'
                   ne' un guadagno ne' una spesa, e un totale di «quanto
                   ho speso» lo deve lasciare fuori

La P.IVA resta con le sue chiavi a database, apposta: sono categorie
fiscali (INPS versata, imposta sostitutiva, bollo) che alimentano
`v_situazione_annuale`, e spostarle nell'albero del personale vorrebbe
dire mescolare le spese del commercialista con quelle del bar. Qui
diventano nomi leggibili, e basta.
"""
from fatture.costanti import CATEGORIA_GIROCONTO as PIVA_GIROCONTO
from fatture.costanti import CATEGORIE_SPESE_PIVA
from spese import dati as D
from spese import revolut_movimenti as RM

CONTI = (
    ("personale", "WeBank Personale"),
    ("piva",      "WeBank P.IVA"),
    ("revolut",   "Revolut"),
)
CONTI_LABEL = dict(CONTI)

# Categorie che su ciascun conto vogliono dire «passa fra due conti tuoi».
TRASFERIMENTI = {
    "personale": {D.CATEGORIA_GIROCONTO, D.CATEGORIA_RISPARMIO},
    # Anche gli Investimenti: il versamento al conto trading sposta denaro
    # fra due posti tuoi, il patrimonio non cambia. Cambia col mercato,
    # dopo — e quello non e' un movimento, e' la valorizzazione scritta a
    # mano sulla fotografia.
    "revolut":   {D.CATEGORIA_RISPARMIO, RM.CATEGORIA_INTERNO,
                  RM.CATEGORIA_INVESTIMENTI},
}


def _tutte(client, tabella: str, select: str = "*") -> list[dict]:
    """Tutte le righe, a blocchi: PostgREST ne da' 1000 alla volta (README §7)."""
    out, offset, passo = [], 0, 1000
    while True:
        try:
            r = (client.table(tabella).select(select).order("data", desc=False)
                 .order("id").range(offset, offset + passo - 1).execute())
            pagina = getattr(r, "data", None) or []
        except Exception:
            return out
        out.extend(pagina)
        if len(pagina) < passo:
            return out
        offset += passo


def _riga(conto, r, tipo, categoria, sottocategoria, trasferimento):
    imp = round(abs(float(r.get("importo") or 0)), 2)
    return {
        "conto": conto,
        "id": r.get("id"),
        "data": str(r.get("data") or "")[:10],
        "descrizione": r.get("descrizione") or "",
        "tipo": tipo,
        "segno": 1 if tipo == "entrata" else -1,
        "importo": imp,
        "categoria": categoria,
        "sottocategoria": sottocategoria,
        "trasferimento": bool(trasferimento),
    }


def registro(client) -> list[dict]:
    """Tutti i movimenti dei tre conti, dal piu' vecchio, nella forma comune."""
    out = []
    for r in _tutte(client, "v_spese"):
        # Le righe storiche con tipo=giroconto sono entrate (README §8.9).
        tipo = "uscita" if D.TIPI_SEGNO.get(r.get("tipo"), 0) < 0 else "entrata"
        cat = r.get("categoria")
        out.append(_riga("personale", r, tipo, cat, r.get("sottocategoria"),
                         cat in TRASFERIMENTI["personale"]))

    etichette = dict(CATEGORIE_SPESE_PIVA)
    for r in _tutte(client, "b2f_spese_piva"):
        tipo = "entrata" if r.get("tipo") == "entrata" else "uscita"
        chiave = r.get("categoria")
        out.append(_riga("piva", r, tipo, etichette.get(chiave, chiave),
                         r.get("sottocategoria"),
                         r.get("tipo") == "giroconto" or chiave == PIVA_GIROCONTO))

    for r in RM.tutti(client) or []:
        cat = r.get("categoria")
        tipo = "entrata" if r.get("tipo") == "entrata" else "uscita"
        out.append(_riga("revolut", r, tipo, cat, r.get("sottocategoria"),
                         cat in TRASFERIMENTI["revolut"]))

    out.sort(key=lambda x: (x["data"], x["conto"], str(x["id"])))
    return out
