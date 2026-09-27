"""
Controlli sul conto Revolut: la lettura dell'estratto e i suoi movimenti.

    python3 tools/verifica_revolut.py

Costruisce un estratto consolidato FINTO nella stessa forma di quello vero
— un CSV infilato nella colonna A di un xlsx, con gli accenti e il simbolo
dell'euro passati due volte per la codifica sbagliata — e ci fa passare
sopra tutto il giro: lettura dei saldi e dei movimenti, quadratura
apertura + movimenti = chiusura, categorie proposte, doppioni, salvataggio,
reimport di un estratto che si sovrappone, saldo «fotografia + movimenti
dopo», ponte con i bonifici WeBank.

Non tocca il database: gira sul finto client di tools/preview.py.
Esce con codice 1 se qualcosa non torna.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl  # noqa: E402

import preview  # noqa: E402  monta l'app sul finto client
from preview import DB, _FakeClient  # noqa: E402
from spese import revolut as R  # noqa: E402
from spese import revolut_movimenti as RM  # noqa: E402

PROBLEMI: list[str] = []


def controlla(cond, msg):
    print(("  ok     " if cond else "  NO     ") + msg)
    if not cond:
        PROBLEMI.append(msg)


def _storpia(testo: str) -> str:
    """UTF-8 letto come cp1252: "à" -> "Ã ", "€" -> "â‚¬". Come il file vero."""
    return testo.encode("utf-8").decode("cp1252", errors="replace")


def estratto(righe_csv: list[str]) -> bytes:
    """Un xlsx con una riga CSV per cella in colonna A, storpiata."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for riga in righe_csv:
        ws.append([_storpia(riga)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Il periodo 01/08 -> 31/08/2026. Liquidita': 100,00 di apertura, poi un
# bonifico da WeBank, due caffe' IDENTICI lo stesso giorno (devono restare
# due movimenti), una cena, lo spostamento nel deposito, un pagamento in
# formato "12.50" col punto. Deposito: 8.000 di apertura, lo spostamento
# in arrivo, gli interessi. Un conto in dollari che va saltato.
RIGHE = [
    "Estratto conto consolidato",
    "Emanuele Bellotti",
    "Riepiloghi dei conti correnti",
    "Conto personale (EUR)",
    "Descrizione,Importo",
    '"Saldo di apertura","100,00€"',
    '"Denaro in uscita","559,90€"',
    '"Denaro in entrata","770,98€"',
    '"Saldo di chiusura","311,08€"',
    "Conto personale (USD)",
    '"Saldo di chiusura","10,00$","9,20€"',
    "Riepiloghi dei conti deposito",
    "Deposito senza vincoli (EUR)",
    '"Saldo di apertura","8.000,00€"',
    '"Saldo di chiusura","8.503,21€"',
    "Riepiloghi degli investimenti",
    "Conto investimenti (EUR)",
    '"Dividendi","1,20€"',
    "Estratti conto dei conti correnti",
    "Conto personale (EUR)",
    "Data,Descrizione,Denaro in uscita,Denaro in entrata,Saldo",
    '"2 ago 2026","Bonifico da Emanuele Bellotti",,"770,98€","870,98€"',
    '"3 ago 2026","Caffè Centrale","1,20€",,"869,78€"',
    '"3 ago 2026","Caffè Centrale","1,20€",,"868,58€"',
    '"10 ago 2026","Trattoria Da Nino","45,00€",,"823,58€"',
    '"11 ago 2026","Al Deposito senza vincoli","500,00€",,"323,58€"',
    '"20 ago 2026","Amazon","12.50",,"311,08€"',
    "Conto personale (USD)",
    "Data,Descrizione,Denaro in uscita,Denaro in entrata,Saldo",
    '"5 ago 2026","App Store","10,00$",,"10,00$"',
    "Estratti conto dei conti deposito",
    "Deposito senza vincoli (EUR)",
    "Data,Descrizione,Denaro in uscita,Denaro in entrata,Saldo",
    '"11 ago 2026","Dal conto personale",,"500,00€","8.500,00€"',
    '"31 ago 2026","Interessi maturati",,"3,21€","8.503,21€"',
]


def main():
    print("\n== numeri e date")
    controlla(R._importo("8.525,39€") == 8525.39, "8.525,39€ -> 8525.39")
    controlla(R._importo("12.50") == 12.5, "12.50 col punto -> 12.5 (non 1250)")
    controlla(R._importo("1.234") == 1234, "1.234 -> 1234 (migliaia)")
    controlla(R._importo("") is None, "cella vuota -> None")
    controlla(R._importo("13.600,00 EGP") == 13600, "13.600,00 EGP -> 13600 (codice valuta)")
    controlla(R._importo("-428¥") == -428, "-428¥ -> -428")
    controlla(str(R._data("3 ago 2026")) == "2026-08-03", "3 ago 2026")
    controlla(str(R._data("03/08/2026")) == "2026-08-03", "03/08/2026")
    controlla(str(R._data("2026-08-03 10:12")) == "2026-08-03", "2026-08-03 10:12")

    print("\n== lettura dell'estratto")
    file = estratto(RIGHE)
    letto = R.parse_estratto(file, "consolidated-statement_20260801_20260831_it.xlsx")
    controlla(letto["data"] == "2026-08-31", f'data dal nome del file ({letto["data"]})')
    controlla(letto["conto"] == round(311.08 + 9.20, 2),
              f'liquidità = euro + controvalore del conto in dollari ({letto["conto"]})')
    controlla(letto["risparmi"] == 8503.21, f'risparmi ({letto["risparmi"]})')
    mov = letto["movimenti"]
    controlla(len(mov) == 8, f"8 movimenti in euro letti ({len(mov)})")
    controlla(all(m["importo"] > 0 for m in mov), "importi tutti positivi")
    caffe = [m for m in mov if "Caff" in m["descrizione"]]
    controlla(len(caffe) == 2 and caffe[0]["chiave"] != caffe[1]["chiave"],
              "due caffè identici restano due movimenti, con impronte diverse")
    controlla(any(m["descrizione"] == "Caffè Centrale" for m in mov),
              "gli accenti tornano a posto")
    amazon = next((m for m in mov if m["descrizione"] == "Amazon"), {})
    controlla(amazon.get("importo") == 12.5, "l'importo col punto resta 12,50")
    controlla({m["sezione"] for m in mov} == {"conto", "risparmi"},
              "sezioni liquidità e deposito riconosciute")
    controlla(any("valuta" in a for a in letto["avvisi"]),
              "il movimento in dollari è saltato, e lo dice")
    q = {x["nome"]: x for x in letto["quadrature"]}
    controlla(q.get("Conto personale", {}).get("ok"),
              "liquidità: apertura + entrate − uscite = chiusura")
    controlla(q.get("Deposito senza vincoli", {}).get("ok"),
              "deposito: apertura + entrate − uscite = chiusura")

    # I titoli come li scrive il file vero: «<qualcosa> Riepiloghi»,
    # «<qualcosa> Estratti conto». Stesso contenuto, stessi numeri.
    vero = [{"Riepiloghi dei conti correnti": "Conti correnti Riepiloghi",
             "Riepiloghi dei conti deposito": "Conti deposito Riepiloghi",
             "Riepiloghi degli investimenti": "Investimenti Riepiloghi",
             "Estratti conto dei conti correnti": "Conti correnti Estratti conto",
             "Estratti conto dei conti deposito": "Conti deposito Estratti conto",
             }.get(r, r) for r in RIGHE]
    letto_v = R.parse_estratto(estratto(vero), "x.xlsx")
    controlla((letto_v["conto"], letto_v["risparmi"], len(letto_v["movimenti"]))
              == (letto["conto"], letto["risparmi"], 8),
              "titoli in coda («Conti correnti Riepiloghi»): stessi numeri")

    print("\n== export dei movimenti («account-statement», CSV)")
    csv_mov = "\n".join([
        "Tipo,Prodotto,Data di inizio,Data di completamento,Descrizione,Importo,Costo,Valuta,State,Saldo",
        "Ricarica,Attuale,2026-08-01 09:00:00,2026-08-01 09:00:00,Bonifico da Emanuele Bellotti,300,0,EUR,COMPLETATO,300",
        "Pagamento con carta,Attuale,2026-08-02 12:00:00,2026-08-03 08:00:00,Caffè Centrale,-1.2,0,EUR,COMPLETATO,298.8",
        "Pagamento con carta,Attuale,2026-08-02 12:30:00,2026-08-03 08:00:00,Caffè Centrale,-1.2,0,EUR,COMPLETATO,297.6",
        "Cambia valuta,Attuale,2026-08-04 10:00:00,2026-08-04 10:00:00,Conversione in USD,-100,0,EUR,COMPLETATO,197.6",
        "Cambia valuta,Attuale,2026-08-04 10:00:00,2026-08-04 10:00:00,Conversione in USD,110,0,USD,COMPLETATO,110",
        "Pagamento con carta,Attuale,2026-08-05 10:00:00,2026-08-05 10:00:00,Diner NYC,-55,0,USD,COMPLETATO,55",
        "Pagamento,Attuale,2026-08-06 10:00:00,2026-08-06 10:00:00,Amazon,-20,0,EUR,ANNULLATO,",
        "Trasferimento,Attuale,2026-08-07 10:00:00,2026-08-07 10:00:00,A EUR Casa,-150,0,EUR,COMPLETATO,47.6",
        "Pagamento,Deposito,2026-08-07 10:00:00,2026-08-07 10:00:00,A EUR Casa,150,0,EUR,COMPLETATO,150",
        "Pagamento,Deposito,2026-08-08 10:00:00,2026-08-08 10:00:00,A EUR Vacanze,50,0,EUR,COMPLETATO,200",
        'Interessi,Deposito,2026-08-09 05:00:00,2026-08-09 05:00:00,"Interessi netti pagati nel conto ""Casa"" in data Aug 9, 2026",0.25,0.05,EUR,COMPLETATO,200.2',
    ])
    lm = R.parse_estratto(csv_mov.encode("utf-8"), "account-statement_2026-08-01_2026-08-31_it-it.csv")
    controlla(lm.get("formato") == "movimenti", "riconosciuto come export movimenti")
    controlla(lm["data"] == "2026-08-31", f'data dal nome del file ({lm["data"]})')
    controlla(lm["conto"] == 47.6, f'liquidità dal saldo progressivo ({lm["conto"]})')
    controlla(lm["risparmi"] == 200.2, f'deposito dal saldo progressivo ({lm["risparmi"]})')
    controlla(lm["salvadanai"] == {"casa": 150.2, "vacanze": 50.0},
              f'salvadanai ricostruiti dalle descrizioni ({lm["salvadanai"]})')
    controlla(all(q["ok"] for q in lm["quadrature"]), "tutte le quadrature tornano")
    mm = lm["movimenti"]
    controlla(not any(m["descrizione"] == "Amazon" for m in mm), "l'operazione annullata è saltata")
    interessi = next(m for m in mm if m["descrizione"].startswith("Interessi"))
    controlla(interessi["importo"] == 0.2, "interessi al netto della ritenuta (0,25 − 0,05)")
    diner = next(m for m in mm if m["descrizione"] == "Diner NYC")
    controlla(diner["importo"] == 50.0 and diner["valuta"] == "USD",
              f'dollari in euro al cambio della conversione ({diner["importo"]})')
    caffe_m = [m for m in mm if m["descrizione"] == "Caffè Centrale"]
    controlla(len(caffe_m) == 2 and caffe_m[0]["chiave"] != caffe_m[1]["chiave"],
              "due caffè identici restano due movimenti")
    # Lo stesso movimento letto dal consolidato e dall'export ha la stessa
    # impronta: reimportare con l'altro formato non raddoppia niente.
    controlla(R._impronta_movimento({"sezione": "risparmi", "data": "2026-08-09", "tipo": "entrata",
                                     "importo": 0.2, "descrizione":
                                     'Interessi netti pagati nel conto "Casa"'})
              == R._impronta_movimento(interessi),
              "impronta indipendente dal formato (senza «in data …»)")
    # In valuta i due formati convertono in euro con cambi diversi: conta
    # l'importo nella valuta, che e' lo stesso.
    controlla(R._impronta_movimento({"sezione": "conto", "data": "2026-08-05", "tipo": "uscita",
                                     "importo": 50.61, "valuta": "USD", "importo_valuta": 55.0,
                                     "descrizione": "Diner NYC"})
              == R._impronta_movimento(diner), "in valuta l'impronta non dipende dal cambio")

    print("\n== lo stesso estratto nell'altro formato non raddoppia")
    from shared import importazione as IM
    esistenti = [{"data": "2025-12-22", "tipo": "entrata", "importo": 60.0,
                  "descrizione": "Pagamento da parte di MARIO ROSSI"},
                 {"data": "2025-10-09", "tipo": "entrata", "importo": 2000.0,
                  "descrizione": "Pagamento da parte di MARIO ROSSI"}]
    file_ = [{"data": "2025-12-22", "tipo": "entrata", "importo": 60.0,
              "descrizione": "Revolut Bank UAB"},
             {"data": "2025-10-09", "tipo": "entrata", "importo": 2000.0,
              "descrizione": "Revolut Bank UAB"},
             {"data": "2025-12-23", "tipo": "entrata", "importo": 60.0,
              "descrizione": "Revolut Bank UAB"}]
    IM.segna_doppioni(esistenti, file_)
    controlla(file_[0].get("presente") and file_[1].get("presente"),
              "«Revolut Bank UAB» riconosciuto come il bonifico col nome (stesso giorno e importo)")
    controlla(not file_[2].get("presente"), "…ma non quello di un altro giorno")

    print("\n== una riga mancante si vede prima di salvare")
    monco = [r for r in RIGHE if "Trattoria" not in r]
    letto_m = R.parse_estratto(estratto(monco), "x.xlsx")
    qm = {x["nome"]: x for x in letto_m["quadrature"]}
    controlla(not qm["Conto personale"]["ok"] and qm["Conto personale"]["scarto"] == -45.0,
              f'scarto −45,00 segnalato ({qm["Conto personale"]["scarto"]})')
    controlla(any("non tornano" in a for a in letto_m["avvisi"]), "avviso sulla quadratura")

    print("\n== categorie proposte")
    client = _FakeClient()
    # La gemella: un bonifico «Risparmi» su WeBank dello stesso importo,
    # il giorno prima. E' lei che fa riconoscere l'entrata su Revolut.
    DB["spese"].append({"id": 900, "data": "2026-08-01", "importo": 770.98,
                        "tipo": "uscita", "descrizione": "Bonifico a Revolut",
                        "categoria": "Risparmi", "sottocategoria": None})
    DB["v_spese"].append(preview._riga_v_spese(DB["spese"][-1]))
    link = lambda cat, sub=None: preview._link_id(cat, sub)  # noqa: E731
    righe_pronte, avvisi = RM.prepara_import(client, mov)
    pronti = {m["descrizione"]: m for m in righe_pronte}
    controlla(pronti["Bonifico da Emanuele Bellotti"]["categoria"] == link("Risparmi")
              and pronti["Bonifico da Emanuele Bellotti"]["gemella"],
              "l'entrata con la gemella su WeBank -> Risparmi")
    controlla(pronti["Al Deposito senza vincoli"]["categoria"] == link(RM.CATEGORIA_INTERNO),
              "verso il deposito -> Giroconto Revolut")
    controlla(pronti["Dal conto personale"]["categoria"] == link(RM.CATEGORIA_INTERNO),
              "arrivo nel deposito -> Giroconto Revolut")
    controlla(pronti["Interessi maturati"]["categoria"] == link(RM.CATEGORIA_INTERESSI),
              "interessi -> Interessi")
    # La cena: nessun fatto la riconosce, ma lo storico si' — la stessa
    # trattoria, gia' categorizzata a luglio.
    cena = pronti["Trattoria Da Nino"]
    controlla(cena["categoria"] == link("Personale", "Ristoranti")
              and "simil" in cena["suggerimento"]["motivo"],
              f'la cena prende la categoria dallo storico ({cena.get("suggerimento")})')
    controlla(pronti["Amazon"]["categoria"] is None,
              "un esercente mai visto resta senza categoria")
    controlla(any("storico" in a["testo"] for a in avvisi), "l'avviso dice quante dallo storico")

    print("\n== salvataggio e reimport")
    prima = len(DB["b2f_revolut_movimenti"])
    righe = [{**m, "idx": i} for i, m in enumerate(righe_pronte)]
    esito = RM.importa(client, righe)
    controlla(len(esito.get("salvate", [])) == 8, f"8 salvati ({esito})")
    # Correggo a mano una categoria, poi reimporto lo stesso estratto: la
    # correzione deve restare, e niente deve raddoppiare.
    cena = next(r for r in DB["b2f_revolut_movimenti"]
                if r.get("descrizione") == "Trattoria Da Nino" and r.get("fonte") == "estratto")
    RM.aggiorna(client, cena["id"], {"categoria_link_id": link("Viaggi", "Hotel")})
    di_nuovo, _ = RM.prepara_import(client, mov)
    controlla(all(r.get("presente") for r in di_nuovo), "al reimport tutte risultano già registrate")
    esito2 = RM.importa(client, [{**m, "idx": i} for i, m in enumerate(di_nuovo)])
    controlla(not esito2.get("salvate") and len(esito2.get("duplicati", [])) == 8,
              f"reimport: 0 nuovi, 8 già presenti")
    controlla(len(DB["b2f_revolut_movimenti"]) == prima + 8, "nessun doppione in tabella")
    cena = next(r for r in DB["b2f_revolut_movimenti"] if r.get("id") == cena["id"])
    controlla(cena["categoria_link_id"] == link("Viaggi", "Hotel"),
              "la categoria corretta a mano resta dopo il reimport")
    controlla(RM.importa(client, []).get("error"), "lista vuota -> errore, non 500")
    controlla(len(RM.importa(client, [{"idx": 0, "chiave": "x", "tipo": "boh", "importo": 1,
                                       "data": "2026-08-01"}]).get("errori", [])) == 1,
              "riga con tipo non valido -> errore sulla riga")
    controlla(len(RM.importa(client, [{"idx": 0, "chiave": "y", "tipo": "uscita", "importo": 1,
                                       "data": "2026-08-01", "categoria": "inventata"}])
                  .get("errori", [])) == 1, "categoria inesistente -> errore sulla riga")

    print("\n== totali: i giroconti interni restano fuori")
    tutte = RM.tutti(client)
    agosto = RM.filtra(tutte, anno=2026, mese=8)
    t = RM.totali([r for r in agosto if not (r.get("chiave") or "").startswith("finta")])
    controlla(t["interni"] == 500.0, f"500 spostati nel deposito, contati a parte ({t['interni']})")
    controlla(t["entrate"] == round(770.98 + 3.21, 2),
              f"entrate senza il giroconto interno ({t['entrate']})")
    controlla(t["dal_webank"] == 770.98, f"netto da WeBank ({t['dal_webank']})")

    print("\n== saldo: fotografia + movimenti dopo")
    rev = R.saldo_revolut(client, "2026-09-30")
    foto = round(rev["conto"] + rev["risparmi"] + rev["investimenti"], 2)
    dopo = rev["dopo"]
    controlla(dopo["n"] > 0, f'{dopo["n"]} movimenti dopo la fotografia del {rev["data"]}')
    controlla(rev["saldo"] == round(foto + dopo["conto"] + dopo["risparmi"], 2),
              "saldo = fotografia + movimenti dopo")
    rev_foto = R.saldo_revolut(client, rev["data"])
    controlla(rev_foto["dopo"]["n"] == 0 and rev_foto["saldo"] == foto,
              "il giorno della fotografia il saldo è la fotografia")

    print("\n== il ponte con WeBank")
    p = RM.ponte(client)
    controlla(p is not None and p["coppie"], f'coppie trovate ({len(p["coppie"]) if p else 0})')
    sole_rev = {(r["data"], r["importo"]) for r in p["sole_revolut"]}
    controlla(("2026-08-02", 150.0) in sole_rev,
              "il 150 del 02/08 senza bonifico WeBank è segnalato")
    doppio = RM.abbina(
        [{"id": 1, "data": "2026-07-30", "tipo": "uscita", "importo": 770.98},
         {"id": 2, "data": "2026-08-28", "tipo": "uscita", "importo": 770.98}],
        [{"id": 10, "data": "2026-08-29", "tipo": "entrata", "importo": 770.98},
         {"id": 11, "data": "2026-07-31", "tipo": "entrata", "importo": 770.98}])
    controlla(sorted((w["id"], r["id"]) for w, r in doppio["coppie"]) == [(1, 11), (2, 10)],
              "due bonifici uguali a un mese di distanza: ognuno col suo")

    print()
    if PROBLEMI:
        print(f"{len(PROBLEMI)} cose da guardare.")
        sys.exit(1)
    print("Tutto torna.")


if __name__ == "__main__":
    main()
