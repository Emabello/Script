"""
shared/parallelo.py — Domande indipendenti al database, tutte insieme.
"""


def in_parallelo(*compiti):
    """
    Esegue le funzioni date insieme invece che una dopo l'altra, e ne
    restituisce i risultati nello stesso ordine (None per quelle fallite).

    Una pagina come la home fa una ventina di domande al database, e ogni
    domanda e' un viaggio fino a Supabase e ritorno: in fila, i tempi si
    sommano, e sono quasi tutti attesa di rete. Le domande indipendenti
    ora partono insieme e la pagina aspetta solo la piu' lenta. Il client
    Supabase e' uno per processo e regge le richieste concorrenti (un
    pool di connessioni httpx).
    """
    from concurrent.futures import ThreadPoolExecutor

    def protetto(f):
        try:
            return f()
        except Exception:
            return None

    if len(compiti) == 1:
        return [protetto(compiti[0])]
    with ThreadPoolExecutor(max_workers=min(8, len(compiti))) as ex:
        return list(ex.map(protetto, compiti))
