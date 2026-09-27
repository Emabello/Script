"""
Il banco di prova dei suggerimenti di categoria, sullo storico vero.

    python3 tools/verifica_suggerimenti.py                 # dal database (SUPABASE_URL/KEY)
    python3 tools/verifica_suggerimenti.py --file storico.txt

Il file, se lo si usa, ha una riga per movimento:
    id|data|tipo|importo|descrizione|Categoria › Sottocategoria

Tre prove, dalla piu' facile alla piu' onesta:

  memoria        ogni movimento, con tutto lo storico a disposizione. Deve
                 fare 100%: e' «la formula riproduce ogni decisione che hai
                 gia' preso». Sotto il 100% la formula ha un buco.
  leave-one-out  ogni movimento nascosto a turno e indovinato dagli altri.
  cronologico    ogni movimento indovinato solo da quelli arrivati PRIMA:
                 e' quello che l'import avrebbe proposto quel giorno.

Per le ultime due conta anche la categoria principale (Personale, Viaggi,
Fisso…), che e' quella che decide il budget: la sottocategoria allo stesso
bancone (Caffè o Cibo al McDonald's) e' spesso una scelta del momento.

In coda, le INCOERENZE: stesso esercente, stesso importo, stessa direzione
e categorie diverse. Nessuna formula le indovina tutte, perche' la risposta
giusta e' due risposte; sistemarle nei dati e' il modo di alzare le prove.

Esce con codice 1 se la prova di memoria non fa 100%.
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import suggerimenti as S  # noqa: E402


def da_file(percorso: str) -> list[dict]:
    righe = []
    for riga in open(percorso, encoding="utf-8"):
        pezzi = riga.rstrip("\n").split("|")
        if len(pezzi) != 6:
            continue
        i, d, t, imp, desc, cat = pezzi
        righe.append({"id": int(i), "data": d, "tipo": t, "importo": float(imp),
                      "descrizione": desc, "etichetta": cat, "nome": cat})
    return righe


def dal_database() -> list[dict]:
    from shared.supabase_client import get_client
    client = get_client()
    if client is None:
        sys.exit("SUPABASE_URL e SUPABASE_KEY non impostate: usa --file.")
    s = S.storico_personale(client)
    righe = []
    for _k, _t, _p, esempi in s.gruppi:
        for n, (tipo, imp, etichetta, quando, desc) in enumerate(esempi):
            righe.append({"id": len(righe), "data": quando, "tipo": tipo, "importo": imp,
                          "descrizione": desc, "etichetta": etichetta,
                          "nome": s.nomi.get(etichetta, str(etichetta))})
    return righe


def principale(nome: str) -> str:
    return str(nome).split(" › ")[0]


def prova(nome, righe, candidati, prevedi):
    n = proposte = giuste = cat = presel = presel_ok = 0
    for r in candidati:
        n += 1
        p = prevedi(r)
        if not p:
            continue
        proposte += 1
        ok = p["etichetta"] == r["etichetta"]
        giuste += ok
        cat += principale(p["nome"]) == principale(r["nome"])
        if p["sicura"]:
            presel += 1
            presel_ok += ok
    q = lambda a, b: f"{a / b:.1%}" if b else "—"  # noqa: E731
    print(f"  {nome:14} proposte {proposte}/{n}  giuste {q(giuste, proposte)} "
          f"(categoria principale {q(cat, proposte)})  "
          f"preselezionate {presel}, giuste {q(presel_ok, presel)}")
    return giuste, proposte


def main():
    if "--file" in sys.argv:
        righe = da_file(sys.argv[sys.argv.index("--file") + 1])
    else:
        righe = dal_database()
    candidati = [r for r in righe if len(S.chiave(r["descrizione"])) >= 3]
    print(f"\n{len(righe)} movimenti, {len(candidati)} con una descrizione utilizzabile\n")

    tutto = S.Storico(righe)
    giuste, proposte = prova("memoria", righe, candidati,
                             lambda r: tutto.suggerisci(r["descrizione"], r["importo"],
                                                        r["tipo"], quando=r["data"]))
    prova("leave-one-out", righe, candidati,
          lambda r: S.Storico([x for x in righe if x is not r]).suggerisci(
              r["descrizione"], r["importo"], r["tipo"], quando=r["data"]))
    ordinate = sorted(righe, key=lambda x: (x["data"], x["id"]))
    prova("cronologico", righe, candidati,
          lambda r: S.Storico([x for x in ordinate
                               if (x["data"], x["id"]) < (r["data"], r["id"])]).suggerisci(
              r["descrizione"], r["importo"], r["tipo"], quando=r["data"]))

    gruppi, quanti = defaultdict(Counter), Counter()
    for r in candidati:
        k = (S.chiave(r["descrizione"]), r["tipo"], round(r["importo"], 2))
        gruppi[k][r["nome"]] += 1
        quanti[k] += 1
    incoerenti = [(k, c) for k, c in gruppi.items() if len(c) > 1]
    print(f"\nIncoerenze — stesso esercente, stesso importo, categorie diverse: "
          f"{len(incoerenti)} ({sum(quanti[k] for k, _c in incoerenti)} movimenti)")
    for (k, tipo, imp), c in sorted(incoerenti, key=lambda x: -quanti[x[0]])[:30]:
        print(f"  {k[:30]:30} {tipo:7} € {imp:8.2f}  " +
              ", ".join(f"{nome} ×{v}" for nome, v in c.most_common()))

    print()
    if giuste < proposte or proposte < len(candidati):
        print("La prova di memoria non fa 100%: la formula non riproduce le decisioni già prese.")
        sys.exit(1)
    print("Memoria 100%: ogni decisione già presa viene riproposta uguale.")


if __name__ == "__main__":
    main()
