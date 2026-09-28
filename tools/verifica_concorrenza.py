"""
Il client Supabase sotto richieste parallele.

    python3 tools/verifica_concorrenza.py

Su /conti i tre saldi partono insieme (shared/parallelo.py). Con la
connessione HTTP/2 condivisa che supabase-py apre di default, ogni tanto
una delle richieste moriva e un quadratino diceva «saldo non disponibile»,
ogni refresh uno diverso. Qui un finto PostgREST locale riceve 240
richieste, otto alla volta, dal client vero di `shared/supabase_client.py`:
nessuna deve fallire, e il client deve essere in HTTP/1.1.

Esce con codice 1 al primo problema.
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PORTA = 8799


class _PostgrestFinto(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        time.sleep(0.02)   # un po' di latenza, perche' le richieste si sovrappongano
        corpo = json.dumps([{"importo": 1, "tipo": "entrata", "data": "2026-01-01"}]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_a):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORTA), _PostgrestFinto)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{PORTA}"
    os.environ["SUPABASE_KEY"] = "x" * 40
    os.environ["NO_PROXY"] = "127.0.0.1"

    from shared.parallelo import in_parallelo
    from shared.supabase_client import get_client
    client = get_client()

    problemi = []
    http2 = client.postgrest.session._transport._pool._http2
    print(f"  {'ok' if not http2 else 'NO':6} client in HTTP/1.1 (http2={http2})")
    if http2:
        problemi.append("http2")

    fallite = 0
    for _giro in range(30):
        esiti = in_parallelo(*[(lambda: client.table("spese").select("*").execute().data)
                               for _ in range(8)])
        fallite += sum(1 for e in esiti if not e)
    print(f"  {'ok' if not fallite else 'NO':6} 240 richieste parallele, {fallite} fallite")
    if fallite:
        problemi.append("fallite")

    print()
    if problemi:
        print(f"{len(problemi)} cose da guardare.")
        sys.exit(1)
    print("Tutto torna.")


if __name__ == "__main__":
    main()
