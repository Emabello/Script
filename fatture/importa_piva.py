"""
fatture/importa_piva.py — L'import dell'estratto WeBank del conto P.IVA.

Lo stesso file e la stessa pagina del conto personale (lettura con
`spese/importa.py::parse_bank_xlsx`, revisione con il pannello comune di
`shared/importazione.py`), con le categorie della P.IVA al posto di quelle
del personale.

DUE COSE CHE DAL FILE NON SI SALVANO
------------------------------------
Sul conto P.IVA due tipi di movimento li scrive gia' qualcun altro, e
importarli dall'estratto li conterebbe due volte:

  * **i giroconti verso il personale**: la ripartizione della fattura
    scrive la sua uscita dal conto P.IVA, specchio di quanto e' davvero
    arrivato sul personale (README §8.18). In banca quel giroconto sono
    piu' bonifici (tranche, rientri); qui e' una riga netta. Si mostrano
    spenti, bloccati, con il motivo.
  * **gli incassi delle fatture**: li registra «registra l'incasso» sulla
    fattura, con il collegamento alla fattura stessa. Dal file arrivano
    come sospetti (stesso importo, stessi giorni): spenti, ma si possono
    riaccendere se davvero non sono stati registrati.

Rotte HTML:  GET  /conti/webank/piva/importa
Rotte JSON:  POST /fatture/api/spese-piva/importa/carica  (multipart)
             POST /fatture/api/spese-piva/importa/salva
"""
import re
from datetime import date

from flask import Response, jsonify, request

from . import fatture_bp
from .costanti import CATEGORIA_GIROCONTO, CATEGORIE_SPESE_PIVA
from shared import importazione as IM
from shared import suggerimenti as SG
from shared.supabase_client import get_client, is_configured
from shared.theme import render_page

# Le parole con cui l'estratto scrive un trasferimento verso un conto tuo.
_GIROCONTO = re.compile(r"trasferimento a conto|disp\.?\s*giro|giroconto|"
                        r"trasferimento verso|bonifico a favore di emanuele", re.I)


def _sb():
    return get_client() if is_configured() else None


def _voci() -> list[dict]:
    return [{"valore": k, "nome": lbl} for k, lbl in CATEGORIE_SPESE_PIVA]


def _esistenti(sb, righe: list[dict]) -> list[dict]:
    """I movimenti P.IVA negli anni del file (± uno), con il giroconto come uscita."""
    anni = {int(str(r.get("data"))[:4]) for r in righe
            if str(r.get("data") or "")[:4].isdigit()}
    if not anni:
        return []
    dal, al = f"{min(anni) - 1}-01-01", f"{max(anni) + 1}-12-31"
    out, offset = [], 0
    while True:
        try:
            r = (sb.table("b2f_spese_piva").select("data,tipo,importo,descrizione")
                 .gte("data", dal).lte("data", al).order("data").order("id")
                 .range(offset, offset + 999).execute())
            pagina = r.data or []
        except Exception:
            break
        out.extend(pagina)
        if len(pagina) < 1000:
            break
        offset += 1000
    return [{**x, "tipo": "uscita" if x.get("tipo") == "giroconto" else x.get("tipo")}
            for x in out]


def _incassi_fatture(sb) -> list[dict]:
    """Le fatture incassate, per riconoscere il loro bonifico nel file."""
    try:
        r = (sb.table("b2f_fatture").select("numero,totale,data_incasso")
             .not_.is_("data_incasso", "null").execute())
        return r.data or []
    except Exception:
        try:
            r = sb.table("b2f_fatture").select("numero,totale,data_incasso").execute()
            return [f for f in (r.data or []) if f.get("data_incasso")]
        except Exception:
            return []


def _blocca_e_segnala(sb, righe: list[dict]) -> dict:
    """I giroconti non si importano; gli incassi delle fatture si segnalano."""
    fatture = _incassi_fatture(sb)
    giroconti = incassi = 0
    for r in righe:
        if r.get("presente"):
            continue
        testo = f'{r.get("descrizione") or ""} {r.get("descrizione_raw") or ""}'
        if r.get("tipo") == "uscita" and _GIROCONTO.search(testo):
            r["presente"] = True
            r["categoria"] = CATEGORIA_GIROCONTO
            r["nota"] = ("giroconto verso il personale: lo registra la ripartizione "
                         "della fattura, dal file si conterebbe due volte")
            giroconti += 1
            continue
        if r.get("tipo") != "entrata":
            continue
        for f in fatture:
            try:
                uguale = abs(float(f.get("totale") or 0) - float(r.get("importo") or 0)) < 0.01
                giorni = abs((date.fromisoformat(str(f["data_incasso"])[:10])
                              - date.fromisoformat(str(r["data"])[:10])).days)
            except (TypeError, ValueError, KeyError):
                continue
            if uguale and giorni <= IM.TOLLERANZA_GIORNI:
                r["sospetto"] = (f'è l\'incasso della fattura {f.get("numero") or ""}: '
                                 f'si registra dalla fattura, così resta collegato')
                r["categoria"] = "fatturato"
                incassi += 1
                break
    return {"giroconti": giroconti, "incassi": incassi}


@fatture_bp.get("/conti/webank/piva/importa")
def piva_importa_pagina():
    from spese.importa import pagina_upload
    breadcrumb = [("Conti", "/conti"), ("WeBank P.IVA", "/conti/webank/piva"),
                  ("Importa da banca", "")]
    if _sb() is None:
        corpo = '<div class="notice warn">Supabase non configurato.</div>'
    else:
        corpo = pagina_upload(
            "Importa l'estratto WeBank P.IVA",
            "Il file .xlsx esportato da WeBank per il conto della partita IVA — "
            "lo stesso formato del conto personale.", ".xlsx,.xls",
            "/fatture/api/spese-piva/importa/carica")
        corpo += IM.pannello(_voci(), "/fatture/api/spese-piva/importa/salva",
                             obbligatoria=True)
        corpo += '<div id="toast" class="toast"></div>'
    return Response(render_page(section="conti-piva", eyebrow="Importa",
                                title_html='Importa da <em>banca</em>',
                                content=corpo, breadcrumb=breadcrumb),
                    mimetype="text/html")


@fatture_bp.post("/fatture/api/spese-piva/importa/carica")
def api_piva_importa_carica():
    from spese.importa import parse_bank_xlsx
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "nessun file caricato"}), 400
    try:
        esito = parse_bank_xlsx(f.read())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"file non leggibile: {str(e)[:200]}"}), 400
    righe = esito["movimenti"]
    avvisi = []
    if esito["scartate"]:
        avvisi.append({"classe": "warn", "testo":
            f'{esito["scartate"]} righe del file non sono state lette (data o importo '
            f'non riconosciuti).'})
    sb = _sb()
    if sb is not None:
        try:
            conti = IM.segna_doppioni(_esistenti(sb, righe), righe)
            speciali = _blocca_e_segnala(sb, righe)
            proposte = IM.proponi(SG.storico_piva(sb), righe,
                                  {k for k, _l in CATEGORIE_SPESE_PIVA})
            if conti["presenti"]:
                avvisi.append({"testo": f'{conti["presenti"]} righe sono già registrate.'})
            if speciali["giroconti"]:
                avvisi.append({"testo": f'{speciali["giroconti"]} giroconti verso il personale '
                                        f'restano fuori: li scrive la ripartizione della fattura.'})
            if speciali["incassi"]:
                avvisi.append({"classe": "warn", "testo":
                    f'{speciali["incassi"]} entrate sono l\'incasso di una fattura: '
                    f'registrale dalla fattura, così restano collegate.'})
            if proposte:
                avvisi.append({"testo": f"{proposte} righe hanno la categoria proposta dallo storico."})
        except Exception:
            pass
    return jsonify({"movimenti": righe, "avvisi": avvisi})


@fatture_bp.post("/fatture/api/spese-piva/importa/salva")
def api_piva_importa_salva():
    sb = _sb()
    if sb is None:
        return jsonify({"error": "supabase not configured"}), 503
    body = request.get_json(silent=True)
    righe = body.get("righe") if isinstance(body, dict) else None
    if not isinstance(righe, list) or not righe:
        return jsonify({"error": "nessuna riga da salvare"}), 400
    righe = [dict(r) for r in righe if isinstance(r, dict)]
    for r in righe:
        r.pop("presente", None)
    IM.segna_doppioni(_esistenti(sb, righe), righe)
    validi = {k for k, _l in CATEGORIE_SPESE_PIVA}

    salvate, errori, duplicati = [], [], []
    for r in righe:
        idx = r.get("idx")
        if r.get("presente"):
            duplicati.append({"idx": idx, "nota": "già registrato"})
            continue
        cat = r.get("categoria")
        if cat not in validi:
            errori.append({"idx": idx, "errore": "categoria mancante o non valida"})
            continue
        if cat == CATEGORIA_GIROCONTO:
            # Il giroconto ha due righe collegate (P.IVA e personale): si
            # registra dalla fattura o dal form, mai da un file.
            errori.append({"idx": idx, "errore": "i giroconti si registrano dalla fattura"})
            continue
        try:
            imp = round(abs(float(r.get("importo"))), 2)
            quando = date.fromisoformat(str(r.get("data"))[:10]).isoformat()
        except (TypeError, ValueError):
            errori.append({"idx": idx, "errore": "data o importo non validi"})
            continue
        if r.get("tipo") not in ("entrata", "uscita") or not imp:
            errori.append({"idx": idx, "errore": "tipo o importo non validi"})
            continue
        try:
            sb.table("b2f_spese_piva").insert({
                "data": quando, "importo": imp, "tipo": r["tipo"],
                "descrizione": (r.get("descrizione") or "Movimento da estratto")[:200],
                "categoria": cat, "note": "Import banca",
            }).execute()
            salvate.append(idx)
        except Exception as e:
            errori.append({"idx": idx, "errore": str(e)[:120]})
    return jsonify({"salvate": salvate, "errori": errori, "duplicati": duplicati})
