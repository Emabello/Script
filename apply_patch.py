"""
apply_patch.py v2 — Modifiche minime a xs_server.py.

Idempotente e ri-eseguibile:
  1. Rimuove eventuali iniezioni precedenti (vecchia "hubnav" dopo <body>).
  2. Inietta la subnav v2 dentro <div class="wrap"> (subito dopo l'apertura).
  3. Aggiorna la funzione index() per iniettare la subnav dinamicamente
     al render (usando `render_nav("ore")` di shared/nav).
  4. Estende il PIN gate a /fatture/api/* e /spese/api/*.

Uso:
    python apply_patch.py --dry-run
    python apply_patch.py
"""
import argparse
import re
import sys
from pathlib import Path

SRC = Path(__file__).parent / "xs_server.py"

# ---------------------------------------------------------------------------
# Patch 1 — index() con iniezione della subnav dentro <div class="wrap">
# ---------------------------------------------------------------------------
OLD_INDEX_PLAIN = '''@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")'''

OLD_INDEX_V1 = '''@app.get("/")
def index():
    # Navbar B2F iniettata sopra il timesheet senza toccare PAGE
    from shared.nav import render_nav
    html = PAGE.replace("<body>", "<body>\\n" + render_nav("ore"), 1)
    return Response(html, mimetype="text/html")'''

NEW_INDEX = '''@app.get("/")
def index():
    # Subnav B2F iniettata dentro <div class="wrap"> senza toccare PAGE
    from shared.nav import render_nav
    html = PAGE.replace(
        '<div class="wrap">',
        '<div class="wrap">\\n' + render_nav("ore"),
        1,
    )
    return Response(html, mimetype="text/html")'''


# ---------------------------------------------------------------------------
# Patch 2 — Gate PIN esteso a /fatture/api/* e /spese/api/*
# ---------------------------------------------------------------------------
OLD_GATE = '''    if request.path.startswith('/api/') and not session.get('ok'):
        return jsonify({'locked': True}), 401'''

NEW_GATE = '''    # Proteggi /api/*, /fatture/api/*, /spese/api/*
    p = request.path
    is_api = (p.startswith('/api/')
              or p.startswith('/fatture/api/')
              or p.startswith('/spese/api/'))
    if is_api and not session.get('ok'):
        return jsonify({'locked': True}), 401'''

NEW_GATE_MARKER = "is_api = (p.startswith('/api/')"


def apply(text: str) -> tuple[str, list[str]]:
    log = []
    out = text

    # --- Patch 1: index() ---
    if NEW_INDEX in out:
        log.append("[skip] patch 1 (subnav dentro .wrap) gia' applicata")
    elif OLD_INDEX_V1 in out:
        out = out.replace(OLD_INDEX_V1, NEW_INDEX, 1)
        log.append("[ok]   patch 1: migrata da v1 (subnav sposta in .wrap)")
    elif OLD_INDEX_PLAIN in out:
        out = out.replace(OLD_INDEX_PLAIN, NEW_INDEX, 1)
        log.append("[ok]   patch 1: applicata da xs_server originale")
    else:
        log.append("[warn] patch 1: index() non trovato in forma nota")

    # --- Patch 2: gate ---
    if NEW_GATE_MARKER in out:
        log.append("[skip] patch 2 (gate esteso) gia' applicata")
    elif OLD_GATE in out:
        out = out.replace(OLD_GATE, NEW_GATE, 1)
        log.append("[ok]   patch 2: gate esteso a /fatture/api/* e /spese/api/*")
    else:
        log.append("[warn] patch 2: gate non trovato in forma nota")

    return out, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"ERRORE: {SRC} non trovato", file=sys.stderr)
        sys.exit(1)

    original = SRC.read_text(encoding="utf-8")
    patched, log = apply(original)

    for line in log:
        print(line)

    if patched == original:
        print("Nessuna modifica necessaria.")
        return

    if args.dry_run:
        print("\n(dry-run: nessun file scritto)")
        return

    backup = SRC.with_suffix(".py.bak")
    backup.write_text(original, encoding="utf-8")
    SRC.write_text(patched, encoding="utf-8")
    print(f"\nOK. Backup salvato in {backup.name}")


if __name__ == "__main__":
    main()
