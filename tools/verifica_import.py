"""
Controlli sull'import da estratto e sui suggerimenti di categoria.

    python3 tools/verifica_import.py

Tre cose, sul finto client di tools/preview.py (il database vero non si
tocca):

1. il motore dei suggerimenti (shared/suggerimenti.py): stesso esercente,
   importi diversi — il caffe' e il pranzo allo stesso bancone —,
   multipli, descrizioni scritte in formati diversi dalla banca;
2. i doppioni (shared/importazione.py): due caffe' identici nello stesso
   giorno sono due movimenti, e il secondo non si butta;
3. il giro completo delle pagine di import, WeBank personale, P.IVA e
   Revolut: leggi il file, rivedi, salva, rileggi lo stesso file.

Esce con codice 1 se qualcosa non torna.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl  # noqa: E402

import preview  # noqa: E402
from preview import DB  # noqa: E402
from shared import importazione as IM  # noqa: E402
from shared import suggerimenti as SG  # noqa: E402
from spese.importa import clean_bank_description  # noqa: E402

PROBLEMI: list[str] = []


def controlla(cond, msg):
    print(("  ok     " if cond else "  NO     ") + msg)
    if not cond:
        PROBLEMI.append(msg)


def storico_finto():
    """Il McDonald's sotto l'ufficio, com'e' davvero nello storico."""
    righe = []
    for i, imp in enumerate([1.10, 1.10, 2.20, 2.20, 3.30, 1.10, 2.20, 1.10, 2.20, 1.10]):
        righe.append({"data": f"2026-07-{i + 1:02d}", "tipo": "uscita", "importo": imp,
                      "descrizione": "Mcdonald'S 35 Mil Ano", "etichetta": "caffe",
                      "nome": "Personale › Caffè"})
    for i, imp in enumerate([14.80, 16.59, 16.59, 11.69]):
        righe.append({"data": f"2026-06-{i + 1:02d}", "tipo": "uscita", "importo": imp,
                      "descrizione": "pagamento con carta - carta *2058-mcdonald's 35  milano  mi  ita",
                      "etichetta": "cibo", "nome": "Personale › Cibo"})
    righe += [
        {"data": "2026-07-14", "tipo": "uscita", "importo": 20.0,
         "descrizione": "SDD Satispay Europe S.A.", "etichetta": "satispay", "nome": "Fisso › Satispay"},
        {"data": "2026-07-21", "tipo": "uscita", "importo": 25.4,
         "descrizione": "SDD Satispay Europe S.A.", "etichetta": "satispay", "nome": "Fisso › Satispay"},
        {"data": "2026-07-01", "tipo": "entrata", "importo": 1270.24,
         "descrizione": "Bonifico da Sileron S.R.L.", "etichetta": "stipendio", "nome": "Stipendio"},
        {"data": "2026-07-02", "tipo": "uscita", "importo": 5.0,
         "descrizione": "", "etichetta": "altro", "nome": "Personale › Altro"},
    ]
    return SG.Storico(righe)


def estratto_webank(righe):
    """Un export WeBank: intestazione e una riga per movimento."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Data Contabile", "Data Valuta", "Importo", "Causale"])
    for r in righe:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main():
    print("\n== descrizioni della banca")
    c = clean_bank_description
    controlla(c("pagamento con carta - carta *2058-mcdonald's 35  milano     mi   ita")
              == "Mcdonald'S 35 Milano", "formato carta nuovo (dal 06/2026) ripulito")
    controlla(c("spesa pagobancomat - carta*2058-08:48-conad 9255 milano ita")
              == "Conad 9255 Milano", "pagobancomat con l'ora")
    controlla(SG.chiave("Mcdonald'S 35 Mil Ano")[:9] == SG.chiave(
        "pagamento con carta - carta *2058-mcdonald's 35 milano mi ita")[:9],
        "le due scritture dello stesso esercente hanno la stessa radice")

    print("\n== suggerimenti")
    s = storico_finto()
    for imp, atteso, perche in [(1.10, "caffe", "stesso importo"),
                                (4.40, "caffe", "multiplo di 1,10"),
                                (3.30, "caffe", "tre caffè"),
                                (15.20, "cibo", "un pranzo, non un caffè"),
                                (17.00, "cibo", "vicino ai pranzi")]:
        p = s.suggerisci("pagamento con carta - carta *2058-mcdonald's 35 milano mi ita", imp, "uscita")
        controlla(p and p["etichetta"] == atteso,
                  f"McDonald's € {imp:.2f} -> {p and p['nome']} ({perche})")
    p = s.suggerisci("SDD Satispay Europe S.A.", 22.10, "uscita")
    controlla(p and p["etichetta"] == "satispay" and p["sicura"], "Satispay, importo nuovo")
    controlla(s.suggerisci("Bonifico da Sileron S.R.L.", 1300, "uscita") is None,
              "la direzione conta: uno stipendio non suggerisce un'uscita")
    controlla(s.suggerisci("", 5.0, "uscita") is None, "senza descrizione niente proposta")
    controlla(s.suggerisci("Ferramenta Rossi", 12.0, "uscita") is None,
              "esercente mai visto: niente proposta")
    p = s.suggerisci("Mcdonald'S 35 Mil Ano", 1.10, "uscita", ammesse={"cibo"})
    controlla(p and p["etichetta"] == "cibo", "le categorie non ammesse non si propongono")

    print("\n== doppioni: le copie si contano")
    caffe = {"data": "2026-09-02", "tipo": "uscita", "importo": 1.10,
             "descrizione": "Mcdonald'S 35 Milano"}
    righe = [dict(caffe), dict(caffe)]
    IM.segna_doppioni([dict(caffe, descrizione="Mcdonald'S 35 Mil Ano")], righe)
    controlla(righe[0].get("presente") and not righe[1].get("presente"),
              "a database un caffè, nel file due: il primo è già registrato, il secondo no")
    controlla(bool(righe[1].get("sospetto")), "…e il secondo è segnato come sospetto, da guardare")
    righe = [dict(caffe), dict(caffe)]
    IM.segna_doppioni([dict(caffe), dict(caffe)], righe)
    controlla(all(r.get("presente") for r in righe), "a database due caffè: entrambi registrati")
    righe = [dict(caffe, data="2026-09-05")]
    IM.segna_doppioni([dict(caffe)], righe)
    controlla(not righe[0].get("presente") and righe[0].get("sospetto"),
              "stesso importo tre giorni dopo: sospetto, non scartato")

    print("\n== import WeBank personale, giro completo")
    app = preview.application.test_client()
    file = estratto_webank([
        ["09/09/2026", "09/09/2026", -1.10, "pagamento con carta - carta *2058-mcdonald's 35  milano mi ita"],
        ["09/09/2026", "09/09/2026", -1.10, "pagamento con carta - carta *2058-mcdonald's 35  milano mi ita"],
        ["10/09/2026", "10/09/2026", -42.90,
         "addebito diretto sepa core - vodafone italia s.p.a. rata mensile"],
        ["11/09/2026", "11/09/2026", -7.77, "pagamento con carta - carta *2058-ferramenta nuova  milano ita"],
    ])
    r = app.post("/spese/api/importa/carica",
                 data={"file": (io.BytesIO(file), "estratto.xlsx")},
                 content_type="multipart/form-data")
    j = r.get_json()
    mov = j.get("movimenti") or []
    controlla(r.status_code == 200 and len(mov) == 4, f"letto il file: {len(mov)} righe")
    caffe_letti = [m for m in mov if m["importo"] == 1.10]
    controlla(len(caffe_letti) == 2 and not any(m.get("presente") for m in caffe_letti),
              "i due caffè identici sono due righe nuove")
    controlla(all(m.get("categoria") is None or m.get("suggerimento") for m in mov),
              "ogni categoria preselezionata ha la sua spiegazione")
    righe = [{"idx": i, "data": m["data"], "tipo": m["tipo"], "importo": m["importo"],
              "descrizione": m["descrizione"],
              "categoria": m.get("categoria") or preview._link_id("Personale", None)}
             for i, m in enumerate(mov)]
    prima = len(DB["spese"])
    r = app.post("/spese/api/importa/salva", json={"righe": righe})
    j = r.get_json()
    controlla(len(j.get("salvate") or []) == 4 and len(DB["spese"]) == prima + 4,
              f"salvate 4 righe, due caffè compresi ({j})")
    r = app.post("/spese/api/importa/carica",
                 data={"file": (io.BytesIO(file), "estratto.xlsx")},
                 content_type="multipart/form-data")
    mov2 = r.get_json().get("movimenti") or []
    controlla(all(m.get("presente") for m in mov2),
              "riletto lo stesso file: tutte già registrate")
    r = app.post("/spese/api/importa/salva", json={"righe": righe})
    controlla(len(r.get_json().get("duplicati") or []) == 4 and len(DB["spese"]) == prima + 4,
              "risalvarlo non duplica niente")
    r = app.post("/spese/api/importa/salva",
                 json={"righe": [dict(righe[0], data="2026-09-20", categoria=None)]})
    controlla((r.get_json().get("errori") or [{}])[0].get("errore") == "categoria mancante",
              "sul personale una riga senza categoria non si salva")

    print("\n== import WeBank P.IVA")
    file = estratto_webank([
        ["12/09/2026", "12/09/2026", -45.00, "addebito diretto sepa - rinnovo pec annuale"],
        ["13/09/2026", "13/09/2026", -900.00, "disp.giro conto - trasferimento a conto *1234"],
        ["31/07/2026", "31/07/2026", 4100.00, "bon.da ACME SISTEMI nr. bonifico 99"],
    ])
    r = app.post("/fatture/api/spese-piva/importa/carica",
                 data={"file": (io.BytesIO(file), "piva.xlsx")},
                 content_type="multipart/form-data")
    mov = r.get_json().get("movimenti") or []
    per = {m["importo"]: m for m in mov}
    controlla(len(mov) == 3, f"letto il file P.IVA: {len(mov)} righe")
    controlla(per.get(900.0, {}).get("presente") and "giroconto" in per[900.0].get("nota", ""),
              "il giroconto verso il personale è bloccato, col motivo")
    controlla("fattura" in (per.get(4100.0, {}).get("sospetto") or "").lower(),
              "l'incasso di una fattura è segnalato: si registra dalla fattura")
    controlla(per.get(45.0, {}).get("categoria") == "pec",
              f'la PEC prende la categoria dallo storico P.IVA ({per.get(45.0, {}).get("suggerimento")})')
    prima = len(DB["b2f_spese_piva"])
    r = app.post("/fatture/api/spese-piva/importa/salva", json={"righe": [
        {"idx": 0, "data": "2026-09-12", "tipo": "uscita", "importo": 45.0,
         "descrizione": "Aruba Pec Rinnovo", "categoria": "pec"},
        {"idx": 1, "data": "2026-09-13", "tipo": "uscita", "importo": 900.0,
         "descrizione": "Trasferimento", "categoria": "giroconto_personale"}]})
    j = r.get_json()
    controlla(j.get("salvate") == [0] and len(DB["b2f_spese_piva"]) == prima + 1,
              "salvata la PEC")
    controlla((j.get("errori") or [{}])[0].get("idx") == 1,
              "un giroconto dal file viene rifiutato anche se forzato")

    print("\n== import Revolut dalla pagina")
    import verifica_revolut as VR
    r = app.post("/spese/api/revolut/leggi",
                 data={"file": (io.BytesIO(VR.estratto(VR.RIGHE)), "x_20260801_20260831.xlsx")},
                 content_type="multipart/form-data")
    j = r.get_json()
    controlla(r.status_code == 200 and len(j.get("movimenti") or []) == 8
              and all(isinstance(a, dict) for a in j.get("avvisi") or []),
              "saldi, movimenti e avvisi nella forma del pannello comune")
    righe = [{"idx": i, "chiave": m["chiave"], "data": m["data"], "tipo": m["tipo"],
              "importo": m["importo"], "descrizione": m["descrizione"],
              "sezione": m["sezione"], "categoria": m.get("categoria")}
             for i, m in enumerate(j["movimenti"]) if not m.get("presente")]
    r = app.post("/spese/api/revolut/movimenti/importa", json={"righe": righe})
    controlla(len(r.get_json().get("salvate") or []) == len(righe),
              f"salvate {len(righe)} righe dal pannello")
    for u in ("/conti/revolut/importa", "/conti/webank/piva/importa",
              "/conti/webank/personale/importa"):
        pagina = app.get(u).get_data(as_text=True)
        controlla("IMPORT.carica" in pagina and "impCorpo" in pagina,
                  f"{u}: stesso pannello di revisione")

    print()
    if PROBLEMI:
        print(f"{len(PROBLEMI)} cose da guardare.")
        sys.exit(1)
    print("Tutto torna.")


if __name__ == "__main__":
    main()
