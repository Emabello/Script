"""
shared/ore.py — il ponte fra il timesheet e la fattura.

Le ore non stanno su Supabase: stanno sul portale XS, e si leggono
**un giorno alla volta** in HTTP+scraping (`xs_client.get_day_entries`).
Un mese sono trenta richieste: e' il motivo per cui questo modulo esiste
come funzione esplicita e non come lettura di sfondo. Chi la chiama sta
facendo un gesto — precompilare una fattura, aggiornare la foto delle ore
— e puo' aspettare qualche secondo; una pagina che si apre no.

Da qui nascono due cose, ed e' la stessa somma:

  - **la fattura di fine mese**: giornate x tariffa, una riga sola;
  - **la foto** che resta attaccata alla fattura (`b2f_fatture.ore_snapshot`),
    cosi' il dettaglio si apre istantaneo e continua a raccontare quel mese
    anche fra due anni, quando il portale avra' dimenticato tutto.

**La giornata e' 8 ore**, la stessa definizione che il riepilogo mensile
del timesheet mostra come "giorni pieni da 8h": se cambia li', cambia qui.
Le giornate si contano sul **totale dei minuti**, non sui giorni di
calendario in cui hai timbrato — due mezze giornate sono una giornata da
fatturare, e il cliente paga il lavoro, non le volte che hai aperto il
portale.
"""
from __future__ import annotations

import calendar
import datetime as dt

from shared.ordina import chiave_alfabetica

GIORNATA_MIN = 8 * 60


def giornate(minuti) -> float:
    """Minuti -> giornate da 8 ore, con due decimali."""
    try:
        return round(float(minuti or 0) / GIORNATA_MIN, 2)
    except (TypeError, ValueError):
        return 0.0


def ore(minuti) -> float:
    """Minuti -> ore decimali, con due decimali."""
    try:
        return round(float(minuti or 0) / 60, 2)
    except (TypeError, ValueError):
        return 0.0


def fmt_min(minuti) -> str:
    """Minuti -> "7h 30m", come li scrive il timesheet."""
    try:
        m = int(minuti or 0)
    except (TypeError, ValueError):
        m = 0
    return f"{m // 60}h {m % 60:02d}m"


def _minuti_voce(voce: dict) -> int:
    """
    I minuti di una singola voce, senza fidarsi del testo del portale.

    `total` e' testo scrapato ("7h 30m", ma anche "", "-", "45m", o una
    timbratura ancora aperta). `day_payload` marca le voci illeggibili con
    `total_unreadable`; qui le saltiamo, e chi ci chiama riceve comunque il
    conteggio di quante ne ha saltate — un totale sottostimato senza dirlo
    e' peggio di un totale con un asterisco.
    """
    if voce.get("total_unreadable"):
        return 0
    testo = str(voce.get("total") or "")
    try:
        if "h" in testo:
            h, resto = testo.split("h", 1)
            m = resto.replace("m", "").strip() or "0"
            return int(h) * 60 + int(m)
        if "m" in testo:
            return int(testo.replace("m", "").strip())
    except (TypeError, ValueError):
        return 0
    return 0


def riepilogo_mese(anno: int, mese: int) -> dict:
    """
    Il mese intero, letto dal portale e riassunto.

    Ritorna sempre un dizionario: se il portale non risponde arriva con
    `errore` valorizzato e i totali a zero, cosi' chi lo mostra puo' dire
    cos'e' successo invece di stampare uno zero che sembra un dato vero.
    """
    anno, mese = int(anno), int(mese)
    vuoto = {
        "anno": anno, "mese": mese,
        "periodo": f"{anno:04d}-{mese:02d}-01",
        "minuti": 0, "ore": 0.0, "giornate": 0.0,
        "giorni_lavorati": 0, "giorni_mese": calendar.monthrange(anno, mese)[1],
        "voci_illeggibili": 0, "clienti": [],
        "letto_il": dt.datetime.now().isoformat(timespec="seconds"),
        "errore": None,
    }

    # Import ritardato: `xs_server` crea l'app Flask che tutto il resto
    # estende, e importarlo in cima a un modulo di `shared/` legherebbe
    # l'ordine degli import dell'intera hub a questo file.
    try:
        from xs_server import day_payload, ensure_login
    except Exception as e:                                   # pragma: no cover
        return {**vuoto, "errore": f"timesheet non disponibile: {str(e)[:120]}"}

    try:
        ensure_login()
    except Exception as e:
        return {**vuoto, "errore": f"login al portale fallito: {str(e)[:120]}"}

    ultimo = calendar.monthrange(anno, mese)[1]
    minuti_tot = 0
    illeggibili = 0
    lavorati = 0
    per_cliente: dict[str, int] = {}

    for giorno in range(1, ultimo + 1):
        try:
            payload = day_payload(dt.date(anno, mese, giorno))
        except Exception as e:
            return {**vuoto, "errore": f"il portale ha smesso di rispondere al "
                                       f"giorno {giorno}: {str(e)[:100]}"}
        minuti_giorno = int(payload.get("total_min") or 0)
        minuti_tot += minuti_giorno
        illeggibili += int(payload.get("unread_count") or 0)
        if minuti_giorno > 0:
            lavorati += 1
        for voce in payload.get("entries") or []:
            nome = (voce.get("client") or "").strip() or "—"
            per_cliente[nome] = per_cliente.get(nome, 0) + _minuti_voce(voce)

    clienti = [{"nome": n, "minuti": m, "ore": ore(m), "giornate": giornate(m)}
               for n, m in per_cliente.items() if m > 0]
    clienti.sort(key=lambda c: (-c["minuti"], chiave_alfabetica(c["nome"])))

    return {**vuoto,
            "minuti": minuti_tot,
            "ore": ore(minuti_tot),
            "giornate": giornate(minuti_tot),
            "giorni_lavorati": lavorati,
            "voci_illeggibili": illeggibili,
            "clienti": clienti,
            "letto_il": dt.datetime.now().isoformat(timespec="seconds")}
