"""
app.py — Entry point della hub B2F (Fiori Launchpad style).

Route:
  /                       -> Launchpad (3 tile Ore/Fatture/Spese)
  /ore                    -> Timesheet (definito in xs_server, spostato dalla root)
  /fatture, /spese        -> Blueprint delle sotto-app
  /api/kpi/fatture        -> KPI async per la launchpad
  /api/kpi/spese          -> KPI async per la launchpad
  /attesa                 -> tenda mosaico, servita dal service worker
                             mentre Render risveglia il container
  /ping                   -> "sono sveglio", per la pagina d'attesa
  /health                 -> stato tabelle Supabase

La radice / mostra la launchpad. Il timesheet e' stato spostato su /ore
tramite apply_patch.py (il decoratore di index() viene riscritto).
"""
import os
from datetime import date

from flask import Response, jsonify, redirect
from werkzeug.middleware.proxy_fix import ProxyFix

import xs_server
from xs_server import app  # importa la Flask app esistente

from fatture import fatture_bp
from fatture.costanti import STATI_EMESSE
from spese import spese_bp
from shared.webauthn import webauthn_bp

from shared.caricamento import render_attesa
from shared.theme import render_launchpad, render_conti_page, render_impostazioni_page
from shared.supabase_client import get_client, is_configured

# Render (come ogni PaaS) termina il TLS su un proxy e inoltra a gunicorn in
# HTTP con header X-Forwarded-Proto: https. Senza ProxyFix, request.scheme
# resta 'http': l'origin WebAuthn calcolato diventa "http://<host>" e NON
# combacia con l'origin reale del browser ("https://<host>"), facendo fallire
# la verifica di registrazione e autenticazione (register/complete 400,
# auth/complete 401). Con ProxyFix lo schema torna corretto.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Cookie di sessione: SameSite esplicito (Lax va bene, le chiamate WebAuthn
# sono same-origin) e Secure in produzione (Render espone la env RENDER).
# In locale (http) Secure resta False così lo sblocco PIN continua a funzionare.
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

# Senza url_prefix, e ogni rotta porta il suo percorso completo nel
# decoratore. E' quello che permette all'albero della navigazione di
# esistere: il conto P.IVA sta in `fatture/fiscale.py` (accanto al resto
# del fisco, dove ha senso che stia il codice) ma risponde su
# /conti/webank/piva, dove ha senso che stia per chi naviga. Con il
# prefisso sul blueprint le due cose erano costrette a coincidere, ed e'
# il motivo per cui i tre conti erano sparsi in due sezioni diverse.
app.register_blueprint(fatture_bp)
app.register_blueprint(spese_bp)
app.register_blueprint(webauthn_bp, url_prefix="/api/webauthn")

# I percorsi di prima, che devono continuare a funzionare: segnalibri,
# l'app installata sul telefono (il manifest ha start_url "/"), i link
# scritti nelle note. Un 301 e non un doppione: due URL vivi per la
# stessa pagina non si riallineano mai piu'.
VECCHI_PERCORSI = {
    "/saldi":                  "/conti",
    "/spese":                  "/conti/webank/personale",
    "/spese/":                 "/conti/webank/personale",
    "/spese/movimenti":        "/conti/webank/personale",
    "/spese/movimenti/nuovo":  "/conti/webank/personale/nuovo",
    "/spese/importa":          "/conti/webank/personale/importa",
    "/spese/revolut":          "/conti/revolut",
    "/spese/risparmi":         "/risparmi",
    "/fatture/spese-piva":       "/conti/webank/piva",
    "/fatture/spese-piva/nuova": "/conti/webank/piva/nuova",
    "/fatture/parametri":      "/impostazioni/parametri",
    "/fatture/emittente":      "/impostazioni/emittente",
}


def _vecchio_percorso(nuovo: str):
    def vai():
        from flask import request as _rq
        meta = nuovo
        if _rq.query_string:
            meta += "?" + _rq.query_string.decode("utf-8", "ignore")
        return redirect(meta, code=301)
    return vai


for _vecchio, _nuovo in VECCHI_PERCORSI.items():
    app.add_url_rule(_vecchio, endpoint=f"legacy{_vecchio.replace('/', '_')}",
                     view_func=_vecchio_percorso(_nuovo))

# Quelli con un id dentro: stessa cosa, ma la rotta ha un segnaposto.
@app.get("/spese/movimenti/<int:mid>")
def legacy_movimento(mid):
    return redirect(f"/conti/webank/personale/{mid}", code=301)


@app.get("/fatture/spese-piva/<int:mid>")
def legacy_spesa_piva(mid):
    return redirect(f"/conti/webank/piva/{mid}", code=301)

# Gli endpoint WebAuthn devono restare accessibili senza PIN: register/*
# richiede comunque sessione già sbloccata (controllo interno al blueprint),
# auth/* è il meccanismo stesso con cui ci si sblocca.
xs_server.ALLOW_NO_PIN.update({
    "webauthn.webauthn_register_begin",
    "webauthn.webauthn_register_complete",
    "webauthn.webauthn_auth_begin",
    "webauthn.webauthn_auth_complete",
    "webauthn.webauthn_status",
    # La tenda d'attesa non mostra dati: deve caricarsi anche a sessione
    # bloccata, ed e' quella che il service worker si mette in cache.
    "attesa",
    "ping",
    # Il foglio di stile serve anche alla schermata del PIN: senza, quella
    # schermata si vedrebbe senza stile. Non contiene dati.
    "foglio_di_stile",
})


# I file statici (font, jsPDF) non cambiano fra un deploy e l'altro: il
# browser li tiene per un mese invece di richiederli a ogni pagina. Prima
# ogni click faceva tre o quattro richieste «e' cambiato?» per i font,
# e con un server che ne serve una alla volta passavano davanti alla pagina.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 30


@app.after_request
def _firma_risposta(resp):
    """
    Ogni risposta dell'app porta questa firma.

    Serve al service worker (shared/caricamento.py): quando il container
    dorme, a rispondere e' il proxy di Render con la sua schermata di
    caricamento — stesso URL, stesso 200, HTML loro. L'header e' il solo
    modo onesto di distinguere "ha risposto l'app" da "ha risposto
    qualcun altro al posto suo": se manca, il worker serve la nostra
    pagina d'attesa dalla cache.
    """
    resp.headers["X-B2F"] = "hub"
    from flask import request as _rq
    if _rq.endpoint in ("manifest", "icon192", "icon512", "appleicon"):
        resp.headers["Cache-Control"] = "public, max-age=86400"
    return _comprimi(resp)


# Tipi che vale la pena comprimere: testo. Un xlsx o un'immagine sono gia'
# compressi, e rifarlo costa tempo senza guadagno.
_COMPRIMIBILI = ("text/html", "text/css", "application/json",
                 "application/javascript", "text/javascript")


def _comprimi(resp):
    """
    Gzip sulle risposte di testo, se il browser lo accetta.

    Una pagina dell'app pesa sui 120 KB, e fino a oggi viaggiava cosi'
    com'era: su una rete mobile e' il tempo che separa il click dalla
    pagina. Compressa ne pesa un quinto. Lo fa l'app e non un proxy
    perche' davanti a Render non c'e' niente che lo faccia al posto suo.
    """
    import gzip
    from flask import request as _rq
    if (resp.status_code != 200 or resp.direct_passthrough
            or "gzip" not in (_rq.headers.get("Accept-Encoding") or "")
            or resp.headers.get("Content-Encoding")
            or (resp.mimetype or "") not in _COMPRIMIBILI):
        return resp
    dati = resp.get_data()
    if len(dati) < 1400:
        return resp
    resp.set_data(gzip.compress(dati, compresslevel=5))
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(resp.get_data()))
    resp.headers.add("Vary", "Accept-Encoding")
    return resp


@app.get("/assets/app.<versione>.css")
def foglio_di_stile(versione):
    """
    Il CSS dell'app, fuori dalle pagine (vedi shared/theme.py, CSS_URL).
    Con l'impronta giusta si tiene in cache un anno: quando il CSS cambia,
    cambia l'URL. Con un'impronta vecchia (una pagina rimasta aperta da
    prima di un deploy) si serve quello attuale, ma senza cache lunga.
    """
    from shared.design import CSS
    from shared.theme import CSS_VERSIONE
    resp = Response(CSS, mimetype="text/css")
    resp.headers["Cache-Control"] = ("public, max-age=31536000, immutable"
                                     if versione == CSS_VERSIONE else "no-cache")
    return resp


@app.get("/ping")
def ping():
    """Battito per la pagina d'attesa: nessuna query, solo "ci sono"."""
    return jsonify({"b2f": "sveglio"})


@app.get("/attesa")
def attesa():
    """
    La tenda mosaico da sola, senza app intorno.

    Non ci si arriva navigando: la serve il service worker dalla cache
    quando la richiesta non trova l'app. La rotta esiste perche' il
    worker possa metterla in cache all'installazione.
    """
    return Response(render_attesa(), mimetype="text/html",
                    headers={"Cache-Control": "no-store"})


def _greet_name() -> str:
    """Preleva il nome dell'emittente da Supabase per il saluto."""
    if not is_configured():
        return ""
    try:
        r = (get_client().table("b2f_emittente")
             .select("nome").eq("id", 1).single().execute())
        return (r.data or {}).get("nome") or ""
    except Exception:
        return ""


from shared.parallelo import in_parallelo as _in_parallelo  # noqa: E402


def _saldi_conti(sb, al: str) -> dict:
    """
    I tre conti, a una data. Estratta a parte perche' serve sia alla
    home (dentro _dashboard_data, insieme a tutto il resto) sia alla
    pagina dedicata /conti (da sola, senza il resto della dashboard).
    I tre saldi non dipendono l'uno dall'altro: si calcolano insieme.
    """
    from fatture.fiscale import saldo_piva
    from spese import dati as personale
    from spese.revolut import saldo_revolut
    calcoli = (lambda: saldo_piva(sb, al),
               lambda: personale.saldo_conto(sb, al),
               lambda: saldo_revolut(sb, al))
    risultati = _in_parallelo(*calcoli)
    # Le tre funzioni non sollevano: se una lettura cade a meta' tornano
    # «non disponibile». Un intoppo di rete isolato non deve svuotare un
    # quadratino della pagina: chi non e' tornato si ricalcola una volta.
    # (Revolut senza nessuna fotografia resta non disponibile anche al
    # secondo giro, ed e' giusto: e' «da collegare».)
    risultati = [r if (r or {}).get("disponibile") else (_in_parallelo(f)[0] or r)
                 for r, f in zip(risultati, calcoli)]
    vuoto = {"al": al, "disponibile": False}
    piva, pers, rev = risultati
    return {"piva": piva or vuoto, "personale": pers or vuoto,
            "revolut": rev or vuoto}


def _dashboard_data() -> dict:
    """
    Dati della home. Ogni blocco e' una funzione a se': partono tutte
    insieme (`_in_parallelo`) e se una fallisce la dashboard perde quel
    riquadro, non l'intera pagina.
    """
    if not is_configured():
        return {"errore": "Supabase non configurato. Aggiungi <code>SUPABASE_URL</code> "
                          "e <code>SUPABASE_KEY</code> alle env vars."}

    from fatture.fiscale import situazione_data
    from fatture import accantonamento as acc
    from fatture.storico import cliente_label
    from fatture.costanti import MESI_NOMI
    from spese import dati as personale

    sb = get_client()
    today = date.today()
    anno = today.year

    # I tre conti, ad oggi. Sono la prima cosa che si guarda aprendo
    # l'app, e sono l'unico numero che nessun'altra pagina dava: /spese
    # mostra il saldo del mese e /fatture/spese-piva quello dell'anno
    # filtrato, non quanto c'e' davvero sui conti.
    def saldi():
        return {"saldi": _saldi_conti(sb, today.isoformat())}

    # Situazione fiscale: da qui arrivano incassato del mese, scadenze e
    # la base per il calcolo dell'accantonamento.
    def fisco():
        out = {}
        try:
            s = situazione_data(sb, anno)
        except Exception as e:
            return {"errore": f"Situazione fiscale non disponibile: {str(e)[:160]}"}
        mese = s["mensile"][today.month - 1]
        incassato_mese = mese["incasso"]
        out["incassato_mese"] = incassato_mese
        out["scadenze"] = [(x["data"], x["descrizione"], x["importo"])
                           for x in s["scadenze"] if x["importo"] > 0]
        scomposizione = acc.scomponi(
            incassato_mese, s["parametri"],
            fatturato_riferimento=s["totali"]["incasso"],
            rivalsa=mese.get("rivalsa", 0), bollo_addebitato=mese.get("bollo", 0),
            anno=today.year,
        )
        out["accantonamento"] = scomposizione
        if incassato_mese > 0:
            out["accantonamento_html"] = acc.card_html(
                scomposizione,
                titolo="Da accantonare",
                contesto=f"Calcolato sugli incassi di {MESI_NOMI[today.month - 1].lower()}. "
                         f"Le tasse del forfettario si pagano per cassa: conta quando "
                         f"il denaro arriva, non quando emetti.",
                uid="accHome",
                anno_saldo=today.year, anno_acconto=today.year + 1,
            )
        return out

    def n_fatture():
        r = (sb.table("b2f_fatture").select("*", count="exact", head=True)
               .eq("anno", anno).in_("stato", list(STATI_EMESSE)).execute())
        return {"n_fatture_anno": r.count}

    def ultime_fatture():
        r = (sb.table("b2f_fatture")
               .select("id,numero,data,totale,stato,cliente_snapshot")
               .in_("stato", list(STATI_EMESSE))
               .order("data", desc=True).limit(4).execute())
        return {"ultime_fatture": [
            (f["id"], f.get("numero") or "—", cliente_label(f),
             f.get("data"), f.get("totale"))
            for f in (r.data or [])
        ]}

    # Saldo del mese dallo stesso livello dati di /spese, non da una
    # query fatta qui: erano due conteggi diversi sulla stessa domanda —
    # questo ignorava le righe storiche con tipo=giroconto, che /spese
    # invece contava come entrate, e i due numeri non tornavano fra loro.
    def saldo_mese():
        righe_mese = personale.righe_periodo(sb, anno=anno, mese=today.month)
        return {"saldo_spese_mese": personale.totali(righe_mese)["saldo"]}

    # "E' arrivato lo stipendio e non hai ancora messo via niente": e'
    # l'unico avviso della home che chiede di fare qualcosa, e compare
    # solo quando c'e' davvero qualcosa da fare (vedi
    # spese/dati.py::avviso_risparmio). Se comparisse sempre, in un mese
    # nessuno lo leggerebbe piu'.
    def avviso():
        a = personale.avviso_risparmio(sb)
        return {"avviso_risparmio": a} if a else {}

    def ultimi_movimenti():
        r = (sb.table("spese").select("data,importo,descrizione,tipo")
               .order("data", desc=True).limit(4).execute())
        return {"ultimi_movimenti": [
            ((m.get("descrizione") or "—"), m.get("data"),
             float(m.get("importo") or 0), m.get("tipo") or "")
            for m in (r.data or [])
        ]}

    out: dict = {"anno": anno}
    for pezzo in _in_parallelo(saldi, fisco, n_fatture, ultime_fatture,
                               saldo_mese, avviso, ultimi_movimenti):
        out.update(pezzo or {})
    return out


@app.get("/")
def launchpad():
    nome, dati = _in_parallelo(_greet_name, _dashboard_data)
    html = render_launchpad(greet_name=nome or "", dati=dati or {})
    return Response(html, mimetype="text/html")


@app.get("/conti")
def conti_page():
    saldi = None
    coerenza_html = ""
    verifiche = {}
    if is_configured():
        from spese import dati as personale
        from fatture.fiscale import saldo_piva
        sb = get_client()

        # Il controllo contro l'estratto. Va fatto **alla data
        # dell'estratto**, non a oggi: fra quel giorno e adesso ci sono
        # movimenti veri, e la differenza non sarebbe un errore ma il
        # normale scorrere del conto. Non dipende dai saldi di oggi, quindi
        # parte insieme a loro (`_in_parallelo`).
        def verifica(conto, calcola):
            v = personale.ultima_verifica(sb, conto)
            if not v:
                return None
            return personale.verifica_saldo(sb, conto, calcola(v["data"])["saldo"], v["data"])

        saldi, v_pers, v_piva = _in_parallelo(
            lambda: _saldi_conti(sb, date.today().isoformat()),
            lambda: verifica("personale", lambda al: personale.saldo_conto(sb, al)),
            lambda: verifica("piva", lambda al: saldo_piva(sb, al)))
        if v_pers:
            verifiche["personale"] = v_pers
        if v_piva:
            verifiche["piva"] = v_piva

        # Il confronto risparmio dichiarato/reale vive gia' su
        # /conti/revolut: qui compare solo se Revolut e' collegato.
        if saldi and (saldi.get("revolut") or {}).get("disponibile"):
            try:
                from spese.revolut import coerenza, _riquadro_coerenza
                coerenza_html = _riquadro_coerenza(coerenza(sb, saldi["revolut"]))
            except Exception:
                coerenza_html = ""
        if not saldi:
            verifiche = {}

    html = render_conti_page(saldi, coerenza_html, verifiche)
    return Response(html, mimetype="text/html")


@app.get("/impostazioni")
def impostazioni_page():
    """
    Le impostazioni, raccolte in un posto solo.

    Prima stavano sparse dentro Fatture: l'emittente nella landing, i
    parametri fiscali **solo** passando dalla Situazione fiscale — una
    pagina che si apre tre volte l'anno, dietro un percorso che nessuno
    indovina. Non sono fatture: sono come e' configurata l'app.
    """
    return Response(render_impostazioni_page(), mimetype="text/html")


@app.get("/api/export/completo.xlsx")
def export_completo():
    """
    L'app intera in un foglio di calcolo.

    Sta qui e non dentro un blueprint perche' attraversa tutte le aree —
    conti, movimenti, periodi di paga, fatture, fisco — e non ce n'e'
    nessuna che possa dirsi proprietaria. L'export fiscale per anno resta
    dove sta (`/fatture/api/export/xlsx`): quello riproduce il foglio del
    commercialista, questo e' lo storico completo.

    Il nome del file porta la data: un export e' una fotografia, e due
    fotografie diverse con lo stesso nome nella cartella Download si
    sovrascrivono a vicenda.
    """
    if not is_configured():
        return jsonify({"error": "supabase not configured"}), 503
    from flask import send_file
    from shared import esporta
    try:
        buf = esporta.costruisci(get_client())
    except Exception as e:
        return jsonify({"error": str(e)[:250]}), 500
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=esporta.nome_file(),
    )


# ---------------------------------------------------------------------
# API KPI per la launchpad (chiamate async dal client)
# ---------------------------------------------------------------------

@app.get("/api/kpi/fatture")
def kpi_fatture():
    if not is_configured():
        return jsonify({"error": "supabase not configured"}), 503
    sb = get_client()
    today = date.today()
    anno = today.year
    d_from = today.replace(day=1).isoformat()
    d_to = today.isoformat()
    try:
        # Fatture emesse/incassate quest'anno (esclude bozze e annullate)
        r_count = (sb.table("b2f_fatture")
                     .select("*", count="exact", head=True)
                     .eq("anno", anno)
                     .in_("stato", list(STATI_EMESSE))
                     .execute())
        # Imponibile del mese corrente
        r_mese = (sb.table("b2f_fatture")
                    .select("imponibile,stato")
                    .gte("data", d_from).lte("data", d_to)
                    .in_("stato", list(STATI_EMESSE))
                    .execute())
        imp = sum(float(row.get("imponibile") or 0) for row in (r_mese.data or []))
        return jsonify({
            "anno": anno,
            "count_anno": r_count.count,
            "imponibile_mese": round(imp, 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@app.get("/api/kpi/spese")
def kpi_spese():
    if not is_configured():
        return jsonify({"error": "supabase not configured"}), 503
    sb = get_client()
    today = date.today()
    d_from = today.replace(day=1).isoformat()
    d_to = today.isoformat()
    try:
        # v_spese e non spese: serve "categoria" per riconoscere il
        # giroconto dalla P.IVA, che arriva come riga tipo=entrata (non
        # tipo=giroconto — vedi fatture/giroconto.py) apposta per contare
        # nel budget. "girati" e' un sotto-totale informativo di
        # "entrate", non un terzo bucket da sommare al saldo: sommarlo
        # due volte gonfierebbe il saldo del doppio dell'incasso P.IVA.
        from spese.dati import CATEGORIA_GIROCONTO
        r = (sb.table("v_spese")
               .select("importo,tipo,categoria")
               .gte("data", d_from).lte("data", d_to).execute())
        entrate = uscite = girati = 0.0
        for row in (r.data or []):
            imp = abs(float(row.get("importo") or 0))
            t = row.get("tipo") or ""
            if t == "entrata":
                entrate += imp
                if row.get("categoria") == CATEGORIA_GIROCONTO:
                    girati += imp
            elif t == "uscita":
                uscite += imp
            elif t == "giroconto":
                entrate += imp
                girati += imp
        return jsonify({
            "entrate_mese": round(entrate, 2),
            "uscite_mese":  round(uscite, 2),
            "girati_mese":  round(girati, 2),
            "saldo_mese":   round(entrate - uscite, 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# ---------------------------------------------------------------------
# Health check (invariato da step 2)
# ---------------------------------------------------------------------

@app.get("/health")
def health():
    out = {"app": "b2f-hub", "status": "up"}
    if not is_configured():
        out["supabase"] = {"configured": False}
        return jsonify(out)
    out["supabase"] = {"configured": True}
    sb = get_client()

    def probe(table):
        try:
            r = sb.table(table).select("*", count="exact", head=True).execute()
            return {"ok": True, "count": r.count}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    out["tables"] = {
        "spese":                    probe("spese"),
        "b2f_emittente":            probe("b2f_emittente"),
        "b2f_clienti":              probe("b2f_clienti"),
        "b2f_fatture":              probe("b2f_fatture"),
        "b2f_webauthn_credentials": probe("b2f_webauthn_credentials"),
    }
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
