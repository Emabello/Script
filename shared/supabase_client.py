"""
shared/supabase_client.py — Client Supabase condiviso.

Legge SUPABASE_URL e SUPABASE_KEY dalle env vars.
Ritorna None se le variabili non sono impostate: in tal caso le API
delle sezioni fatture/spese devono restituire 503, non crashare.

Usa la libreria ufficiale `supabase-py`.
"""
import os
from functools import lru_cache

try:
    from supabase import create_client, Client  # type: ignore
except ImportError:  # ambiente senza il pacchetto (dev locale non ancora installato)
    create_client = None  # type: ignore
    Client = None  # type: ignore


@lru_cache(maxsize=1)
def get_client():
    """Ritorna un client Supabase o None se non configurato."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")  # anon o service_role
    if not url or not key or create_client is None:
        return None
    return create_client(url, key, options=_opzioni())


def _opzioni():
    """
    Il client HTTP sotto supabase-py, scelto qui invece che lasciato al
    default.

    Il default di postgrest e' un `httpx.Client(http2=True)`: UNA
    connessione HTTP/2 condivisa da tutto il processo. Da quando le
    pagine chiedono i saldi in parallelo (`shared/parallelo.py`) quella
    connessione la usano piu' thread insieme, e ogni tanto una richiesta
    muore con un errore di protocollo. L'errore non e' una risposta 503
    (che postgrest ripete da solo): risale fino alla pagina, che mostra il
    conto come «saldo non disponibile» — un quadratino diverso a ogni
    refresh, come se fosse a caso. In HTTP/1.1 ogni richiesta concorrente
    prende una connessione sua dal pool, e il client e' sicuro fra thread.
    """
    try:
        import httpx
        from supabase.lib.client_options import SyncClientOptions
    except ImportError:
        return None
    http = httpx.Client(
        http2=False, follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
    )
    return SyncClientOptions(httpx_client=http, postgrest_client_timeout=30)


def is_configured() -> bool:
    return get_client() is not None
