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

from flask import Response, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

import xs_server
from xs_server import app  # importa la Flask app esistente

from fatture import fatture_bp
from fatture.costanti import STATI_EMESSE
from spese import spese_bp
from shared.webauthn import webauthn_bp

from shared.caricamento import render_attesa
from shared.theme import render_launchpad, render_saldi_page
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

app.register_blueprint(fatture_bp, url_prefix="/fatture")
app.register_blueprint(spese_bp,   url_prefix="/spese")
app.register_blueprint(webauthn_bp, url_prefix="/api/webauthn")

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
})


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


def _saldi_conti(sb, al: str) -> dict:
    """
    I tre conti, a una data. Estratta a parte perche' serve sia alla
    home (dentro _dashboard_data, insieme a tutto il resto) sia alla
    pagina dedicata /saldi (da sola, senza il resto della dashboard).
    """
    from fatture.fiscale import saldo_piva
    from spese import dati as personale
    from spese.revolut import saldo_revolut
    return {
        "piva": saldo_piva(sb, al),
        "personale": personale.saldo_conto(sb, al),
        "revolut": saldo_revolut(sb, al),
    }


def _dashboard_data() -> dict:
    """
    Dati della home. Ogni blocco e' isolato in un try: se una query
    fallisce la dashboard perde quel riquadro, non l'intera pagina.
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
    out: dict = {"anno": anno}

    # I tre conti, ad oggi. Sono la prima cosa che si guarda aprendo
    # l'app, e sono l'unico numero che nessun'altra pagina dava: /spese
    # mostra il saldo del mese e /fatture/spese-piva quello dell'anno
    # filtrato, non quanto c'e' davvero sui conti.
    try:
        out["saldi"] = _saldi_conti(sb, today.isoformat())
    except Exception:
        pass

    # Situazione fiscale: da qui arrivano incassato del mese, scadenze e
    # la base per il calcolo dell'accantonamento.
    try:
        s = situazione_data(sb, anno)
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
    except Exception as e:
        out["errore"] = f"Situazione fiscale non disponibile: {str(e)[:160]}"

    try:
        r = (sb.table("b2f_fatture").select("*", count="exact", head=True)
               .eq("anno", anno).in_("stato", list(STATI_EMESSE)).execute())
        out["n_fatture_anno"] = r.count
    except Exception:
        pass

    try:
        r = (sb.table("b2f_fatture")
               .select("id,numero,data,totale,stato,cliente_snapshot")
               .in_("stato", list(STATI_EMESSE))
               .order("data", desc=True).limit(4).execute())
        out["ultime_fatture"] = [
            (f["id"], f.get("numero") or "—", cliente_label(f),
             f.get("data"), f.get("totale"))
            for f in (r.data or [])
        ]
    except Exception:
        pass

    # Saldo del mese dallo stesso livello dati di /spese, non da una
    # query fatta qui: erano due conteggi diversi sulla stessa domanda —
    # questo ignorava le righe storiche con tipo=giroconto, che /spese
    # invece contava come entrate, e i due numeri non tornavano fra loro.
    try:
        righe_mese = personale.righe_periodo(sb, anno=anno, mese=today.month)
        out["saldo_spese_mese"] = personale.totali(righe_mese)["saldo"]
    except Exception:
        pass

    # "E' arrivato lo stipendio e non hai ancora messo via niente": e'
    # l'unico avviso della home che chiede di fare qualcosa, e compare
    # solo quando c'e' davvero qualcosa da fare (vedi
    # spese/dati.py::avviso_risparmio). Se comparisse sempre, in un mese
    # nessuno lo leggerebbe piu'.
    try:
        avviso = personale.avviso_risparmio(sb)
        if avviso:
            out["avviso_risparmio"] = avviso
    except Exception:
        pass

    try:
        r = (sb.table("spese").select("data,importo,descrizione,tipo")
               .order("data", desc=True).limit(4).execute())
        out["ultimi_movimenti"] = [
            ((m.get("descrizione") or "—"), m.get("data"),
             float(m.get("importo") or 0), m.get("tipo") or "")
            for m in (r.data or [])
        ]
    except Exception:
        pass

    return out


@app.get("/")
def launchpad():
    html = render_launchpad(greet_name=_greet_name(), dati=_dashboard_data())
    return Response(html, mimetype="text/html")


@app.get("/saldi")
def saldi_page():
    saldi = None
    coerenza_html = ""
    if is_configured():
        sb = get_client()
        try:
            saldi = _saldi_conti(sb, date.today().isoformat())
        except Exception:
            saldi = None
        # Il confronto risparmio dichiarato/reale vive gia' su /spese/revolut:
        # qui compare solo se Revolut e' collegato, stessa logica, nessuna
        # query in piu' se non serve.
        if saldi and (saldi.get("revolut") or {}).get("disponibile"):
            try:
                from spese.revolut import coerenza, _riquadro_coerenza
                coerenza_html = _riquadro_coerenza(coerenza(sb, saldi["revolut"]))
            except Exception:
                coerenza_html = ""
    # Il controllo contro l'estratto. Va fatto **alla data dell'estratto**,
    # non a oggi: fra quel giorno e adesso ci sono movimenti veri, e la
    # differenza non sarebbe un errore ma il normale scorrere del conto.
    verifiche = {}
    if is_configured() and saldi:
        from spese import dati as personale
        from fatture.fiscale import saldo_piva
        sb2 = get_client()
        try:
            v = personale.ultima_verifica(sb2, "personale")
            if v:
                al = v["data"]
                verifiche["personale"] = personale.verifica_saldo(
                    sb2, "personale", personale.saldo_conto(sb2, al)["saldo"], al)
        except Exception:
            pass
        try:
            v = personale.ultima_verifica(sb2, "piva")
            if v:
                al = v["data"]
                verifiche["piva"] = personale.verifica_saldo(
                    sb2, "piva", saldo_piva(sb2, al)["saldo"], al)
        except Exception:
            pass

    html = render_saldi_page(saldi, coerenza_html, verifiche)
    return Response(html, mimetype="text/html")


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
