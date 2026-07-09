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
    return create_client(url, key)


def is_configured() -> bool:
    return get_client() is not None
