"""
shared/ordina.py — l'ordine in cui gli elenchi arrivano ai menu a tendina.

LA REGOLA
---------
Ogni menu che elenca *dati* (categorie, sottocategorie, clienti, metodi di
pagamento, tipi di movimento, commesse) si ordina alfabeticamente **per la
descrizione mostrata**, non per la chiave tecnica ne' per un campo `ordine`
del database. Chi cerca una voce in un menu la cerca col nome che legge:
se l'ordine e' un altro, la si trova solo scorrendo tutto.

Restano fuori i menu in cui l'ordine *e' informazione*, e alfabetizzarli
la distruggerebbe: mesi (Gennaio -> Dicembre), anni (dal piu' recente),
stati della fattura (l'ordine del ciclo di vita), scenari di
accantonamento (dal minimo al sicuro).

PERCHE' UNA FUNZIONE E NON `sorted()`
-------------------------------------
`sorted()` ordina per code point: "Zucchero" viene prima di "à la carte",
e "Ãˆlite" finisce dopo "Zzz". Con categorie come "Éxtra" o clienti
accentati l'elenco sembra ordinato male senza che nulla sia rotto. Qui
gli accenti si appiattiscono (NFKD) e il confronto e' senza maiuscole,
cosi' "È" sta fra "Duomo" e "Farmacia" come uno se lo aspetta.

Il secondo elemento della chiave e' il testo originale: due voci che si
appiattiscono uguali ("Perche" e "Perché") restano in un ordine stabile e
deterministico invece di dipendere dall'ordine di arrivo dal database.
"""
import unicodedata


def chiave_alfabetica(testo) -> tuple[str, str]:
    """Chiave di ordinamento per una descrizione mostrata all'utente."""
    s = "" if testo is None else str(testo)
    piatto = "".join(c for c in unicodedata.normalize("NFKD", s)
                     if not unicodedata.combining(c))
    return (piatto.casefold().strip(), s)


def ordina(voci, per=None) -> list:
    """
    Gli stessi elementi, in ordine alfabetico per descrizione.

    `per` estrae la descrizione da ogni elemento (default: l'elemento
    stesso). Non modifica la sequenza ricevuta: ritorna una lista nuova.
    """
    estrai = per or (lambda v: v)
    return sorted(voci, key=lambda v: chiave_alfabetica(estrai(v)))


def ordina_coppie(coppie) -> list:
    """Coppie (valore, etichetta) ordinate per etichetta."""
    return ordina(coppie, per=lambda c: c[1])
