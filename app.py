"""
app.py — Entry point della hub B2F.

Riusa `app` di xs_server (timesheet "Le mie ore") esattamente com'è, e ci
registra sopra due blueprint aggiuntivi:

  /fatture   -> fatturatore forfettario (persistenza Supabase)
  /spese     -> gestione spese (Supabase, tabella `spese`)

La radice / redirige al timesheet per compatibilità con la PWA già
installata. Il PIN gate di xs_server continua a proteggere tutto perché
il `before_request` è registrato sull'oggetto app, non sul blueprint.

Deploy Render:
  web: gunicorn -w 1 app:app
"""
from flask import redirect, url_for

from xs_server import app  # importa la Flask app esistente, invariata

# Nuove aree
from fatture import fatture_bp
from spese import spese_bp

app.register_blueprint(fatture_bp, url_prefix="/fatture")
app.register_blueprint(spese_bp,   url_prefix="/spese")


# Home: per ora manda al timesheet (PWA installata continua a funzionare).
# In futuro, se vorrai una landing hub vera con tre card, la mettiamo qui.
@app.get("/hub")
def hub_home():
    # placeholder path esplicito per uso futuro
    return redirect("/")


if __name__ == "__main__":
    # Solo per uso locale; su Render entra Gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=False)
