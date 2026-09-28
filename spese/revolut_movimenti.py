"""
spese/revolut_movimenti.py — I movimenti del conto Revolut.

PERCHE' ESISTE
--------------
Fino al 27/09/2026 Revolut era **solo una fotografia**: `b2f_revolut`
teneva i saldi di chiusura dell'estratto, e nient'altro. Degli altri due
conti l'app sa ogni riga — chi ha pagato, quanto, con che categoria —
di questo sapeva soltanto quanto c'era a una data. Un'entrata su Revolut
non aveva un tipo, non aveva una categoria, e non esisteva da nessuna
parte: la domanda «da dove arrivano i soldi che ci sono?» non aveva
risposta, e nemmeno «quanto ho speso con la carta Revolut in vacanza».

Qui i movimenti diventano righe **nella stessa forma degli altri due
conti**:

  * importo sempre positivo, la direzione la da' `tipo` (entrata/uscita)
    — la stessa convenzione di `spese` e di `b2f_spese_piva` (README §7,
    «Il tipo dà la direzione, non il segno»);
  * la categoria e' un rimando a `cfg_categoria_sottocategoria`, lo
    **stesso albero** del conto personale: una cena pagata con Revolut e'
    «Personale › Cena» esattamente come se l'avessi pagata con WeBank, e
    finisce nella stessa ripartizione;
  * i trasferimenti si dicono con la categoria, non con il tipo (README
    §7, «"È un trasferimento" si dice solo con la categoria»).

LE CATEGORIE CHE SERVONO SOLO QUI (migrazione §8.19)
----------------------------------------------------
  Risparmi           gia' esistente: sul personale e' l'uscita verso
                     Revolut, qui e' la stessa cosa vista dall'altra
                     parte — un'entrata. Stessa categoria, tipo opposto,
                     come «Giroconto P.IVA» fra P.IVA e personale.
  Giroconto Revolut  denaro che passa fra la liquidita' e il deposito
                     dei salvadanai, dentro Revolut. Non entra e non
                     esce da niente: resta fuori da entrate e uscite.
  Interessi          quello che il deposito matura (e la ritenuta).
  Investimenti       versamenti e prelievi verso il conto trading.

IL SALDO: FOTOGRAFIA + MOVIMENTI DOPO
-------------------------------------
Il saldo del conto personale e' `apertura + movimenti`. Qui l'apertura e'
l'ultima fotografia: il saldo di Revolut a oggi e' l'ultimo estratto piu'
i movimenti registrati **dopo** quel giorno. Senza movimenti successivi
e' esattamente la fotografia di prima, quindi niente cambia per chi non
ne registra; con, il saldo smette di essere fermo alla data dell'estratto.

IL PONTE CON WEBANK
-------------------
Ogni bonifico «Risparmi» che esce da WeBank deve entrare su Revolut, con
lo stesso importo, entro pochi giorni. Sono due righe di due tabelle che
descrivono lo stesso euro: `ponte()` le appaia, e quello che resta
spaiato e' un errore di una delle due parti — un bonifico categorizzato
male su WeBank, o un'entrata su Revolut che non viene dal conto
personale. E' la stessa idea del controllo contro l'estratto: due misure
indipendenti della stessa cosa, che devono combaciare.

Rotte HTML:
  GET  /conti/revolut/movimenti             elenco con filtri
  GET  /conti/revolut/movimenti/nuovo       form
  GET  /conti/revolut/movimenti/<id>        modifica

Rotte JSON:
  GET    /spese/api/revolut/movimenti
  POST   /spese/api/revolut/movimenti            (un movimento a mano)
  POST   /spese/api/revolut/movimenti/importa    (le righe lette dall'estratto)
  PATCH  /spese/api/revolut/movimenti/<id>
  DELETE /spese/api/revolut/movimenti/<id>
"""
import json
import re
from datetime import date, timedelta

from flask import Response, jsonify, request

from . import dati as D
from . import spese_bp
from shared.design import icon, info
from shared.fmt import data_it, eur, eur_segno
from shared.ordina import ordina, ordina_coppie
from shared import importazione as IM
from shared.theme import render_page


TABELLA = "b2f_revolut_movimenti"
MIGRAZIONE = "§8.19"

CATEGORIA_INTERNO = D.CATEGORIA_GIROCONTO_REVOLUT
CATEGORIA_INTERESSI = "Interessi"
CATEGORIA_INVESTIMENTI = "Investimenti"

# Le parti di Revolut che hanno movimenti in euro. Gli investimenti non ci
# sono apposta: il loro valore si muove col mercato, non con dei movimenti,
# e resta scritto a mano sulla fotografia (vedi spese/revolut.py).
SEZIONI = tuple(ordina_coppie([
    ("conto",    "Liquidità"),
    ("risparmi", "Risparmi (deposito)"),
]))
SEZIONI_CHIAVI = tuple(k for k, _ in SEZIONI)
SEZIONI_LABEL = dict(SEZIONI)

# Categorie che su Revolut non hanno senso: "Giroconto P.IVA" e' il
# passaggio fra i due conti WeBank, e "Stipendio" apre i periodi di
# risparmio — che si calcolano sul conto personale, non qui.
CATEGORIE_ESCLUSE = (D.CATEGORIA_GIROCONTO,)

CAMPI = ("data", "importo", "tipo", "descrizione", "categoria_link_id",
         "sezione", "note")

# Quanti giorni possono separare il bonifico che parte da WeBank da quello
# che arriva su Revolut. Un istantaneo arriva in giornata, un SEPA del
# venerdi' il lunedi', con un festivo in mezzo anche dopo.
FINESTRA_PONTE = 5


def _righe(r):
    d = getattr(r, "data", None)
    if d is None:
        return []
    return d if isinstance(d, list) else [d]


def _manca_tabella(msg: str) -> bool:
    msg = (msg or "").lower()
    return TABELLA in msg and ("does not exist" in msg or "relation" in msg
                               or "schema cache" in msg)


def avviso_migrazione() -> str:
    return (f'<div class="notice warn">I movimenti di Revolut hanno bisogno '
            f'della tabella <code>{TABELLA}</code>: esegui la migrazione '
            f'{MIGRAZIONE} documentata nel README. Fino ad allora la pagina '
            f'mostra solo le fotografie dei saldi.</div>')


# ---------------------------------------------------------------------------
# Categorie: le stesse del conto personale
# ---------------------------------------------------------------------------

def voci_categoria(client) -> list[dict]:
    """
    Gli accoppiamenti categoria/sottocategoria usabili su Revolut: gli
    stessi del conto personale (`D.voci_categoria`, gia' in ordine
    alfabetico), meno quelli che qui non hanno senso.
    """
    return [v for v in D.voci_categoria(client)
            if v["categoria"] not in CATEGORIE_ESCLUSE]


def albero_categorie(client) -> list[dict]:
    return [g for g in D.albero_categorie(client)
            if g["categoria"] not in CATEGORIE_ESCLUSE]


def _mappa_link(client) -> dict:
    """link_id -> (categoria, sottocategoria), per risolvere i nomi."""
    return {v["link_id"]: (v["categoria"], v["sottocategoria"])
            for v in D.voci_categoria(client)}


def _con_nomi(righe: list[dict], mappa: dict) -> list[dict]:
    out = []
    for r in righe:
        cat, sub = mappa.get(r.get("categoria_link_id"), (None, None))
        out.append({**r, "categoria": cat, "sottocategoria": sub})
    return out


def _link_di(client, nome: str | None):
    """Il link della categoria senza sottocategoria, o None."""
    if not nome:
        return None
    return D.link_categoria(client, nome, None)


# ---------------------------------------------------------------------------
# Lettura
# ---------------------------------------------------------------------------

def tutti(client, dal: str | None = None, al: str | None = None) -> list[dict] | None:
    """
    Tutti i movimenti Revolut, dal piu' vecchio, con i nomi di categoria.
    None se la tabella non esiste ancora (migrazione non eseguita): e'
    diverso da «nessun movimento», e chi chiama lo deve poter dire.

    Pagina con `.range()` fino in fondo: e' la stessa trappola delle 1000
    righe di README §7, e un estratto dall'apertura del conto ne ha piu'
    di mille da solo.
    """
    out: list[dict] = []
    offset, passo = 0, 1000
    while True:
        try:
            q = client.table(TABELLA).select("*")
            if dal:
                q = q.gte("data", dal)
            if al:
                q = q.lte("data", al)
            pagina = _righe(q.order("data", desc=False).order("id")
                            .range(offset, offset + passo - 1).execute())
        except Exception as e:
            return None if _manca_tabella(str(e)) else _con_nomi(out, _mappa_link(client))
        out.extend(pagina)
        if len(pagina) < passo:
            break
        offset += passo
    return _con_nomi(out, _mappa_link(client))


def filtra(righe: list[dict], anno=None, mese=None, tipo=None, categoria=None,
           sezione=None, cerca=None) -> list[dict]:
    """
    I filtri dell'elenco, applicati in Python sulle righe gia' lette.

    La categoria non e' una colonna della tabella ma un nome risolto dal
    link: filtrarla in SQL vorrebbe una vista in piu' solo per questo. Le
    righe di Revolut sono qualche migliaio al massimo, e leggerle tutte
    serve comunque ai totali — che devono contare tutto il filtrato, non
    solo le righe mostrate (la stessa regola di `D.totali_periodo`).
    `categoria="-"` vuol dire «senza categoria»: e' il filtro che serve
    per sistemare quelle da categorizzare.
    """
    out = []
    ago = (cerca or "").strip().lower()
    for r in righe:
        d = str(r.get("data") or "")
        if anno and d[:4] != str(anno):
            continue
        if mese and d[5:7] != f"{int(mese):02d}":
            continue
        if tipo and r.get("tipo") != tipo:
            continue
        if sezione and r.get("sezione") != sezione:
            continue
        if categoria == "-":
            if r.get("categoria"):
                continue
        elif categoria and r.get("categoria") != categoria:
            continue
        if ago and ago not in (r.get("descrizione") or "").lower():
            continue
        out.append(r)
    return out


def movimento(client, mid: int) -> dict | None:
    try:
        r = client.table(TABELLA).select("*").eq("id", mid).limit(1).execute()
        righe = _righe(r)
    except Exception:
        return None
    if not righe:
        return None
    return _con_nomi(righe, _mappa_link(client))[0]


def interno(r: dict) -> bool:
    """Un passaggio fra liquidita' e deposito: non entra ne' esce da Revolut."""
    return r.get("categoria") == CATEGORIA_INTERNO


def totali(righe: list[dict]) -> dict:
    """
    Entrate e uscite **vere** di Revolut, piu' le voci che servono a
    leggerle.

    I giroconti interni restano fuori da entrate e uscite, come sul conto
    P.IVA restano fuori i giroconti verso il personale: sono lo stesso
    euro visto due volte (esce dalla liquidita', entra nel deposito), e
    contarli gonfierebbe entrambi i totali del doppio di ogni spostamento.
    Restano pero' nel saldo, perche' il saldo e' per sezione e li' si
    muovono davvero.

    `dal_webank` e' il netto dei Risparmi: quanto e' arrivato dal conto
    personale meno quanto e' tornato indietro. E' lo stesso numero che
    `D.risparmio_totale` misura dall'altra parte del bonifico.
    """
    t = {"entrate": 0.0, "uscite": 0.0, "interni": 0.0, "dal_webank": 0.0,
         "interessi": 0.0, "da_categorizzare": 0, "n": len(righe)}
    for r in righe:
        imp = abs(float(r.get("importo") or 0))
        entra = r.get("tipo") == "entrata"
        cat = r.get("categoria")
        if not cat:
            t["da_categorizzare"] += 1
        if interno(r):
            if entra:
                t["interni"] += imp
            continue
        if entra:
            t["entrate"] += imp
        else:
            t["uscite"] += imp
        if cat == D.CATEGORIA_RISPARMIO:
            t["dal_webank"] += imp if entra else -imp
        elif cat == CATEGORIA_INTERESSI:
            t["interessi"] += imp if entra else -imp
    for k in ("entrate", "uscite", "interni", "dal_webank", "interessi"):
        t[k] = round(t[k], 2)
    t["saldo"] = round(t["entrate"] - t["uscite"], 2)
    return t


def per_categoria(righe: list[dict], tipo: str) -> list[dict]:
    """Come `D.per_categoria`, senza i giroconti interni."""
    return D.per_categoria([r for r in righe if not interno(r)], tipo)


def dopo_la_fotografia(client, dal: str, al: str) -> dict | None:
    """
    Quanto si e' mosso ogni sezione **dopo** la data della fotografia,
    fino a `al` compreso. La fotografia e' il saldo di fine giornata:
    i movimenti di quello stesso giorno ci sono gia' dentro.

    None se la tabella non c'e': chi chiama tiene la fotografia com'e'.
    """
    try:
        inizio = (date.fromisoformat(dal[:10]) + timedelta(days=1)).isoformat()
    except (TypeError, ValueError):
        return None
    if inizio > al:
        return {"conto": 0.0, "risparmi": 0.0, "n": 0}
    righe = tutti(client, inizio, al)
    if righe is None:
        return None
    mosso = {"conto": 0.0, "risparmi": 0.0, "n": 0}
    for r in righe:
        sez = r.get("sezione") if r.get("sezione") in SEZIONI_CHIAVI else "conto"
        imp = abs(float(r.get("importo") or 0))
        mosso[sez] += imp if r.get("tipo") == "entrata" else -imp
        mosso["n"] += 1
    mosso["conto"] = round(mosso["conto"], 2)
    mosso["risparmi"] = round(mosso["risparmi"], 2)
    return mosso


# ---------------------------------------------------------------------------
# Il ponte con WeBank: i bonifici Risparmi visti dalle due parti
# ---------------------------------------------------------------------------

def _giorno(r) -> date | None:
    try:
        return date.fromisoformat(str(r.get("data") or "")[:10])
    except ValueError:
        return None


def abbina(webank: list[dict], revolut: list[dict]) -> dict:
    """
    Appaia i bonifici fra i due conti: un'uscita WeBank con un'entrata
    Revolut dello **stesso importo** arrivata fra il giorno prima e
    `FINESTRA_PONTE` giorni dopo; e al contrario per i rientri (uscita
    Revolut, entrata WeBank).

    Ogni riga si usa una volta sola, e si scorre in ordine di data: due
    bonifici identici da 770,98 a un mese di distanza vanno ciascuno col
    suo, non entrambi col primo. Non guarda le descrizioni — dicono cose
    diverse sui due estratti — e non guarda le categorie di Revolut: e'
    proprio quello che deve poter suggerire.
    """
    presi: set = set()
    coppie, sole_webank = [], []
    for w in sorted(webank, key=lambda x: str(x.get("data") or "")):
        gw = _giorno(w)
        if gw is None:
            continue
        verso = "entrata" if w.get("tipo") == "uscita" else "uscita"
        imp = round(abs(float(w.get("importo") or 0)), 2)
        trovata = None
        for r in sorted(revolut, key=lambda x: str(x.get("data") or "")):
            chiave = r.get("id") or r.get("chiave")
            if chiave in presi or r.get("tipo") != verso:
                continue
            if abs(round(abs(float(r.get("importo") or 0)), 2) - imp) >= 0.01:
                continue
            gr = _giorno(r)
            if gr is None:
                continue
            scarto = (gr - gw).days if verso == "entrata" else (gw - gr).days
            if -1 <= scarto <= FINESTRA_PONTE:
                trovata = r
                break
        if trovata is not None:
            presi.add(trovata.get("id") or trovata.get("chiave"))
            coppie.append((w, trovata))
        else:
            sole_webank.append(w)
    sole_revolut = [r for r in revolut
                    if (r.get("id") or r.get("chiave")) not in presi]
    return {"coppie": coppie, "sole_webank": sole_webank,
            "sole_revolut": sole_revolut}


def risparmi_webank(client, dal: str, al: str) -> list[dict]:
    """Le righe Risparmi del conto personale in un intervallo, paginate."""
    out, offset, passo = [], 0, 1000
    while True:
        try:
            pagina = _righe(client.table("v_spese")
                            .select("id,data,tipo,importo,descrizione,categoria")
                            .eq("categoria", D.CATEGORIA_RISPARMIO)
                            .gte("data", dal).lte("data", al)
                            .order("data", desc=False).order("id")
                            .range(offset, offset + passo - 1).execute())
        except Exception:
            return out
        out.extend(pagina)
        if len(pagina) < passo:
            return out
        offset += passo


def ponte(client, righe: list[dict] | None = None) -> dict | None:
    """
    Il confronto fra i bonifici Risparmi di WeBank e i movimenti Risparmi
    di Revolut, sull'intervallo coperto dai movimenti Revolut.

    Solo su quell'intervallo: prima del primo movimento importato Revolut
    non sa niente, e ogni bonifico WeBank di allora risulterebbe «senza
    contropartita» senza esserlo. None se non ci sono movimenti.
    """
    if righe is None:
        righe = tutti(client)
    if not righe:
        return None
    dal = str(righe[0].get("data"))[:10]
    al = str(righe[-1].get("data"))[:10]
    webank = risparmi_webank(client, dal, al)
    rev = [r for r in righe if r.get("categoria") == D.CATEGORIA_RISPARMIO]
    esito = abbina(webank, rev)
    esito.update({"dal": dal, "al": al, "webank": len(webank), "revolut": len(rev)})
    return esito


# ---------------------------------------------------------------------------
# Suggerimento della categoria, all'import
# ---------------------------------------------------------------------------

# Le descrizioni che l'estratto Revolut usa davvero (consolidato del
# 27/09/2026, 976 movimenti), per le tre categorie che sono fatti del
# conto e non abitudini di spesa.
_INTERESSI = re.compile(r"interess|interest|ritenuta|withholding", re.I)
_INVESTIMENTI = re.compile(r"investiment|investment|portfolio|trading|broker|"
                           r"\brobo\b|azioni|stock|cripto|crypto", re.I)
# Soldi che si spostano fra le parti di Revolut: dal conto a un salvadanaio
# («Accredita EUR Emergenze da EUR», «A EUR Casa»), indietro («Prelievo da
# Pocket», «Da EUR Vacanze»), fra valute («Conversione in JPY»), o il
# trasloco del conto in un'altra entita' Revolut («Balance migration…»,
# aprile 2026: esce e rientra lo stesso importo, lo stesso giorno).
_INTERNI = re.compile(r"accredita\s+eur|prelievo da pocket|^\s*(a|da)\s+eur\b|"
                      r"conversione in [a-z]{3}\b|deposito senza vincoli|balance migration|"
                      r"\bpocket\b|\bvault\b|conto di risparmio|savings", re.I)


def _interno(mov: dict) -> bool:
    """Uno spostamento fra le parti di Revolut: non entra ne' esce niente."""
    return (bool(_INTERNI.search(mov.get("descrizione") or ""))
            or (mov.get("categoria_banca") or "").lower() in ("cambio valuta", "cambia valuta"))


def suggerisci(mov: dict, gemella: bool = False) -> str | None:
    """
    La categoria che l'import propone per una riga dell'estratto, quando
    e' un FATTO del conto e non una scelta: il resto lo propone lo storico
    (shared/suggerimenti.py), e quello che nemmeno lo storico conosce
    resta da scegliere.

    1. **la gemella su WeBank**: un bonifico «Risparmi» dello stesso
       importo nei giorni giusti — questa riga e' la sua altra meta'.
    2. **gli interessi** del deposito.
    3. **gli investimenti**: «Al conto di investimento», «To Robo portfolio».
    4. **i giroconti interni**: conto ↔ salvadanai, cambi di valuta.

    Una spesa pagata DA un salvadanaio (un volo dalle «Vacanze») non e' un
    giroconto: esce da Revolut davvero. Per questo la sezione da sola non
    decide piu' niente — decidono le parole e la categoria che Revolut
    stessa assegna («Esercente», «Cambio valuta»).
    """
    if gemella:
        return D.CATEGORIA_RISPARMIO
    desc = (mov.get("descrizione") or "")
    banca = (mov.get("categoria_banca") or "").lower()
    if _INTERESSI.search(desc):
        return CATEGORIA_INTERESSI
    if banca == "esercente":
        return None
    if _INVESTIMENTI.search(desc):
        return CATEGORIA_INVESTIMENTI
    if banca == "cambio valuta" or _INTERNI.search(desc):
        return CATEGORIA_INTERNO
    return None


def voci_pannello(client) -> list[dict]:
    """Le categorie di Revolut per il pannello di import comune."""
    return ordina([{"valore": v["link_id"],
                    "nome": v["categoria"] + (f' › {v["sottocategoria"]}'
                                              if v["sottocategoria"] else "")}
                   for v in voci_categoria(client)], per=lambda v: v["nome"])


def prepara_import(client, letti: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Le righe dell'estratto pronte per il pannello di revisione comune
    (shared/importazione.py), piu' gli avvisi da mostrare sopra.

    La categoria arriva da due fonti, in quest'ordine:
      1. i **fatti** di `suggerisci()` — la gemella su WeBank, la sezione
         deposito, le parole degli interessi: valgono piu' dello storico;
      2. lo **storico** dei movimenti gia' categorizzati, di WeBank e di
         Revolut insieme (`shared/suggerimenti.py`): la pizzeria sotto
         casa e' la stessa qualunque carta si usi.

    `presente` sono le righe con un'impronta gia' salvata da un import
    precedente; `sospetto` quelle che somigliano a un movimento scritto a
    mano (che un'impronta non ce l'ha).
    """
    from shared import importazione as IM
    from shared import suggerimenti as SG
    if not letti:
        return [], []
    dal = min(m["data"] for m in letti)
    al = max(m["data"] for m in letti)
    try:
        dal_w = (date.fromisoformat(dal) - timedelta(days=FINESTRA_PONTE)).isoformat()
        al_w = (date.fromisoformat(al) + timedelta(days=1)).isoformat()
    except ValueError:
        dal_w, al_w = dal, al
    # Solo i movimenti che escono o entrano davvero da Revolut possono essere
    # l'altra meta' di un bonifico WeBank. Il 03/08/2026 il prelievo «Da
    # EUR Emergenze» (salvadanaio → conto, 150) si e' preso la gemella del
    # bonifico vero «To Emanuele Bellotti» (conto → WeBank, 150, stesso
    # giorno): il prelievo e' finito in Risparmi e il bonifico in Hype, e
    # quei 150 risultavano usciti due volte.
    esito = abbina(risparmi_webank(client, dal_w, al_w),
                   [m for m in letti if not _interno(m)])
    gemelle = {r.get("chiave") for _w, r in esito["coppie"]}
    presenti = chiavi_presenti(client, [m["chiave"] for m in letti])

    link: dict[str, object] = {}
    out = []
    for m in letti:
        nome = suggerisci(m, m.get("chiave") in gemelle)
        if nome and nome not in link:
            link[nome] = _link_di(client, nome)
        riga = {**m, "categoria": link.get(nome), "gemella": m.get("chiave") in gemelle}
        if riga["gemella"]:
            riga["nota"] = "ha il suo bonifico «Risparmi» su WeBank"
        if m.get("chiave") in presenti:
            riga["presente"] = True
            riga["nota"] = "già registrato da un estratto precedente"
        out.append(riga)

    avvisi = []
    nuove = [r for r in out if not r.get("presente")]
    # Chi non ha l'impronta uguale si confronta con tutto quello che e'
    # gia' salvato e non e' stato riconosciuto: i movimenti scritti a mano
    # e quelli di un estratto nell'ALTRO formato. Il consolidato e l'export
    # dei movimenti chiamano lo stesso bonifico in due modi («Pagamento da
    # parte di MARIO ROSSI» / «Revolut Bank UAB»): stessa data, stesso
    # importo, due impronte. Sezione per sezione, perche' il versamento al
    # deposito esce dal conto ed entra nel deposito lo stesso giorno.
    riconosciute = {m.get("chiave") for m in letti} & presenti
    salvati = [r for r in (tutti(client, dal_w, al_w) or [])
               if r.get("chiave") not in riconosciute]
    for sezione in SEZIONI_CHIAVI:
        esistenti = [r for r in salvati if (r.get("sezione") or "conto") == sezione]
        if esistenti:
            IM.segna_doppioni(esistenti,
                              [r for r in nuove if (r.get("sezione") or "conto") == sezione])
    nuove = [r for r in nuove if not r.get("presente")]
    ammesse = {v["valore"] for v in voci_pannello(client)}
    proposte = IM.proponi(SG.storico_personale(client), nuove, ammesse)
    storni = IM.accoppia_storni(out, salvati)
    n_presenti = len(out) - len(nuove)
    if n_presenti:
        avvisi.append({"testo": f"{n_presenti} movimenti erano già registrati "
                                f"(da un estratto precedente o a mano): restano come sono."})
    if gemelle:
        avvisi.append({"testo": f"{len(gemelle)} entrate hanno il loro bonifico «Risparmi» "
                                f"su WeBank, e sono già categorizzate così."})
    if proposte:
        avvisi.append({"testo": f"{proposte} righe hanno la categoria proposta dallo storico."})
    if storni:
        avvisi.append({"testo": f"{storni} rimborsi hanno la categoria della spesa "
                                f"che annullano."})
    return out, avvisi


# ---------------------------------------------------------------------------
# Scrittura
# ---------------------------------------------------------------------------

def chiavi_presenti(client, chiavi: list[str]) -> set:
    """Le impronte gia' salvate, fra quelle date. A blocchi: l'URL ha un limite."""
    trovate: set = set()
    chiavi = [c for c in chiavi if c]
    for i in range(0, len(chiavi), 200):
        try:
            r = (client.table(TABELLA).select("chiave")
                 .in_("chiave", chiavi[i:i + 200]).execute())
        except Exception:
            continue
        trovate.update(x.get("chiave") for x in _righe(r))
    return trovate


def _normalizza(dati: dict) -> tuple[dict, str | None]:
    """Il movimento ripulito, o un errore da mostrare."""
    out = {}
    for k in CAMPI:
        if k not in dati:
            continue
        v = dati[k]
        if isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    if "data" in out:
        try:
            out["data"] = date.fromisoformat(str(out["data"])[:10]).isoformat()
        except (TypeError, ValueError):
            return {}, "data non valida"
    if "importo" in out:
        try:
            # Sempre positivo: la direzione la da' `tipo`, come sugli
            # altri due conti.
            out["importo"] = round(abs(float(out["importo"])), 2)
        except (TypeError, ValueError):
            return {}, "importo non valido"
        if not out["importo"]:
            return {}, "importo mancante"
    if "tipo" in out and out["tipo"] not in D.TIPI_CHIAVI:
        return {}, "tipo non valido: entrata o uscita"
    if "sezione" in out and out["sezione"] is None:
        del out["sezione"]
    if "sezione" in out and out["sezione"] not in SEZIONI_CHIAVI:
        return {}, "sezione non valida"
    if "descrizione" in out:
        out["descrizione"] = (out["descrizione"] or "")[:200]
    return out, None


def _errore(e: Exception) -> str:
    msg = str(e)
    if _manca_tabella(msg):
        return (f"Manca la tabella {TABELLA}: esegui la migrazione {MIGRAZIONE} "
                "documentata nel README.")
    return msg[:200]


def crea(client, dati: dict) -> dict:
    d, err = _normalizza(dati)
    if err:
        return {"error": err}
    for k in ("data", "importo", "tipo"):
        if not d.get(k):
            return {"error": f"{k} mancante"}
    d.setdefault("sezione", "conto")
    d.setdefault("descrizione", "")
    d["fonte"] = "manuale"
    try:
        r = client.table(TABELLA).insert(d).execute()
        righe = _righe(r)
        return {"id": righe[0].get("id") if righe else None}
    except Exception as e:
        return {"error": _errore(e)}


# Come Revolut chiama oggi i salvadanai nelle descrizioni del deposito
# («A EUR Casa»): le stesse parole, cosi' al prossimo estratto questi
# movimenti scritti dalla procedura risultano gia' registrati.
NOMI_DEPOSITO = {"casa": "Casa", "emergenze": "Emergenze", "vacanze": "Vacanze",
                 "regali": "Regali"}
DA_WEBANK = "Pagamento da BELLOTTI EMANUELE"


def ripartizione(importo: float, percentuali: dict) -> dict:
    """
    Come si divide un bonifico ai salvadanai: la quota di ogni salvadanaio
    (importo × percentuale, al centesimo) e il resto, che non va in un
    salvadanaio ma negli investimenti e intanto resta in liquidita'.
    """
    from .revolut import SALVADANAI
    quote = {}
    for chiave, _rev, _app, campo_perc, _col, _alias in SALVADANAI:
        if chiave not in NOMI_DEPOSITO:
            continue
        try:
            p = float(percentuali.get(campo_perc) or 0)
        except (TypeError, ValueError):
            p = 0.0
        q = round(importo * p, 2)
        if q > 0:
            quote[chiave] = q
    return {"quote": quote, "resto": round(importo - sum(quote.values()), 2)}


def registra_risparmio(client, importo: float, quando: str, percentuali: dict) -> dict:
    """
    Il lato Revolut del bonifico ai salvadanai, come succede davvero: il
    bonifico arriva sul conto («Risparmi», l'altra meta' dell'uscita
    WeBank), e da li' ogni quota passa nel suo salvadanaio (due righe per
    quota, conto → deposito, «Giroconto Revolut»). Il resto — la quota
    degli investimenti — resta in liquidita' finche' non lo sposti: quello
    arriva con l'estratto («Al conto di investimento»).

    Senza questo la procedura scriveva solo WeBank: i soldi risultavano
    usciti dal personale e mai arrivati, e i salvadanai dell'app restavano
    fermi all'ultima fotografia.
    """
    try:
        importo = round(abs(float(importo)), 2)
    except (TypeError, ValueError):
        return {"error": "importo non valido"}
    rip = ripartizione(importo, percentuali)
    risparmio = _link_di(client, D.CATEGORIA_RISPARMIO)
    interno = _link_di(client, CATEGORIA_INTERNO)
    nota = "registrato dalla procedura di fine periodo"
    righe = [{"data": quando, "tipo": "entrata", "importo": importo, "sezione": "conto",
              "descrizione": DA_WEBANK, "categoria_link_id": risparmio, "note": nota}]
    for chiave, q in rip["quote"].items():
        desc = f"A EUR {NOMI_DEPOSITO[chiave]}"
        righe.append({"data": quando, "tipo": "uscita", "importo": q, "sezione": "conto",
                      "descrizione": desc, "categoria_link_id": interno, "note": nota})
        righe.append({"data": quando, "tipo": "entrata", "importo": q, "sezione": "risparmi",
                      "descrizione": desc, "categoria_link_id": interno, "note": nota})
    pulite = []
    for r in righe:
        d, err = _normalizza(r)
        if err:
            return {"error": err}
        d["fonte"] = "manuale"
        pulite.append(d)
    try:
        client.table(TABELLA).insert(pulite).execute()
    except Exception as e:
        return {"error": _errore(e)}
    esito = {"righe": len(pulite), **rip}
    # Una fotografia con la stessa data e' il saldo di fine giornata: i
    # movimenti di quel giorno si considerano gia' dentro, e questi non
    # sposterebbero niente. Va detto, non taciuto.
    try:
        foto = _righe(client.table("b2f_revolut").select("data").eq("data", quando).execute())
    except Exception:
        foto = []
    if foto:
        esito["avviso"] = (f"C'è già una fotografia Revolut del {quando[8:10]}/{quando[5:7]}: "
                           "i movimenti di quel giorno si considerano già dentro. "
                           "Aggiornala con i saldi di fine giornata.")
    return esito


def aggiorna(client, mid: int, dati: dict) -> dict:
    d, err = _normalizza(dati)
    if err:
        return {"error": err}
    if not d:
        return {"error": "nessun campo da aggiornare"}
    try:
        client.table(TABELLA).update(d).eq("id", mid).execute()
        return {"id": mid}
    except Exception as e:
        return {"error": _errore(e)}


def elimina(client, mid: int) -> dict:
    try:
        client.table(TABELLA).delete().eq("id", mid).execute()
        return {"ok": True}
    except Exception as e:
        return {"error": _errore(e)}


def importa(client, righe: list) -> dict:
    """
    Salva le righe lette dall'estratto, nella forma del pannello comune:
    ogni riga ha `idx` (la sua posizione nel pannello), `chiave`, e la
    categoria in `categoria` (il link `cfg_*`). Ritorna {salvate: [idx],
    duplicati: [{idx, nota}], errori: [{idx, errore}]}, come l'import WeBank.

    Quelle con un'impronta gia' presente si saltano **senza toccarle**:
    reimportare un estratto che si sovrappone al precedente non deve
    rimettere la categoria proposta su una riga che nel frattempo hai
    corretto a mano.
    """
    if not isinstance(righe, list) or not righe:
        return {"error": "nessuna riga da salvare"}
    validi = {v["link_id"] for v in voci_categoria(client)}
    pulite, errori = [], []
    for n, x in enumerate(righe):
        if not isinstance(x, dict):
            continue
        idx = x.get("idx", n)
        if not x.get("chiave"):
            errori.append({"idx": idx, "errore": "riga senza impronta"})
            continue
        x = dict(x)
        if "categoria" in x and "categoria_link_id" not in x:
            x["categoria_link_id"] = x.get("categoria")
        d, err = _normalizza(x)
        if err or not d.get("data") or not d.get("importo") or not d.get("tipo"):
            errori.append({"idx": idx, "errore": err or "data, importo o tipo mancanti"})
            continue
        if d.get("categoria_link_id") and d["categoria_link_id"] not in validi:
            errori.append({"idx": idx, "errore": "categoria non valida"})
            continue
        d.setdefault("sezione", "conto")
        if not d.get("sezione"):
            d["sezione"] = "conto"
        d.setdefault("descrizione", "")
        d["chiave"] = str(x["chiave"])[:64]
        d["fonte"] = "estratto"
        pulite.append((idx, d))

    gia = chiavi_presenti(client, [d["chiave"] for _i, d in pulite])
    duplicati, nuove, viste = [], [], set()
    for idx, d in pulite:
        # Anche dentro lo stesso invio: una chiave ripetuta due volte e'
        # lo stesso movimento spedito due volte, non due movimenti.
        if d["chiave"] in gia or d["chiave"] in viste:
            duplicati.append({"idx": idx, "nota": "già registrato"})
            continue
        viste.add(d["chiave"])
        nuove.append((idx, d))

    salvate = []
    for i in range(0, len(nuove), 200):
        blocco = nuove[i:i + 200]
        try:
            client.table(TABELLA).insert([d for _i, d in blocco]).execute()
            salvate.extend(idx for idx, _d in blocco)
        except Exception as e:
            return {"error": _errore(e), "salvate": salvate,
                    "duplicati": duplicati, "errori": errori}
    return {"ok": True, "salvate": salvate, "duplicati": duplicati, "errori": errori,
            "inseriti": len(salvate), "gia_presenti": len(duplicati),
            "scartate": len(errori)}


# ---------------------------------------------------------------------------
# Pezzi di pagina, usati anche da /conti/revolut
# ---------------------------------------------------------------------------

def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;") \
        .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def riga_html(m: dict) -> str:
    """Una riga dell'elenco, nella stessa forma di quelle del personale."""
    entra = m.get("tipo") == "entrata"
    imp = abs(float(m.get("importo") or 0))
    cat = m.get("categoria")
    etichetta = (cat + (f' · {m["sottocategoria"]}' if m.get("sottocategoria") else "")
                 if cat else "")
    sez = SEZIONI_LABEL.get(m.get("sezione"), "")
    marchi = ""
    if not cat:
        marchi = '<span class="chip warn">da categorizzare</span>'
    elif interno(m):
        marchi = '<span class="chip">interno</span>'
    cls = "" if interno(m) else ("pos" if entra else "neg")
    return f'''
    <a class="item" href="/conti/revolut/movimenti/{m.get("id")}">
      <span class="body">
        <span class="n">{_esc((m.get("descrizione") or "—")[:60])}</span>
        <span class="m">{data_it(m.get("data"))} · {_esc(etichetta or "senza categoria")} · {_esc(sez)}</span>
      </span>
      <span class="end">
        <span class="amt tnum {cls}">{eur_segno(imp if entra else -imp)}</span>
        {marchi}
      </span>
    </a>'''


def card_ponte(p: dict | None) -> str:
    """Il confronto dei bonifici Risparmi fra WeBank e Revolut."""
    if not p:
        return ""
    sw, sr = p["sole_webank"], p["sole_revolut"]
    ok = not sw and not sr

    def riga(r, dove):
        entra = r.get("tipo") == "entrata"
        imp = abs(float(r.get("importo") or 0))
        return f'''
        <div class="row"><span class="t">{_esc((r.get("descrizione") or "—")[:50])}
          <span class="sub">{dove} · {data_it(r.get("data"))}</span></span>
          <span class="v tnum">{eur_segno(imp if entra else -imp)}</span></div>'''

    righe = "".join(riga(r, "solo su WeBank") for r in sw[:12])
    righe += "".join(riga(r, "solo su Revolut") for r in sr[:12])
    spiega = (f'Dal {data_it(p["dal"])} al {data_it(p["al"])} ogni bonifico «Risparmi» '
              f'uscito da WeBank ha la sua entrata su Revolut, e viceversa: '
              f'{len(p["coppie"])} coppie, nessuna riga spaiata.' if ok else
              f'Dal {data_it(p["dal"])} al {data_it(p["al"])}: {len(p["coppie"])} coppie '
              f'trovate, {len(sw)} bonifici WeBank senza l\'entrata su Revolut e '
              f'{len(sr)} movimenti Revolut «Risparmi» senza il bonifico WeBank. '
              f'Di solito è una categoria sbagliata su uno dei due lati, o un '
              f'importo diverso di qualche centesimo.')
    return f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">Il ponte con WeBank
          {info("Ogni bonifico verso i salvadanai &egrave; una riga su WeBank "
                "(uscita, categoria Risparmi) e una su Revolut (entrata, stessa "
                "categoria). Sono due misure indipendenti dello stesso euro: le "
                "appaio per importo, con qualche giorno di tolleranza sulla data. "
                "Quello che resta spaiato &egrave; un errore di una delle due parti.")}</div>
        <span class="chip {"pos" if ok else "warn"}">{"combacia" if ok else "da guardare"}</span>
      </div>
      <p class="small muted">{spiega}</p>
      {f'<div class="rows detail mt-2">{righe}</div>' if righe else ""}
    </div>'''


# ---------------------------------------------------------------------------
# Pagine
# ---------------------------------------------------------------------------

MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def _render(content: str, eyebrow: str, titolo: str, breadcrumb=None,
            fab=None) -> Response:
    return Response(render_page(section="conti-revolut", eyebrow=eyebrow,
                                title_html=titolo, content=content,
                                breadcrumb=breadcrumb, fab=fab),
                    mimetype="text/html")


@spese_bp.get("/conti/revolut/movimenti")
def revolut_movimenti_lista():
    breadcrumb = [("Conti", "/conti"), ("Revolut", "/conti/revolut"),
                  ("Movimenti", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       "Revolut", 'Movimenti <em>Revolut</em>', breadcrumb)
    tutte = tutti(client)
    if tutte is None:
        return _render(avviso_migrazione(), "Revolut",
                       'Movimenti <em>Revolut</em>', breadcrumb)

    anni = sorted({int(str(r.get("data"))[:4]) for r in tutte if r.get("data")},
                  reverse=True)
    # anno=0 vuol dire «tutti gli anni»: serve soprattutto per trovare
    # le righe ancora da categorizzare, che un import dall'apertura del
    # conto sparge su due o tre anni.
    anno_arg = request.args.get("anno", type=int)
    if anno_arg == 0:
        anno = None
    else:
        anno = anno_arg or (anni[0] if anni else date.today().year)
        if anno not in anni:
            anni = sorted(set(anni + [anno]), reverse=True)
    mese = request.args.get("mese", type=int) or 0
    tipo = request.args.get("tipo") or ""
    categoria = request.args.get("categoria") or ""
    sezione = request.args.get("sezione") or ""
    cerca = (request.args.get("q") or "").strip()

    righe = filtra(tutte, anno=anno, mese=mese or None, tipo=tipo or None,
                   categoria=categoria or None, sezione=sezione or None,
                   cerca=cerca or None)
    t = totali(righe)
    categorie = ordina({v["categoria"] for v in voci_categoria(client)})

    def opzioni(valori, corrente, vuota, icone=None):
        icone = icone or {}
        out = [f'<option value="">{vuota}</option>']
        for val, lbl in valori:
            sel = " selected" if str(val) == str(corrente) else ""
            ic = f' data-icona="{icone[val]}"' if val in icone else ""
            out.append(f'<option value="{_esc(val)}"{sel}{ic}>{_esc(lbl)}</option>')
        return "".join(out)

    toolbar = f'''
    <div class="toolbar">
      <select class="select-pill" aria-label="Anno" data-etichetta="Anno"
              data-icona="📆" onchange="filtra('anno', this.value)">
        {"".join(f'<option value="{a}"{" selected" if a == anno else ""}>{a}</option>' for a in anni)}
        <option value="0"{" selected" if anno is None else ""}>Tutti gli anni</option>
      </select>
      <select class="select-pill" aria-label="Mese" data-etichetta="Mese"
              data-icona="🗓️" onchange="filtra('mese', this.value)">
        {opzioni([(i + 1, MESI[i]) for i in range(12)], mese or "", "Tutto l'anno")}
      </select>
      <select class="select-pill" aria-label="Tipo" data-etichetta="Tipo di movimento"
              data-icona="↕️" onchange="filtra('tipo', this.value)">
        {opzioni(D.TIPI, tipo, "Tutti i tipi", {"entrata": "🟢", "uscita": "🔴"})}
      </select>
      <select class="select-pill" aria-label="Categoria" data-etichetta="Categoria"
              data-icona="🏷️" onchange="filtra('categoria', this.value)">
        {opzioni([(c, c) for c in categorie] + [("-", "— senza categoria —")],
                 categoria, "Tutte le categorie")}
      </select>
      <select class="select-pill" aria-label="Sezione" data-etichetta="Parte del conto"
              data-icona="🏦" onchange="filtra('sezione', this.value)">
        {opzioni(SEZIONI, sezione, "Tutto il conto")}
      </select>
      <input class="select-pill" style="min-width:150px" placeholder="Cerca…"
             value="{_esc(cerca)}" onchange="filtra('q', this.value)">
      <a class="btn ghost" href="/conti/revolut/importa">{icon("download")}Importa da banca</a>
    </div>'''

    da_cat = ""
    if t["da_categorizzare"]:
        da_cat = f'''
      <div class="card"><div class="stat sm clickable"
           onclick="location.href='/conti/revolut/movimenti?anno={anno or 0}&amp;categoria=-'">
        <div class="val tnum warn">{t["da_categorizzare"]}</div>
        <div class="lbl">Da categorizzare</div>
        <div class="hint">mostrali ›</div></div></div>'''

    kpi = f'''
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat">
        <div class="val tnum {"pos" if t["saldo"] >= 0 else "neg"}">€ {eur_segno(t["saldo"], 0)}</div>
        <div class="lbl">Netto del periodo</div>
        <div class="hint">{t["n"]} movimenti · senza i giroconti interni</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum pos">€ {eur(t["entrate"], 0)}</div>
        <div class="lbl">Entrate</div>
        <div class="hint">di cui € {eur(t["dal_webank"], 0)} netti da WeBank</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum neg">€ {eur(t["uscite"], 0)}</div>
        <div class="lbl">Uscite</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum">€ {eur(t["interni"], 0)}</div>
        <div class="lbl">Spostati nel deposito</div>
        <div class="hint">giroconti interni, fuori dai totali</div></div></div>
      {da_cat}
    </div>'''

    if righe:
        elenco = "".join(riga_html(m) for m in reversed(righe[-300:]))
        corpo = f'<div class="list">{elenco}</div>'
        if len(righe) > 300:
            corpo += (f'<p class="small muted mt-2">Mostrati i 300 più recenti su '
                      f'{len(righe)}: i totali qui sopra li contano tutti.</p>')
    else:
        corpo = f'''<div class="empty">{icon("wallet")}
          <div class="t">Nessun movimento</div>
          <div class="s">Nessun risultato per i filtri scelti. I movimenti
            arrivano dall'estratto consolidato: si caricano da
            <a href="/conti/revolut">Revolut</a>.</div></div>'''

    def ripartizione(tipo_r, titolo):
        quote = per_categoria(righe, tipo_r)[:8]
        if not quote:
            return ""
        voci = "".join(f'''
          <div class="row"><span class="t">{_esc(q["categoria"])}
            <span class="sub">{q["quota"] * 100:.1f}% delle {titolo.lower()}</span></span>
            <span class="v tnum">€ {eur(q["importo"])}</span></div>''' for q in quote)
        return f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">{titolo} per categoria</div></div>
          <div class="rows detail">{voci}</div>
        </div>'''

    body = f'''
    {kpi}{toolbar}
    <div class="grid split">
      <div class="stack">{corpo}</div>
      <div class="stack">
        {ripartizione("entrata", "Entrate")}
        {ripartizione("uscita", "Uscite")}
      </div>
    </div>
    <script>
      function filtra(chiave, valore) {{
        const u = new URL(location.href);
        if (valore) u.searchParams.set(chiave, valore);
        else u.searchParams.delete(chiave);
        location.href = u;
      }}
    </script>'''
    return _render(body, f"Revolut {anno or 'tutti gli anni'}", 'Movimenti <em>Revolut</em>',
                   breadcrumb, fab=("Nuovo movimento", "/conti/revolut/movimenti/nuovo"))


def _form(client, m: dict | None = None) -> str:
    m = m or {}
    mid = m.get("id")
    albero = albero_categorie(client)
    cat_corrente = m.get("categoria") or ""
    tipo_corrente = m.get("tipo") or "uscita"
    sez_corrente = m.get("sezione") or "conto"
    cat_opts = "".join(
        f'<option value="{_esc(g["categoria"])}"'
        f'{" selected" if g["categoria"] == cat_corrente else ""}>'
        f'{_esc(g["categoria"])}</option>' for g in albero)
    da_estratto = m.get("fonte") == "estratto"
    avviso = ""
    if da_estratto:
        avviso = ('<div class="notice info mb-4">Letto dall\'estratto Revolut: data, '
                  'importo e direzione sono quelli della banca. Qui si sceglie la '
                  'categoria; se cambi i numeri, il prossimo import dello stesso '
                  'periodo non lo riconoscerà più come già presente.</div>')

    return f'''
    <div class="narrow">
    {avviso}
    <div class="card">
      <div class="field-group">
        <div class="field"><label>Data</label>
          <input type="date" id="f_data" value="{_esc(m.get("data") or date.today().isoformat())}"></div>
        <div class="field"><label>Importo (€)</label>
          <input type="number" step="0.01" min="0" inputmode="decimal" id="f_importo"
                 value="{abs(float(m.get("importo") or 0)) or ""}"></div>
      </div>
      <div class="field-group">
        <div class="field"><label>Tipo</label>
          <select id="f_tipo" data-etichetta="Tipo di movimento" data-icona="↕️">
            {"".join(f'<option value="{k}"{" selected" if k == tipo_corrente else ""}'
                     f' data-icona="{"🟢" if k == "entrata" else "🔴"}">{lbl}</option>'
                     for k, lbl in D.TIPI)}
          </select>
          <div class="hint">L'importo è sempre positivo: la direzione la dà il tipo.</div></div>
        <div class="field"><label>Parte del conto</label>
          <select id="f_sezione" data-etichetta="Parte del conto" data-icona="🏦">
            {"".join(f'<option value="{k}"{" selected" if k == sez_corrente else ""}>{lbl}</option>'
                     for k, lbl in SEZIONI)}
          </select></div>
      </div>
      <div class="field"><label>Descrizione</label>
        <input id="f_descrizione" value="{_esc(m.get("descrizione"))}"></div>
      <div class="field-group">
        <div class="field"><label>Categoria</label>
          <select id="f_categoria" data-etichetta="Categoria" data-icona="🏷️"
                  onchange="aggiornaSub()">
            <option value="">—</option>{cat_opts}
          </select>
          <div class="hint">Le stesse categorie del conto personale.
            «{CATEGORIA_INTERNO}» per gli spostamenti fra liquidità e deposito,
            «{D.CATEGORIA_RISPARMIO}» per i bonifici da e verso WeBank.</div></div>
        <div class="field"><label>Sottocategoria</label>
          <select id="f_sottocategoria" data-etichetta="Sottocategoria"
                  data-icona="🔖"><option value="">—</option></select></div>
      </div>
      <div class="field"><label>Note</label>
        <textarea id="f_note">{_esc(m.get("note"))}</textarea></div>
      <div class="actions">
        <button type="button" class="btn" onclick="onSalva()">{"Aggiorna" if mid else "Registra movimento"}</button>
        {'<button type="button" class="btn danger" onclick="onElimina()">Elimina</button>' if mid else ""}
        <a class="btn ghost" href="/conti/revolut/movimenti">Annulla</a>
      </div>
    </div>
    </div>
    {IM.suggerimento_form("revolut")}
    <div id="toast" class="toast"></div>
    <script>
      const ALBERO = {json.dumps(albero, ensure_ascii=False)};
      const MID = {mid if mid else "null"};
      const SUB_INIZIALE = {json.dumps(m.get("sottocategoria"), ensure_ascii=False)};

      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 2600);
      }}
      function aggiornaSub() {{
        const cat = document.getElementById('f_categoria').value;
        const sel = document.getElementById('f_sottocategoria');
        const gruppo = ALBERO.find(g => g.categoria === cat);
        sel.innerHTML = '<option value="">—</option>';
        if (!gruppo) return;
        for (const v of gruppo.voci) {{
          if (!v.sottocategoria) continue;
          const o = document.createElement('option');
          o.value = v.sottocategoria; o.textContent = v.sottocategoria;
          sel.appendChild(o);
        }}
      }}
      function linkId() {{
        const cat = document.getElementById('f_categoria').value;
        const sub = document.getElementById('f_sottocategoria').value || null;
        const gruppo = ALBERO.find(g => g.categoria === cat);
        if (!gruppo) return null;
        const v = gruppo.voci.find(x => (x.sottocategoria || null) === sub);
        return v ? v.link_id : null;
      }}
      async function onSalva() {{
        const importo = Number(document.getElementById('f_importo').value || 0);
        if (!(importo > 0)) {{ toast('Inserisci un importo', 'err'); return; }}
        const cat = document.getElementById('f_categoria').value;
        const link = linkId();
        if (cat && !link) {{
          toast('Questa coppia categoria/sottocategoria non è prevista', 'err'); return;
        }}
        const body = {{
          data: document.getElementById('f_data').value,
          tipo: document.getElementById('f_tipo').value,
          sezione: document.getElementById('f_sezione').value,
          importo: importo,
          descrizione: document.getElementById('f_descrizione').value.trim(),
          categoria_link_id: link,
          note: document.getElementById('f_note').value.trim() || null,
        }};
        const nuovo = !MID;
        try {{
          const r = await fetch(nuovo ? '/spese/api/revolut/movimenti'
                                      : '/spese/api/revolut/movimenti/' + MID, {{
            method: nuovo ? 'POST' : 'PATCH',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast(nuovo ? 'Movimento registrato' : 'Aggiornato', 'ok');
          setTimeout(()=>{{ location.href = '/conti/revolut/movimenti'; }}, 600);
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}
      async function onElimina() {{
        if (!confirm('Eliminare questo movimento?')) return;
        try {{
          const r = await fetch('/spese/api/revolut/movimenti/' + MID, {{method: 'DELETE'}});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Eliminato', 'ok');
          setTimeout(()=>{{ location.href = '/conti/revolut/movimenti'; }}, 600);
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}
      aggiornaSub();
      if (SUB_INIZIALE) document.getElementById('f_sottocategoria').value = SUB_INIZIALE;
    </script>'''


@spese_bp.get("/conti/revolut/movimenti/nuovo")
def revolut_movimento_nuovo():
    breadcrumb = [("Conti", "/conti"), ("Revolut", "/conti/revolut"),
                  ("Movimenti", "/conti/revolut/movimenti"), ("Nuovo", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       "Nuovo movimento", '<em>Nuovo</em> movimento', breadcrumb)
    return _render(_form(client), "Nuovo movimento", '<em>Nuovo</em> movimento',
                   breadcrumb)


@spese_bp.get("/conti/revolut/movimenti/<int:mid>")
def revolut_movimento_modifica(mid):
    breadcrumb = [("Conti", "/conti"), ("Revolut", "/conti/revolut"),
                  ("Movimenti", "/conti/revolut/movimenti"), (str(mid), "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       "Movimento", '<em>Movimento</em>', breadcrumb)
    m = movimento(client, mid)
    if not m:
        return _render('<div class="notice err">Movimento non trovato.</div>',
                       "Movimento", '<em>Movimento</em>', breadcrumb)
    return _render(_form(client, m), "Movimento Revolut",
                   f'<em>{_esc((m.get("descrizione") or "Movimento")[:24])}</em>',
                   breadcrumb)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _client_o_503():
    client = D.sb()
    if client is None:
        return None, (jsonify({"error": "supabase not configured"}), 503)
    return client, None


def _esito(esito: dict):
    if not esito.get("error"):
        return jsonify(esito)
    return jsonify(esito), (503 if TABELLA in esito["error"] else 400)


@spese_bp.get("/spese/api/revolut/movimenti")
def api_revolut_movimenti():
    client, err = _client_o_503()
    if err:
        return err
    righe = tutti(client)
    if righe is None:
        return jsonify({"error": f"manca la tabella {TABELLA} (migrazione {MIGRAZIONE})"}), 503
    return jsonify(filtra(righe,
                          anno=request.args.get("anno", type=int),
                          mese=request.args.get("mese", type=int),
                          tipo=request.args.get("tipo") or None,
                          categoria=request.args.get("categoria") or None,
                          sezione=request.args.get("sezione") or None,
                          cerca=request.args.get("q") or None))


@spese_bp.post("/spese/api/revolut/movimenti")
def api_revolut_movimento_crea():
    client, err = _client_o_503()
    if err:
        return err
    return _esito(crea(client, request.get_json(silent=True) or {}))


@spese_bp.post("/spese/api/revolut/movimenti/importa")
def api_revolut_movimenti_importa():
    client, err = _client_o_503()
    if err:
        return err
    corpo = request.get_json(silent=True)
    righe = corpo.get("righe") if isinstance(corpo, dict) else None
    return _esito(importa(client, righe))


@spese_bp.patch("/spese/api/revolut/movimenti/<int:mid>")
def api_revolut_movimento_aggiorna(mid):
    client, err = _client_o_503()
    if err:
        return err
    return _esito(aggiorna(client, mid, request.get_json(silent=True) or {}))


@spese_bp.delete("/spese/api/revolut/movimenti/<int:mid>")
def api_revolut_movimento_elimina(mid):
    client, err = _client_o_503()
    if err:
        return err
    return _esito(elimina(client, mid))
