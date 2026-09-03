"""
Verifica che nessuna pagina abbia JavaScript rotto.

L'app genera il suo JS da f-string Python, e li' dentro un apostrofo o un
a-capo scritto con un backslash solo non arriva mai al browser: se lo
mangia Python. La stringa JS si chiude a meta' frase e il browser scarta
**l'intero blocco `<script>`** con un errore di sintassi — bottoni morti,
form che non salvano, e nessun segno visibile sulla pagina.

E' successo davvero: `spese/risparmi.py` aveva
`confirm('Registro un\\'uscita...')` con un backslash solo, e la
procedura di fine periodo non funzionava. Non se n'era accorto nessuno
perche' la pagina si disegna lo stesso.

    ./venv/bin/python tools/verifica_js.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 5097
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

PAGINE = [
    ("home",        "/"),
    ("ore",         "/ore"),
    ("fatture",     "/fatture/"),
    ("storico",     "/fatture/storico"),
    ("dettaglio",   "/fatture/1"),
    ("editor",      "/fatture/nuova"),
    ("modifica",    "/fatture/7/modifica"),
    ("clienti",     "/fatture/clienti"),
    ("emittente",   "/fatture/emittente"),
    ("situazione",  "/fatture/situazione"),
    ("parametri",   "/fatture/parametri"),
    ("spesepiva",   "/fatture/spese-piva"),
    ("spese",       "/spese/"),
    ("movimenti",   "/spese/movimenti"),
    ("risparmi",    "/spese/risparmi"),
    ("revolut",     "/spese/revolut"),
    ("importa",     "/spese/importa"),
    ("saldi",       "/saldi"),
]


def serve():
    preview.application.run(host="127.0.0.1", port=PORT, debug=False,
                            use_reloader=False, threaded=True)


def main():
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(2)

    guasti = 0
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 900, "height": 1000}).new_page()
        for nome, url in PAGINE:
            errori = []
            ascolta = lambda e: errori.append(str(e))   # noqa: E731
            pg.on("pageerror", ascolta)
            try:
                pg.goto(f"http://127.0.0.1:{PORT}{url}",
                        wait_until="domcontentloaded", timeout=15000)
                pg.wait_for_timeout(400)
            except Exception as e:
                errori.append(f"pagina non caricata: {str(e)[:80]}")
            pg.remove_listener("pageerror", ascolta)

            if errori:
                guasti += 1
                print(f"  ROTTO  {nome:11} {url}")
                for e in errori:
                    print(f"         {e}")
            else:
                print(f"  ok     {nome:11} {url}")
        b.close()

    print()
    print("nessun errore JavaScript" if guasti == 0
          else f"{guasti} pagine con JavaScript rotto")
    return guasti


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
