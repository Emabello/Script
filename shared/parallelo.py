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
    Supabase e' uno per processo e regge le richieste concorrenti perche'
    usa un pool di connessioni HTTP/1.1 (`shared/supabase_client.py`): con
    la connessione HTTP/2 condivisa di default, un saldo spariva a caso.
    """
    from concurrent.futures import ThreadPoolExecutor

    import logging

    # Un errore di rete isolato (una connessione chiusa dal server nel
    # momento sbagliato) non deve far sparire un conto dalla pagina: si
    # riprova una volta. Se fallisce ancora resta None, ma nel log: prima
    # l'errore spariva in silenzio e l'unico segno era un saldo a zero.
    def protetto(f):
        for tentativo in (1, 2):
            try:
                return f()
            except Exception:
                logging.getLogger("parallelo").warning(
                    "compito in parallelo fallito (tentativo %d)", tentativo, exc_info=True)
        return None

    if len(compiti) == 1:
        return [protetto(compiti[0])]
    with ThreadPoolExecutor(max_workers=min(8, len(compiti))) as ex:
        return list(ex.map(protetto, compiti))
