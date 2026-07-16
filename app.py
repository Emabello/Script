"""
app.py — Entry point della hub B2F (Fiori Launchpad style).

Route:
  /                       -> Launchpad (3 tile Ore/Fatture/Spese)
  /ore                    -> Timesheet (definito in xs_server, spostato dalla root)
  /fatture, /spese        -> Blueprint delle sotto-app
  /api/kpi/fatture        -> KPI async per la launchpad
  /api/kpi/spese          -> KPI async per la launchpad
  /health                 -> stato tabelle Supabase

La radice / mostra la launchpad. Il timesheet e' stato spostato su /ore
tramite apply_patch.py (il decoratore di index() viene riscritto).
"""
from datetime import date

from flask import Response, jsonify

import xs_server
from xs_server import app  # importa la Flask app esistente

from fatture import fatture_bp
from spese import spese_bp
from shared.webauthn import webauthn_bp

from shared.theme import render_launchpad
from shared.supabase_client import get_client, is_configured

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
})


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


@app.get("/")
def launchpad():
    html = render_launchpad(greet_name=_greet_name())
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
                     .in_("stato", ["emessa", "incassata"])
                     .execute())
        # Imponibile del mese corrente
        r_mese = (sb.table("b2f_fatture")
                    .select("imponibile,stato")
                    .gte("data", d_from).lte("data", d_to)
                    .in_("stato", ["emessa", "incassata"])
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
        r = (sb.table("spese")
               .select("importo,tipo")
               .gte("data", d_from).lte("data", d_to).execute())
        entrate = uscite = 0.0
        for row in (r.data or []):
            imp = float(row.get("importo") or 0)
            t = row.get("tipo") or ""
            if t == "entrata": entrate += imp
            elif t == "uscita": uscite += imp
        return jsonify({
            "entrate_mese": round(entrate, 2),
            "uscite_mese":  round(uscite, 2),
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
        "spese":         probe("spese"),
        "b2f_emittente": probe("b2f_emittente"),
        "b2f_clienti":   probe("b2f_clienti"),
        "b2f_fatture":   probe("b2f_fatture"),
    }
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
