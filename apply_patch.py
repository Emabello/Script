"""
apply_patch.py — Modifica minima e idempotente a xs_server.py.

Applica due patch chirurgiche al tuo xs_server.py esistente:

  1. Iniezione della navbar B2F dentro il PAGE del timesheet (subito
     dopo <body>). Usa `PAGE.replace(...)`, non riscrive PAGE.
  2. Hardening del PIN gate: protegge anche /fatture/api/* e
     /spese/api/*, non solo /api/*.

Lo script è idempotente: puoi rilanciarlo, verifica se le patch sono
già applicate e nel caso salta.

Uso:
    python apply_patch.py            # applica in-place
    python apply_patch.py --dry-run  # solo mostra cosa cambierebbe

Poi committi xs_server.py modificato.
"""
import argparse
import sys
from pathlib import Path

SRC = Path(__file__).parent / "xs_server.py"

# Patch 1 — index() con iniezione navbar
OLD_INDEX = '''@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")'''

NEW_INDEX = '''@app.get("/")
def index():
    # Navbar B2F iniettata sopra il timesheet senza toccare PAGE
    from shared.nav import render_nav
    html = PAGE.replace("<body>", "<body>\\n" + render_nav("ore"), 1)
    return Response(html, mimetype="text/html")'''

# Patch 2 — gate PIN esteso a tutte le API della hub
OLD_GATE = '''    if request.path.startswith('/api/') and not session.get('ok'):
        return jsonify({'locked': True}), 401'''

NEW_GATE = '''    # Proteggi /api/*, /fatture/api/*, /spese/api/*
    p = request.path
    is_api = (p.startswith('/api/')
              or p.startswith('/fatture/api/')
              or p.startswith('/spese/api/'))
    if is_api and not session.get('ok'):
        return jsonify({'locked': True}), 401'''


def apply(text: str) -> tuple[str, list[str]]:
    """Applica le patch e restituisce (nuovo_testo, log_operazioni)."""
    log = []
    out = text

    if NEW_INDEX.split("\n")[2].strip() in out:  # marker: la nostra import
        log.append("[skip] patch 1 (navbar) gi\u00e0 applicata")
    elif OLD_INDEX in out:
        out = out.replace(OLD_INDEX, NEW_INDEX, 1)
        log.append("[ok]   patch 1 (navbar) applicata")
    else:
        log.append("[warn] patch 1: index() non trovato nella forma attesa")

    if "is_api = (p.startswith('/api/')" in out:
        log.append("[skip] patch 2 (gate) gi\u00e0 applicata")
    elif OLD_GATE in out:
        out = out.replace(OLD_GATE, NEW_GATE, 1)
        log.append("[ok]   patch 2 (gate) applicata")
    else:
        log.append("[warn] patch 2: gate non trovato nella forma attesa")

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
