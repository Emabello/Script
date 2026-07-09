"""
app.py — Entry point della hub B2F.

Riusa `app` di xs_server (timesheet "Le mie ore") esattamente com'è, e
ci registra sopra due blueprint aggiuntivi:

  /fatture   -> fatturatore forfettario (persistenza Supabase)
  /spese     -> gestione spese (Supabase, tabella `spese`)

La radice / redirige al timesheet per compatibilità con la PWA gia
installata. Il PIN gate di xs_server continua a proteggere tutto perche
il `before_request` e' registrato sull'oggetto app, non sul blueprint.

Deploy Render:
  web: gunicorn -w 1 app:app
"""
from flask import jsonify, redirect

from xs_server import app  # importa la Flask app esistente, invariata

# Nuove aree
from fatture import fatture_bp
from spese import spese_bp

from shared.supabase_client import get_client, is_configured

app.register_blueprint(fatture_bp, url_prefix="/fatture")
app.register_blueprint(spese_bp,   url_prefix="/spese")


# Home: per ora manda al timesheet (PWA installata continua a funzionare).
# In futuro, se vorrai una landing hub vera con tre card, la mettiamo qui.
@app.get("/hub")
def hub_home():
    return redirect("/")


@app.get("/health")
def health():
    """
    Endpoint pubblico (non protetto da PIN, non finisce in /api/).
    Utile per verificare da Render che tutto sia collegato correttamente.
    """
    out = {"app": "b2f-hub", "status": "up"}

    # 1. Supabase configurato?
    if not is_configured():
        out["supabase"] = {"configured": False}
        return jsonify(out)

    out["supabase"] = {"configured": True}
    sb = get_client()

    # 2. Le tabelle rispondono? (count leggeri, no scanning)
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
    # Solo per uso locale; su Render entra Gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=False)
