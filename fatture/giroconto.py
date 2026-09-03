"""
fatture/giroconto.py — Dall'incasso ai due conti.

IL PASSAGGIO CHE MANCAVA
------------------------
Quando una fattura viene incassata i soldi arrivano tutti sul conto
P.IVA, ma non sono tutti tuoi: INPS e imposta sostitutiva maturano
all'incasso, e vanno lasciati dove sono. Il resto e' stipendio, e sta
sul conto personale.

    incasso lordo sul conto P.IVA        5.000,00
      - accantonamento (scenario scelto) 2.574,48   resta su P.IVA
      = da spostare sul personale        2.425,52   lo sposti tu

DECISIONE E FATTO SONO DUE COSE DIVERSE
---------------------------------------
Fino al 03/09/2026 la ripartizione scriveva **una** entrata sul conto
personale con l'importo deciso e la data della decisione, e la chiamava
fatta. Ma il bonifico lo fai tu dalla banca: quando vuoi, in quante
tranche vuoi, e puo' anche tornare indietro. Sulla fattura 2026/001 la
riga diceva 2.425,52 il 05/08; la banca aveva mosso 2.000,00 il 05/08,
1.491,85 il 13/08 e -1.068,33 il 02/09, cioe' 2.423,52 netti. Due euro
di scarto, in silenzio, sul saldo di un conto vero — la stessa forma
del guasto che sui risparmi era arrivato a 829,78 € (vedi
`spese/dati.py::saldo_conto`).

Da qui in poi le due cose stanno in due posti diversi:

  la DECISIONE  ->  sulla fattura: `accantonamento_scenario`,
                    `accantonamento_importo`, `giroconto_importo`,
                    `data_giroconto`. Non si muove piu'.
  il FATTO      ->  le righe di `spese` con categoria "Giroconto P.IVA"
                    agganciate alla fattura da `fattura_giroconto_id`
                    (README §8.18). Sono movimenti veri del conto,
                    arrivati dall'import della banca o registrati a mano:
                    quanti servono, con le date vere, anche in negativo
                    se una parte e' rientrata.

**La ripartizione non inventa piu' nessuna riga sul conto personale.**
Se il bonifico non l'hai ancora fatto, l'app lo dice ("in attesa") e il
saldo del personale resta quello che dice la banca. Quando il movimento
arriva, si aggancia da solo: `aggancia()` lo fa a ogni import, a ogni
ripartizione e ogni volta che premi "Ricontrolla la banca".

Il lato P.IVA e' lo specchio del lato personale, non della decisione:
`_sincronizza_piva()` tiene l'uscita dal conto P.IVA uguale a quello che
e' davvero arrivato sul personale. Se sul personale non e' arrivato
niente, sul conto P.IVA non esce niente — i soldi sono ancora li'.

Rotte JSON:
  POST   /fatture/api/fatture/<int:fid>/giroconto            -> decide
  DELETE /fatture/api/fatture/<int:fid>/giroconto            -> annulla
  POST   /fatture/api/fatture/<int:fid>/giroconto/aggancia   -> ricontrolla
  POST   /fatture/api/fatture/<int:fid>/giroconto/bonifico   -> registra a mano
"""
from datetime import date

from flask import request, jsonify

from . import fatture_bp
from . import accantonamento as acc
from .costanti import (CATEGORIA_GIROCONTO as CATEGORIA_PIVA,
                       ha_incassato, normalizza_stato)
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

    E non scende sotto la **rivalsa INPS** incassata con la fattura.
    Quella parte del corrispettivo non e' un tuo ricavo: e' il contributo
    previdenziale che il cliente ti ha girato perche' tu lo versi. I
    quattro scenari la coprono tutti abbondantemente (l'INPS
    sull'accantonamento vale circa il 17,5 % del lordo, la rivalsa il
    3,85 %), ma un importo scritto a mano potrebbe scenderci sotto e
    spostare sul personale denaro gia' destinato all'INPS.
    """
    lordo = float(f.get("totale") or 0)
    rivalsa = round(float(f.get("cassa_importo") or 0), 2)
    # L'anno della fattura, non quello di oggi: e' quello che decide se
    # i contributi erano gia' stati versati (e quindi deducibili).
    try:
        anno_f = int(str(f.get("data") or "")[:4])
    except (TypeError, ValueError):
        anno_f = None
    s = acc.scomponi(
        lordo, param, fatturato_riferimento=incassato_anno, rivalsa=rivalsa,
        bollo_addebitato=(f.get("bollo") or 0) if f.get("bollo_addebitato") else 0,
        anno=anno_f)

    if importo_personalizzato is not None:
        accantonato = float(importo_personalizzato)
    else:
        accantonato = float(s["importi"][scenario])

    accantonato = round(min(max(accantonato, 0.0), lordo), 2)

    pavimento = round(min(rivalsa, lordo), 2)
    alzato_alla_rivalsa = accantonato < pavimento
    if alzato_alla_rivalsa:
        accantonato = pavimento

    return {
        "lordo": round(lordo, 2),
        "scenario": scenario,
        "accantonamento": accantonato,
        "giroconto": round(lordo - accantonato, 2),
        "rivalsa": rivalsa,
        "alzato_alla_rivalsa": alzato_alla_rivalsa,
        "scomposizione": s,
    }


# ---------------------------------------------------------------------------
# Il fatto: i movimenti veri del conto personale
# ---------------------------------------------------------------------------

def aggancia(sb) -> int:
    """
    Attacca a una fattura i movimenti del conto personale che sono
    davvero il suo giroconto, e restituisce quanti ne ha agganciati.

    Candidato e' una riga di `spese` con categoria "Giroconto P.IVA" e
    `fattura_giroconto_id` ancora vuoto — non importa da dove arrivi
    (import della banca, inserimento a mano, "registra il bonifico").

    **La regola quando le fatture sono piu' di una**: ogni movimento va
    alla fattura ripartita piu' di recente fra quelle la cui data di
    ripartizione non e' successiva al movimento. Detta al contrario: un
    bonifico appartiene all'ultima ripartizione decisa prima che il
    bonifico arrivasse. E' deterministica, non guarda gli importi (che
    non combaciano quasi mai, e' tutto il punto) e non puo' attribuire
    denaro a una fattura che allora non era ancora stata ripartita.

    Un movimento anteriore a ogni ripartizione resta senza fattura: non
    e' un errore, e' un giroconto fatto per conto suo.
    """
    try:
        r = sb.table("b2f_fatture").select("id, data_giroconto").execute()
        fatture = [x for x in (r.data or []) if x.get("data_giroconto")]
    except Exception:
        return 0
    if not fatture:
        return 0
    # Dalla piu' recente: la prima che "sta prima" del movimento vince.
    fatture.sort(key=lambda x: str(x["data_giroconto"]), reverse=True)

    # La categoria del lato PERSONALE ("Giroconto P.IVA"), che e' un'altra
    # stringa da quella del lato P.IVA ("giroconto_personale"): la prima
    # e' un nome scelto dall'utente in `cfg_categorie`, la seconda una
    # chiave interna di `b2f_spese_piva`.
    from spese.dati import CATEGORIA_GIROCONTO as CATEGORIA_PERSONALE
    try:
        r = (sb.table("v_spese").select("id, data, fattura_giroconto_id")
             .eq("categoria", CATEGORIA_PERSONALE).execute())
        liberi = [x for x in (r.data or []) if not x.get("fattura_giroconto_id")]
    except Exception:
        return 0

    agganciati = 0
    for riga in liberi:
        quando = str(riga.get("data") or "")
        scelta = next((f for f in fatture
                       if str(f["data_giroconto"]) <= quando), None)
        if not scelta:
            continue
        try:
            (sb.table("spese").update({"fattura_giroconto_id": scelta["id"]})
             .eq("id", riga["id"]).execute())
            agganciati += 1
        except Exception:
            pass
    return agganciati


def movimenti(sb, fid) -> list[dict]:
    """I movimenti veri del conto personale agganciati a questa fattura."""
    try:
        r = (sb.table("v_spese")
             .select("id, data, tipo, importo, descrizione, metodo_pagamento")
             .eq("fattura_giroconto_id", fid).order("data").execute())
        return r.data or []
    except Exception:
        return []


def arrivato(righe: list[dict]) -> float:
    """
    Quanto e' davvero arrivato sul conto personale: entrate meno uscite.

    Le uscite contano perche' una tranche puo' tornare indietro — sulla
    2026/001 sono rientrati 1.068,33 tre settimane dopo. Un giroconto e'
    il **netto** di quello che si e' mosso, non la somma degli accrediti.
    """
    tot = 0.0
    for r in righe:
        try:
            imp = float(r.get("importo") or 0)
        except (TypeError, ValueError):
            continue
        tot += -imp if r.get("tipo") == "uscita" else imp
    return round(tot, 2)


def stato(sb, f: dict) -> dict:
    """
    Il quadro completo di una ripartizione: cosa hai deciso, cosa e'
    davvero arrivato, e quanto manca.

    E' l'unico posto che mette insieme i due lati; la card di
    `fatture/storico.py` e le rotte qui sotto leggono da qui, cosi' non
    esistono due modi di calcolare "manca".
    """
    fid = f.get("id")
    righe = movimenti(sb, fid) if fid else []
    reale = arrivato(righe)
    deciso = round(float(f.get("giroconto_importo") or 0), 2)
    return {
        "deciso": deciso,
        "arrivato": reale,
        "manca": round(deciso - reale, 2),
        "movimenti": righe,
        "in_attesa": not righe,
    }


def _sincronizza_piva(sb, f: dict, reale: float) -> int | None:
    """
    Tiene l'uscita dal conto P.IVA uguale a quello che e' davvero
    arrivato sul personale, e restituisce l'id della riga (o None).

    Non e' un dettaglio contabile: e' la stessa somma vista dai due lati
    dello stesso bonifico. Se sul personale sono arrivati 2.423,52, dal
    conto P.IVA ne sono usciti 2.423,52 — non i 2.425,52 che avevi
    deciso di spostare. Finche' non e' arrivato niente, dal conto P.IVA
    non esce niente: quei soldi sono ancora li', e il saldo deve dirlo.
    """
    fid = f.get("id")
    rid = f.get("giroconto_piva_id")
    numero = f.get("numero") or f"#{fid}"
    deciso = round(float(f.get("giroconto_importo") or 0), 2)

    if reale <= 0:
        if rid:
            try:
                sb.table("b2f_spese_piva").delete().eq("id", rid).execute()
            except Exception:
                pass
        return None

    # La rivalsa resta scritta nella riga, non solo calcolata: fra sei mesi,
    # guardando il movimento, e' l'unico posto in cui quel numero e' ancora
    # leggibile (README § 4, tabella "dove si vede la rivalsa").
    rivalsa = round(float(f.get("cassa_importo") or 0), 2)
    nota = (f"Deciso di spostarne € {deciso:.2f}; sul conto personale "
            f"ne sono arrivati € {reale:.2f}."
            + (f" Di cui rivalsa INPS € {rivalsa:.2f}, già inclusa "
               f"nell'accantonamento." if rivalsa else ""))
    riga = {
        "data":        f.get("data_giroconto") or date.today().isoformat(),
        "tipo":        "giroconto",
        "importo":     reale,
        "descrizione": f"Giroconto al personale — fattura {numero}",
        "categoria":   CATEGORIA_PIVA,
        "fattura_id":  fid,
        "note":        nota,
    }
    if rid:
        try:
            sb.table("b2f_spese_piva").update(riga).eq("id", rid).execute()
            return rid
        except Exception:
            return rid
    try:
        ins = sb.table("b2f_spese_piva").insert(riga).execute()
        return (ins.data or [{}])[0].get("id")
    except Exception:
        return None


def _rispecchia(sb, f: dict) -> dict:
    """Rilegge il fatto e allinea il lato P.IVA di UNA fattura."""
    s = stato(sb, f)
    rid = _sincronizza_piva(sb, f, s["arrivato"])
    if rid != f.get("giroconto_piva_id"):
        try:
            (sb.table("b2f_fatture").update({"giroconto_piva_id": rid})
             .eq("id", f.get("id")).execute())
        except Exception:
            pass
        f["giroconto_piva_id"] = rid
    return s


def riconcilia(sb, f: dict) -> dict:
    """
    Aggancia quello che c'e' di nuovo, rispecchia il lato P.IVA e
    restituisce il quadro aggiornato. E' il gesto che chiude il cerchio,
    e va chiamato ogni volta che sul conto personale puo' essere
    comparso un movimento: dopo una ripartizione, quando si apre la
    fattura, o quando l'utente preme "Ricontrolla la banca".
    """
    aggancia(sb)
    return _rispecchia(sb, f)


def riconcilia_tutte(sb) -> int:
    """
    La stessa cosa, ma per tutte le fatture ripartite: e' quello che
    serve dopo un import, dove i movimenti arrivano in blocco e non si
    sa in anticipo a quali fatture appartengano.

    Ritorna quanti movimenti sono stati agganciati.
    """
    n = aggancia(sb)
    try:
        r = sb.table("b2f_fatture").select("*").execute()
        fatture = [x for x in (r.data or []) if x.get("data_giroconto")]
    except Exception:
        return n
    for f in fatture:
        try:
            _rispecchia(sb, f)
        except Exception:
            pass
    return n


@fatture_bp.post("/api/fatture/<int:fid>/giroconto")
def api_giroconto_esegui(fid):
    """
    Registra la **decisione** di accantonamento, poi guarda sul conto
    personale se il bonifico e' gia' arrivato.

    Le guardie stanno qui e non solo nell'interfaccia: un doppio invio
    o una chiamata diretta non devono poter duplicare la decisione.
    """
    sb, err = _sb_or_503()
    if err:
        return err

    f, errore = _carica(sb, fid)
    if errore:
        return errore

    # A incasso avvenuto, non "in stato incassata": dopo l'incasso la
    # fattura prosegue verso lo studio e lo SDI, e la ripartizione si puo'
    # fare in qualunque momento da li' in poi.
    stato_f = normalizza_stato(f.get("stato"))
    if not ha_incassato(f):
        return jsonify({
            "error": ("Il giroconto si fa a incasso avvenuto: fino ad allora "
                      "i soldi non sono ancora sul conto P.IVA. Segna prima "
                      "la fattura come incassata."),
            "stato": stato_f,
        }), 409

    if f.get("data_giroconto"):
        return jsonify({
            "error": ("Il giroconto di questa fattura è già stato registrato. "
                      "Annullalo se devi rifarlo con un altro scenario."),
            "data_giroconto": f.get("data_giroconto"),
        }), 409

    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario") or "consigliato"
    scenario = acc.normalizza_scenario(scenario)
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
    from .fiscale import get_parametri, _aliquota_imposta_per_anno
    param = get_parametri(sb)
    anno_f = int((f.get("data") or "")[:4] or date.today().year)
    # get_parametri() corregge l'aliquota solo per l'anno di oggi: qui si
    # scrive davvero il giroconto sul database, quindi va ricorretta per
    # l'anno della fattura, altrimenti una fattura di un anno con
    # aliquota al 15% verrebbe scomposta ancora al 5%, spostando sul
    # personale piu' soldi di quanti dovrebbero restare accantonati.
    param["aliquota_imposta"] = _aliquota_imposta_per_anno(param, anno_f)
    try:
        r = (sb.table("b2f_fatture").select("totale")
               .neq("stato", "annullata")
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

    # --- 1) Il lordo, sul conto P.IVA, se non c'e' gia' -------------------
    # La ripartizione muove denaro fuori dal conto P.IVA: se il lordo
    # incassato non ci e' mai arrivato (perche' non si e' passati da
    # "Registra entrata su P.IVA"), il saldo di quel conto finirebbe
    # sotto della cifra spostata, come se il cliente non avesse pagato.
    id_entrata = f.get("spesa_piva_id")
    id_entrata_nuova = None   # solo se creata ora: da disfare in caso di rollback
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

    # --- 2) La decisione, sulla fattura -----------------------------------
    # Prima di guardare la banca, e non dopo: e' `data_giroconto` a dire
    # ad `aggancia()` da quando i movimenti appartengono a questa fattura.
    upd = {
        "accantonamento_scenario": scenario,
        "accantonamento_importo":  calc["accantonamento"],
        "giroconto_importo":       calc["giroconto"],
        "data_giroconto":          quando,
        "spesa_piva_id":           id_entrata,
    }
    try:
        sb.table("b2f_fatture").update(upd).eq("id", fid).execute()
    except Exception as e:
        if id_entrata_nuova:
            try:
                sb.table("b2f_spese_piva").delete().eq("id", id_entrata_nuova).execute()
            except Exception:
                pass
        return jsonify({"error": f"aggiornamento fattura fallito: {str(e)[:200]}"}), 500

    # --- 3) Il fatto, dalla banca -----------------------------------------
    # Qui non si scrive nessuna entrata sul conto personale: si guarda se
    # il bonifico c'e' gia'. Se non c'e', la fattura resta "in attesa" e
    # il saldo del personale continua a dire la verita'.
    f.update(upd)
    f["id"] = fid
    s = riconcilia(sb, f)

    return jsonify({
        "ok": True,
        "scenario": scenario,
        "accantonamento": calc["accantonamento"],
        "giroconto": calc["giroconto"],
        "rivalsa": calc["rivalsa"],
        "alzato_alla_rivalsa": calc["alzato_alla_rivalsa"],
        "data": quando,
        "movimento_piva_id": f.get("giroconto_piva_id"),
        **s,
    })


@fatture_bp.post("/api/fatture/<int:fid>/giroconto/aggancia")
def api_giroconto_aggancia(fid):
    """
    "Ricontrolla la banca": riguarda se sono comparsi movimenti di
    giroconto da agganciare, e riallinea il lato P.IVA.
    """
    sb, err = _sb_or_503()
    if err:
        return err
    f, errore = _carica(sb, fid)
    if errore:
        return errore
    if not f.get("data_giroconto"):
        return jsonify({"error": "questa fattura non è ancora stata ripartita"}), 409
    return jsonify({"ok": True, **riconcilia(sb, f)})


@fatture_bp.post("/api/fatture/<int:fid>/giroconto/bonifico")
def api_giroconto_bonifico(fid):
    """
    Registra a mano il bonifico appena eseguito, quando l'estratto conto
    non e' ancora stato importato.

    E' comunque un movimento vero del conto personale, non una
    dichiarazione parallela: finisce in `spese` come tutti gli altri,
    con la sua data e il suo importo. Se poi l'import della banca porta
    la stessa riga, il controllo sui doppioni la segnala
    (`spese/importa.py`) invece di scriverla due volte.
    """
    sb, err = _sb_or_503()
    if err:
        return err
    f, errore = _carica(sb, fid)
    if errore:
        return errore
    if not f.get("data_giroconto"):
        return jsonify({"error": "ripartisci prima l'incasso"}), 409

    body = request.get_json(silent=True) or {}
    try:
        importo = round(float(body.get("importo") or 0), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "importo non valido"}), 400
    if importo == 0:
        return jsonify({"error": "importo mancante"}), 400

    quando = body.get("data") or date.today().isoformat()
    if str(quando) < str(f.get("data_giroconto")):
        return jsonify({
            "error": ("Il bonifico non può essere anteriore alla ripartizione "
                      f"({f.get('data_giroconto')}): fino a quel giorno quei "
                      "soldi non erano ancora stati destinati al personale."),
        }), 400

    # Import qui dentro e non in testa: `fatture` e `spese` sono due
    # blueprint indipendenti, e legarli al caricamento del modulo
    # imporrebbe un ordine di import fra i due.
    from spese import dati as personale

    numero = f.get("numero") or f"#{fid}"
    verso = "da" if importo > 0 else "a"
    # `tipo=entrata` e non `giroconto`: v_risparmi_mese conta le entrate,
    # e un movimento marcato giroconto resterebbe fuori dal budget.
    esito = personale.crea(sb, {
        "data":              quando,
        "tipo":              "entrata" if importo > 0 else "uscita",
        "importo":           abs(importo),
        "descrizione":       f"Giroconto {verso} P.IVA — fattura {numero}",
        "metodo_pagamento":  "Giroconto",
        "categoria_link_id": personale.link_categoria(
            sb, personale.CATEGORIA_GIROCONTO),
    })
    if esito.get("error") or not esito.get("id"):
        return jsonify({"error": "errore sul conto personale: "
                                 f'{esito.get("error") or "nessun id di ritorno"}'}), 500

    return jsonify({"ok": True, "movimento_id": esito["id"], **riconcilia(sb, f)})


@fatture_bp.delete("/api/fatture/<int:fid>/giroconto")
def api_giroconto_annulla(fid):
    """
    Annulla la **decisione**: libera la fattura, cosi' si puo' rifare la
    ripartizione con un altro scenario, e toglie l'uscita dal conto P.IVA.

    I movimenti del conto personale **non vengono cancellati**: sono
    bonifici veri, e un bonifico non si disfa cambiando idea su come
    ripartire. Vengono solo staccati dalla fattura; alla prossima
    ripartizione `aggancia()` li rimette al loro posto.
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
    staccati = 0
    try:
        r = (sb.table("spese").update({"fattura_giroconto_id": None})
             .eq("fattura_giroconto_id", fid).execute())
        staccati = len(r.data or [])
    except Exception as e:
        problemi.append(f"spese: {str(e)[:80]}")

    rid = f.get("giroconto_piva_id")
    if rid:
        try:
            sb.table("b2f_spese_piva").delete().eq("id", rid).execute()
        except Exception as e:
            problemi.append(f"b2f_spese_piva: {str(e)[:80]}")

    if problemi:
        return jsonify({
            "error": ("Non sono riuscito a disfare tutto; la fattura resta "
                      "collegata per non perderne traccia. "
                      + " | ".join(problemi)),
        }), 500

    upd = {k: None for k in ("accantonamento_scenario", "accantonamento_importo",
                             "giroconto_importo", "data_giroconto",
                             "giroconto_piva_id", "giroconto_personale_id")}
    try:
        sb.table("b2f_fatture").update(upd).eq("id", fid).execute()
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500

    return jsonify({"ok": True, "movimenti_staccati": staccati})
