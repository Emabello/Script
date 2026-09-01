"""
Verifica del facsimile PDF.

Il PDF e' l'unico artefatto dell'app che esce e finisce in mano a un
altro: lo studio ci costruisce sopra la fattura elettronica. Se cambia
per sbaglio non se ne accorge nessuno finche' non e' troppo tardi, quindi
qui si controlla che contenga quello che deve.

    ./venv/bin/python tools/verifica_facsimile.py
"""
import os
import pathlib
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 5096
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# Fattura 1 dei dati di prova: 20 x 250 = 5.000 concordati, rivalsa 4 %
# scorporata, bollo addebitato.
ATTESI = [
    # (frammento, perche' deve esserci)
    ("FACSIMILE",
     "chi lo riceve deve capire subito che non e' la fattura fiscale"),
    ("Corrispettivo",
     "il totale concordato col cliente"),
    ("di cui compenso",
     "la voce che lo studio mette in DettaglioLinee"),
    ("di cui rivalsa INPS",
     "la voce che lo studio mette in DatiCassaPrevidenziale"),
    ("4.807,69",
     "compenso = 5.000 / 1,04: se cambia, e' tornato l'addebito"),
    ("192,31",
     "rivalsa scorporata = 5.000 - compenso"),
    ("5.002,00",
     "totale = corrispettivo + bollo, NON corrispettivo + 4 %"),
    ("IBAN",
     "lo studio l'ha chiesto esplicitamente per il bonifico"),
    ("regime forfettario",
     "dicitura di legge sull'assenza di IVA"),
    ("ritenuta d'acconto",
     "dicitura di legge sulla non assoggettabilita'"),
]

# Non devono comparire: sono i segni del vecchio comportamento.
VIETATI = [
    ("5.200,00", "e' il totale con la rivalsa ADDEBITATA invece che scorporata"),
    ("cdnjs.cloudflare", "la libreria PDF deve essere quella locale"),
    # L'avviso in calce e' stato tolto su richiesta (01/09/2026): il foglio
    # si stampa e si consegna, e non deve portarsi dietro il nome dello
    # studio ne' la frase sul valore fiscale. Sta fra i VIETATI e non fra
    # gli spariti-e-basta perche' il modo in cui torna e' che qualcuno
    # rimetta il blocco senza sapere che era stato tolto apposta.
    ("documento non valido ai fini fiscali",
     "l'avviso in calce e' stato tolto: non deve ricomparire"),
    ("Sistema di Interscambio",
     "stessa riga dell'avviso, stesso motivo"),
    ("Studio Bagaglia",
     "il nome dello studio non deve finire sul foglio consegnato"),
]


def serve():
    preview.application.run(host="127.0.0.1", port=PORT, debug=False,
                            use_reloader=False, threaded=True)


def main():
    try:
        from pypdf import PdfReader
    except ImportError:
        print("serve pypdf:  pip install pypdf")
        return 2

    threading.Thread(target=serve, daemon=True).start()
    time.sleep(2)

    out = pathlib.Path(__file__).parent / "_facsimile_verifica.pdf"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(accept_downloads=True).new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/fatture/1",
                wait_until="domcontentloaded", timeout=15000)
        pg.wait_for_timeout(2000)

        if not pg.evaluate("!!(window.jspdf && window.jspdf.jsPDF)"):
            print("jsPDF non caricata: il PDF non si genera")
            b.close()
            return 1

        with pg.expect_download(timeout=20000) as dl:
            pg.evaluate("window.b2fRenderInvoicePDF(FATTURA_PAYLOAD)")
        download = dl.value
        nome = download.suggested_filename
        download.save_as(out)
        b.close()

    testo = "\n".join(pg_.extract_text() for pg_ in PdfReader(out).pages)
    out.unlink(missing_ok=True)

    print(f"file generato: {nome}\n")
    guasti = 0

    if not nome.startswith("Facsimile_"):
        print(f"  MANCA  il nome del file dovrebbe iniziare per Facsimile_, e' «{nome}»")
        guasti += 1

    for frammento, perche in ATTESI:
        ok = frammento in testo
        print(f"  {'ok   ' if ok else 'MANCA'}  {frammento:36} {perche}")
        if not ok:
            guasti += 1

    print()
    for frammento, perche in VIETATI:
        ok = frammento not in testo
        print(f"  {'ok   ' if ok else 'TROVATO'}  {frammento:34} {perche}")
        if not ok:
            guasti += 1

    print()
    print("facsimile corretto" if guasti == 0 else f"{guasti} controlli falliti")
    return guasti


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
