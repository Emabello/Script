"""
spese/interessi.py — Gli interessi dei salvadanai Revolut, fra un estratto
e l'altro.

Il «Deposito senza vincoli» paga gli interessi **ogni giorno**, su ogni
salvadanaio, al netto della ritenuta:

    interesse del giorno = saldo × tasso lordo annuo ÷ 365 × (1 − 26%)

Casa con 5.328 € all'1,38% fa 0,15 € al giorno. Sono pochi centesimi, ma
fra un estratto e l'altro si accumulano, e il saldo dell'app si allontana
da quello che Revolut mostra oggi. E il tasso non e' fisso: 1,50% da
aprile a giugno 2026, 1,38% da luglio.

Qui dentro tre cose, tutte calcolate e nessuna scritta nel database:

  * `tasso_dagli_interessi`: il tasso lordo ricavato dagli interessi veri
    degli ultimi 30 giorni, guardando solo i salvadanai sopra i 500 € —
    su Regali (85 €) il maturato del giorno e' meno di un centesimo,
    Revolut lo paga ogni 3–4 giorni e il tasso «visto» sembrerebbe il 4%;
  * i tassi scritti a mano in `b2f_revolut_tassi` (migrazione §8.20):
    «da questa data il tasso e' X», per quando Revolut annuncia un tasso
    nuovo prima che un estratto lo mostri. Valgono solo se piu' recenti
    degli interessi da cui si ricava il tasso: il dato vero vince;
  * `stima`: gli interessi maturati dall'ultimo giorno pagato a oggi,
    salvadanaio per salvadanaio. Si mostrano accanto al saldo come stima
    («≈»), mai dentro il saldo: al prossimo estratto arrivano quelli veri,
    e la stima riparte da li'. Nessun movimento inventato, nessun doppione.
"""
import re
from datetime import date, timedelta

RITENUTA = 0.26
TABELLA_TASSI = "b2f_revolut_tassi"
FINESTRA_GIORNI = 30
SALDO_MINIMO = 500.0
# Un cambio di tasso fra un mese e l'altro sotto questa soglia e' rumore
# degli arrotondamenti al centesimo, non una decisione di Revolut.
SOGLIA_CAMBIO = 0.05

_INTERESSI = re.compile(r"interess|interest", re.I)


def _giorno(v) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _firmato(r) -> float:
    try:
        imp = abs(float(r.get("importo") or 0))
    except (TypeError, ValueError):
        return 0.0
    return imp if r.get("tipo") == "entrata" else -imp


def _deltas(movimenti: list[dict]) -> list[tuple[date, str, float, bool]]:
    """
    I movimenti del deposito che nominano un salvadanaio, come
    (giorno, salvadanaio, importo firmato, e' un interesse).
    """
    from .revolut import _salvadanaio_da_descrizione
    out = []
    for r in movimenti or []:
        if (r.get("sezione") or "conto") != "risparmi":
            continue
        g = _giorno(r.get("data"))
        k = _salvadanaio_da_descrizione(r.get("descrizione") or "")
        if g is None or not k:
            continue
        out.append((g, k, _firmato(r), bool(_INTERESSI.search(r.get("descrizione") or ""))))
    return out


def saldo_salvadanai(foto: dict, foto_data: str, deltas, giorno: date) -> dict:
    """
    I salvadanai a fine `giorno`, partendo dalla fotografia (fine del suo
    giorno) e muovendosi con i movimenti che li nominano — in avanti se
    `giorno` e' dopo la fotografia, all'indietro se e' prima.
    """
    base = _giorno(foto_data)
    saldi = {k: float(v or 0) for k, v in (foto or {}).items()}
    if base is None:
        return saldi
    for g, k, imp, _i in deltas:
        if base < g <= giorno:
            saldi[k] = saldi.get(k, 0.0) + imp
        elif giorno < g <= base:
            saldi[k] = saldi.get(k, 0.0) - imp
    return {k: round(v, 2) for k, v in saldi.items()}


def _lordo(netto_giornaliero: float) -> float:
    """Da interesse netto per euro al giorno a tasso lordo annuo in %."""
    return round(netto_giornaliero * 365 / (1 - RITENUTA) * 100, 2)


def tasso_dagli_interessi(foto: dict, foto_data: str, movimenti: list[dict],
                          al: str) -> dict | None:
    """
    Il tasso lordo annuo che Revolut ha pagato davvero negli ultimi
    `FINESTRA_GIORNI` giorni di interessi fino ad `al`, e mese per mese
    quello dei mesi coperti, per accorgersi dei cambi. None se non ci sono
    interessi su salvadanai abbastanza grandi da misurarlo.
    """
    fine = _giorno(al)
    deltas = _deltas(movimenti)
    pagati = sorted((g, k, imp) for g, k, imp, interesse in deltas
                    if interesse and fine and g <= fine)
    if not pagati:
        return None
    ultimo = pagati[-1][0]
    inizio = ultimo - timedelta(days=FINESTRA_GIORNI - 1)

    # Per mese: interessi netti e saldo del giorno prima, sommati sui
    # salvadanai grandi. Il saldo del giorno prima e' quello su cui
    # matura l'interesse pagato il giorno dopo.
    mesi: dict[str, list[float]] = {}
    finestra = [0.0, 0.0]
    cache: dict[date, dict] = {}
    for g, k, imp in pagati:
        prima = g - timedelta(days=1)
        if prima not in cache:
            cache[prima] = saldo_salvadanai(foto, foto_data, deltas, prima)
        base = cache[prima].get(k, 0.0)
        if base < SALDO_MINIMO or imp <= 0:
            continue
        m = mesi.setdefault(g.strftime("%Y-%m"), [0.0, 0.0])
        m[0] += imp
        m[1] += base
        if g >= inizio:
            finestra[0] += imp
            finestra[1] += base
    if not finestra[1]:
        return None
    per_mese = [(m, _lordo(v[0] / v[1])) for m, v in sorted(mesi.items()) if v[1]]
    cambio = None
    if len(per_mese) >= 2 and abs(per_mese[-1][1] - per_mese[-2][1]) >= SOGLIA_CAMBIO:
        cambio = {"mese": per_mese[-1][0], "da": per_mese[-2][1], "a": per_mese[-1][1]}
    return {
        "tasso": _lordo(finestra[0] / finestra[1]),
        "dal": max(inizio, pagati[0][0]).isoformat(),
        "al": ultimo.isoformat(),
        "mesi": per_mese[-6:],
        "cambio": cambio,
        "fonte": "estratto",
    }


def tassi_manuali(client) -> list[dict]:
    """I tassi scritti a mano, dal piu' vecchio. Lista vuota senza tabella."""
    try:
        r = client.table(TABELLA_TASSI).select("*").order("dal").execute()
        righe = getattr(r, "data", None) or []
    except Exception:
        return []
    out = []
    for x in righe:
        try:
            out.append({"dal": str(x["dal"])[:10], "tasso": round(float(x["tasso_lordo"]), 3),
                        "note": x.get("note")})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def tasso_del_giorno(giorno: date, ricavato: dict | None, manuali: list[dict]) -> dict | None:
    """
    Il tasso che vale in `giorno`: quello scritto a mano con la data piu'
    recente fino a quel giorno, se e' piu' recente degli interessi da cui
    e' ricavato l'altro; altrimenti quello ricavato. None se nessuno dei due.
    """
    fine_ricavato = _giorno((ricavato or {}).get("al"))
    scelto = None
    for m in manuali:
        dal = _giorno(m["dal"])
        if dal and dal <= giorno and (fine_ricavato is None or dal > fine_ricavato):
            scelto = {"tasso": m["tasso"], "fonte": "manuale", "dal": m["dal"]}
    if scelto:
        return scelto
    if ricavato:
        return {"tasso": ricavato["tasso"], "fonte": "estratto", "dal": ricavato["dal"]}
    return None


def stima(foto: dict, foto_data: str, movimenti: list[dict], al: str,
          manuali: list[dict] | None = None) -> dict:
    """
    Gli interessi maturati e non ancora registrati, fino ad `al` compreso.

    Partono dal giorno dopo l'ultimo interesse registrato (o dalla
    fotografia, se e' piu' recente): quel giorno e i precedenti sono gia'
    dentro il saldo. Ogni giorno matura sul saldo del salvadanaio, al tasso
    che vale quel giorno.
    """
    manuali = manuali or []
    fine = _giorno(al)
    vuota = {"totale": 0.0, "per_salvadanaio": {}, "giorni": 0, "dal": None, "al": al,
             "tasso": None, "fonte_tasso": None, "ricavato": None, "manuali": manuali}
    if fine is None:
        return vuota
    deltas = _deltas(movimenti)
    ricavato = tasso_dagli_interessi(foto, foto_data, movimenti, al)
    vuota["ricavato"] = ricavato
    pagati = [g for g, _k, _imp, interesse in deltas if interesse and g <= fine]
    base = max([d for d in (_giorno(foto_data), max(pagati) if pagati else None) if d]
               or [fine])
    giorni = (fine - base).days
    if giorni <= 0:
        t = tasso_del_giorno(fine, ricavato, manuali)
        vuota.update({"tasso": t and t["tasso"], "fonte_tasso": t and t["fonte"]})
        return vuota
    saldi = saldo_salvadanai(foto, foto_data, deltas, base)
    maturato = {k: 0.0 for k in saldi}
    usato = None
    for n in range(1, giorni + 1):
        giorno = base + timedelta(days=n)
        t = tasso_del_giorno(giorno, ricavato, manuali)
        if not t:
            continue
        usato = t
        for k, s in saldi.items():
            if s > 0:
                maturato[k] += s * t["tasso"] / 100 / 365 * (1 - RITENUTA)
    per = {k: round(v, 2) for k, v in maturato.items() if round(v, 2)}
    return {
        "totale": round(sum(maturato.values()), 2),
        "per_salvadanaio": per,
        "giorni": giorni,
        "dal": (base + timedelta(days=1)).isoformat(),
        "al": al,
        "tasso": usato and usato["tasso"],
        "fonte_tasso": usato and usato["fonte"],
        "ricavato": ricavato,
        "manuali": manuali,
    }


def resa(saldi: dict, tasso: float | None, giorni: int) -> float:
    """Gli interessi netti che i salvadanai renderanno in `giorni` giorni."""
    if not tasso or giorni <= 0:
        return 0.0
    tot = sum(float(v or 0) for v in (saldi or {}).values() if float(v or 0) > 0)
    return round(tot * tasso / 100 / 365 * (1 - RITENUTA) * giorni, 2)


def movimenti_deposito(client, dal: str, al: str) -> list[dict] | None:
    """I movimenti del deposito in un intervallo: pochi, bastano per la stima."""
    from .revolut_movimenti import TABELLA
    try:
        r = (client.table(TABELLA).select("data,tipo,importo,descrizione,sezione")
             .eq("sezione", "risparmi").gte("data", dal).lte("data", al)
             .order("data").order("id").execute())
        return getattr(r, "data", None) or []
    except Exception:
        return None


def salva_tasso(client, dati: dict) -> dict:
    """Registra «da questa data il tasso e' X». La data e' la chiave."""
    dal = str(dati.get("dal") or "")[:10]
    if _giorno(dal) is None:
        return {"error": "data non valida"}
    try:
        tasso = round(float(str(dati.get("tasso")).replace(",", ".")), 3)
    except (TypeError, ValueError):
        return {"error": "tasso non valido"}
    if not 0 <= tasso <= 20:
        return {"error": "tasso fuori scala: si scrive in percento, per esempio 1,38"}
    riga = {"dal": dal, "tasso_lordo": tasso, "note": (dati.get("note") or None)}
    try:
        client.table(TABELLA_TASSI).upsert(riga, on_conflict="dal").execute()
    except Exception as e:
        return {"error": f"non salvato: {str(e)[:120]}"}
    return {"ok": True, **riga}


def cancella_tasso(client, dal: str) -> dict:
    if _giorno(dal) is None:
        return {"error": "data non valida"}
    try:
        client.table(TABELLA_TASSI).delete().eq("dal", str(dal)[:10]).execute()
    except Exception as e:
        return {"error": f"non cancellato: {str(e)[:120]}"}
    return {"ok": True}
