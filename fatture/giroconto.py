"""
fatture/giroconto.py — Dall'incasso ai due conti.

IL PASSAGGIO CHE MANCAVA
------------------------
Quando una fattura viene incassata i soldi arrivano tutti sul conto
P.IVA, ma non sono tutti tuoi: INPS e imposta sostitutiva maturano
all'incasso, e vanno lasciati dove sono. Il resto e' stipendio, e sta
sul conto personale.

Finora l'app sapeva calcolare la quota (card "Da accantonare") ma la
scelta dello scenario era solo visiva: nessuna traccia di cosa avessi
deciso, e il denaro non si muoveva. Qui quel gesto diventa un fatto
registrato:

    incasso lordo sul conto P.IVA        5.000,00
      - accantonamento (scenario scelto) 1.508,15   resta su P.IVA
      = giroconto al personale           3.491,85   si sposta

Due righe, una per conto, scritte insieme:

  b2f_spese_piva  tipo=giroconto, categoria=giroconto_personale
                  -> uscita dal conto P.IVA
  spese           tipo=entrata
                  -> arrivo sul conto personale

Il giroconto NON e' una spesa deducibile ne' un ricavo: e' denaro che
cambia conto. Per questo sul lato P.IVA usa `tipo=giroconto`, che i
calcoli fiscali gia' ignorano (contano solo le uscite), e una categoria
dedicata.

Rotte JSON:
  POST   /fatture/api/fatture/<int:fid>/giroconto  -> esegue
  DELETE /fatture/api/fatture/<int:fid>/giroconto  -> annulla
"""
from datetime import date

from flask import request, jsonify

from . import fatture_bp
from . import accantonamento as acc
from .costanti import CATEGORIA_GIROCONTO, normalizza_stato
from shared.supabase_client import get_client, is_configured


def _sb_or_503():
    if not is_configured():
        return None, (jsonify({"error": "supabase not configured"}), 503)
    return get_client(), None


def _carica(sb, fid):
    try:
        r = sb.table("b2f_fatture").select("*").eq("id", fid).single().execute()
        if not r.data:
            return None, (jsonify({"error": "fattura non trovata"}), 404)
        return r.data, None
    except Exception as e:
        return None, (jsonify({"error": f"fattura non trovata: {str(e)[:120]}"}), 404)


# La scrittura sul conto personale passa dal suo livello dati
# (spese/dati.py): li' stanno le regole di quella tabella — mese e anno
# obbligatori, id col primo libero, categoria come rimando e non come
# testo. Riscriverle qui significherebbe tenerne due copie allineate a
# mano, e prima o poi divergono.


def calcola(f: dict, param: dict, scenario: str,
            incassato_anno: float = 0.0,
            importo_personalizzato=None) -> dict:
    """
    Quanto resta sul conto P.IVA e quanto si sposta sul personale.

    `importo_personalizzato` permette di scavalcare lo scenario con una
    cifra decisa a mano: la quota da accantonare resta comunque limitata
    all'incasso, perche' non si puo' mettere da parte piu' di quanto e'
    arrivato.
    """
    lordo = float(f.get("totale") or 0)
    s = acc.scomponi(lordo, param, fatturato_riferimento=incassato_anno)

    if importo_personalizzato is not None:
        accantonato = float(importo_personalizzato)
    else:
        accantonato = float(s["importi"][scenario])

    accantonato = round(min(max(accantonato, 0.0), lordo), 2)
    return {
        "lordo": round(lordo, 2),
        "scenario": scenario,
        "accantonamento": accantonato,
        "giroconto": round(lordo - accantonato, 2),
        "scomposizione": s,
    }


@fatture_bp.post("/api/fatture/<int:fid>/giroconto")
def api_giroconto_esegui(fid):
    """
    Registra la decisione di accantonamento e sposta la quota tua sul
    conto personale, con due movimenti collegati.

    Le guardie stanno qui e non solo nell'interfaccia: un doppio invio
    o una chiamata diretta non devono poter duplicare lo spostamento.
    """
    sb, err = _sb_or_503()
    if err:
        return err

    f, errore = _carica(sb, fid)
    if errore:
        return errore

    stato = normalizza_stato(f.get("stato"))
    if stato != "incassata":
        return jsonify({
            "error": ("Il giroconto si fa a incasso avvenuto: fino ad allora "
                      "i soldi non sono ancora sul conto P.IVA. Segna prima "
                      "la fattura come incassata."),
            "stato": stato,
        }), 409

    if f.get("data_giroconto"):
        return jsonify({
            "error": ("Il giroconto di questa fattura è già stato registrato. "
                      "Annullalo se devi rifarlo con un altro scenario."),
            "data_giroconto": f.get("data_giroconto"),
        }), 409

    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario") or "consigliato"
    if scenario not in acc.SCENARI:
        return jsonify({"error": f"scenario non valido: {scenario}"}), 400

    personalizzato = body.get("accantonamento")
    if personalizzato in ("", None):
        personalizzato = None
    else:
        try:
            personalizzato = float(personalizzato)
        except (TypeError, ValueError):
            return jsonify({"error": "importo di accantonamento non valido"}), 400

    quando = body.get("data") or f.get("data_incasso") or date.today().isoformat()

    # Base per spalmare i costi fissi: l'incassato dell'anno della fattura.
    from .fiscale import get_parametri
    param = get_parametri(sb)
    anno_f = int((f.get("data") or "")[:4] or date.today().year)
    try:
        r = (sb.table("b2f_fatture").select("totale").eq("stato", "incassata")
               .gte("data_incasso", f"{anno_f}-01-01")
               .lte("data_incasso", f"{anno_f}-12-31").execute())
        incassato_anno = sum(float(x.get("totale") or 0) for x in (r.data or []))
    except Exception:
        incassato_anno = 0.0

    calc = calcola(f, param, scenario, incassato_anno, personalizzato)
    if calc["giroconto"] <= 0:
        return jsonify({
            "error": ("Con questo scenario l'intero incasso resta accantonato: "
                      "non c'è nulla da spostare sul conto personale."),
        }), 400

    numero = f.get("numero") or f"#{fid}"
    etichetta = acc.ETICHETTE[scenario][0]

    # --- 0) Il lordo, sul conto P.IVA, se non c'e' gia' -------------------
    # La ripartizione sposta la tua quota fuori dal conto P.IVA: se il
    # lordo incassato non ci e' mai arrivato (perche' non si e' passati
    # da "Registra entrata su P.IVA"), il saldo di quel conto finirebbe
    # sotto della cifra spostata, come se il cliente non avesse pagato.
    # Qui la ripartizione si basta da sola, e se l'incasso era gia' stato
    # registrato a mano non lo duplica.
    id_entrata = f.get("spesa_piva_id")
    id_entrata_nuova = None   # solo se creata ora: e' quella da disfare in caso di rollback
    if not id_entrata:
        from .storico import cliente_label
        riga_entrata = {
            "data":        quando,
            "tipo":        "entrata",
            "importo":     calc["lordo"],
            "descrizione": f"Fattura {numero} — {cliente_label(f)}",
            "categoria":   "fatturato",
            "fattura_id":  fid,
        }
        try:
            ins_e = sb.table("b2f_spese_piva").insert(riga_entrata).execute()
            id_entrata = id_entrata_nuova = (ins_e.data or [{}])[0].get("id")
            if not id_entrata:
                return jsonify({"error": "insert incasso P.IVA senza id di ritorno"}), 500
        except Exception as e:
            return jsonify({"error": f"errore nel registrare l'incasso sul conto "
                                     f"P.IVA: {str(e)[:200]}"}), 500

    # --- 1) Uscita dal conto P.IVA ---------------------------------------
    riga_piva = {
        "data":        quando,
        "tipo":        "giroconto",
        "importo":     calc["giroconto"],
        "descrizione": f"Giroconto al personale — fattura {numero}",
        "categoria":   CATEGORIA_GIROCONTO,
        "fattura_id":  fid,
        "note":        (f"Scenario {etichetta}: accantonati "
                        f"€ {calc['accantonamento']:.2f} di € {calc['lordo']:.2f}."),
    }
    try:
        ins = sb.table("b2f_spese_piva").insert(riga_piva).execute()
        id_piva = (ins.data or [{}])[0].get("id")
        if not id_piva:
            return jsonify({"error": "insert P.IVA senza id di ritorno"}), 500
    except Exception as e:
        return jsonify({"error": f"errore sul conto P.IVA: {str(e)[:200]}"}), 500

    # --- 2) Entrata sul conto personale -----------------------------------
    # Import qui dentro e non in testa: `fatture` e `spese` sono due
    # blueprint indipendenti, e legarli al caricamento del modulo
    # imporrebbe un ordine di import fra i due.
    from spese import dati as personale

    # `tipo=entrata` e non `giroconto`: v_risparmi_mese conta le entrate,
    # e un movimento marcato giroconto resterebbe fuori dal budget.
    esito = personale.crea(sb, {
        "data":              quando,
        "tipo":              "entrata",
        "importo":           calc["giroconto"],
        "descrizione":       f"Giroconto da P.IVA — fattura {numero}",
        "metodo_pagamento":  "Giroconto",
        "categoria_link_id": personale.link_categoria(
            sb, personale.CATEGORIA_GIROCONTO),
    })
    if esito.get("error") or not esito.get("id"):
        # Rollback: senza la riga sul personale il giroconto sarebbe monco,
        # e il conto P.IVA risulterebbe svuotato verso il nulla. Se il
        # lordo era stato registrato qui sopra (non gia' prima), via anche
        # quello: altrimenti resterebbe un incasso senza ripartizione.
        for tabella, rid in (("b2f_spese_piva", id_piva), ("b2f_spese_piva", id_entrata_nuova)):
            try:
                if rid:
                    sb.table(tabella).delete().eq("id", rid).execute()
            except Exception:
                pass
        return jsonify({"error": "errore sul conto personale: "
                                 f'{esito.get("error") or "nessun id di ritorno"}'}), 500
    id_pers = esito["id"]

    # --- 3) La decisione, sulla fattura -----------------------------------
    upd = {
        "accantonamento_scenario": scenario,
        "accantonamento_importo":  calc["accantonamento"],
        "giroconto_importo":       calc["giroconto"],
        "data_giroconto":          quando,
        "giroconto_piva_id":       id_piva,
        "giroconto_personale_id":  id_pers,
        "spesa_piva_id":           id_entrata,
    }
    try:
        sb.table("b2f_fatture").update(upd).eq("id", fid).execute()
    except Exception as e:
        for tabella, rid in (("b2f_spese_piva", id_piva), ("spese", id_pers),
                             ("b2f_spese_piva", id_entrata_nuova)):
            try:
                if rid:
                    sb.table(tabella).delete().eq("id", rid).execute()
            except Exception:
                pass
        return jsonify({"error": f"aggiornamento fattura fallito: {str(e)[:200]}"}), 500

    return jsonify({
        "ok": True,
        "scenario": scenario,
        "accantonamento": calc["accantonamento"],
        "giroconto": calc["giroconto"],
        "data": quando,
        "movimento_piva_id": id_piva,
        "movimento_personale_id": id_pers,
    })


@fatture_bp.delete("/api/fatture/<int:fid>/giroconto")
def api_giroconto_annulla(fid):
    """
    Annulla il giroconto: toglie le due righe dai conti e libera la
    fattura, cosi' si puo' rifare con un altro scenario.
    """
    sb, err = _sb_or_503()
    if err:
        return err

    f, errore = _carica(sb, fid)
    if errore:
        return errore

    if not f.get("data_giroconto"):
        return jsonify({"error": "nessun giroconto da annullare"}), 404

    problemi = []
    for tabella, campo in (("b2f_spese_piva", "giroconto_piva_id"),
                           ("spese", "giroconto_personale_id")):
        rid = f.get(campo)
        if not rid:
            continue
        try:
            sb.table(tabella).delete().eq("id", rid).execute()
        except Exception as e:
            problemi.append(f"{tabella}: {str(e)[:80]}")

    if problemi:
        return jsonify({
            "error": ("Non sono riuscito a togliere tutti i movimenti; la "
                      "fattura resta collegata per non perderne traccia. "
                      + " | ".join(problemi)),
        }), 500

    upd = {k: None for k in ("accantonamento_scenario", "accantonamento_importo",
                             "giroconto_importo", "data_giroconto",
                             "giroconto_piva_id", "giroconto_personale_id")}
    try:
        sb.table("b2f_fatture").update(upd).eq("id", fid).execute()
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500

    return jsonify({"ok": True})
