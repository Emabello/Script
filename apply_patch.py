"""
apply_patch.py v3 — Sposta il timesheet da / a /ore + rimuove le
iniezioni precedenti (v1 hubnav / v2 subnav).

Modifiche a xs_server.py:
  1. Rotta index() cambia da @app.get("/")  a  @app.get("/ore").
     La funzione torna a fare return Response(PAGE, ...) puro: la
     personalizzazione (header con logo B2F back button) e' iniettata
     dal server SU RICHIESTA (non nel PAGE statico).
  2. Aggiorna ALLOW_NO_PIN per aggiungere i KPI del launchpad e la
     rotta 'launchpad' se registrata.
  3. Rimuove eventuale patch v1/v2 sull'index (idempotente).
  4. Gate PIN esteso (gia' in ALLOW_NO_PIN o via /api/ path).
"""
import argparse
import sys
from pathlib import Path

SRC = Path(__file__).parent / "xs_server.py"

INDEX_PLAIN = '''@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")'''

INDEX_V1 = '''@app.get("/")
def index():
    # Navbar B2F iniettata sopra il timesheet senza toccare PAGE
    from shared.nav import render_nav
    html = PAGE.replace("<body>", "<body>\\n" + render_nav("ore"), 1)
    return Response(html, mimetype="text/html")'''

INDEX_V2 = '''@app.get("/")
def index():
    # Subnav B2F iniettata dentro <div class="wrap"> senza toccare PAGE
    from shared.nav import render_nav
    html = PAGE.replace(
        '<div class="wrap">',
        '<div class="wrap">\\n' + render_nav("ore"),
        1,
    )
    return Response(html, mimetype="text/html")'''

INDEX_V3 = '''@app.get("/ore")
def index():
    # Timesheet: iniettiamo l'header B2F (logo cliccabile back-to-home
    # + toggle tema) subito dentro <div class="wrap">, poi lasciamo il
    # PAGE intatto.
    from shared.theme import inject_app_header
    html = inject_app_header(PAGE, eyebrow="Timesheet",
                             title_html='Le mie <em>ore</em>')
    return Response(html, mimetype="text/html")'''

# --- Gate PIN ---
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

# --- ALLOW_NO_PIN: aggiunge launchpad e KPI ---
# La riga esistente e' del tipo:
#   ALLOW_NO_PIN = {'index', 'manifest', 'icon192', 'icon512', ...}
# Aggiungiamo 'launchpad', 'kpi_fatture', 'kpi_spese', 'health'
ALLOW_ADDITIONS = ["launchpad", "kpi_fatture", "kpi_spese", "health"]


def _patch_allow_no_pin(text: str, log: list) -> str:
    """Aggiunge nuovi endpoint a ALLOW_NO_PIN se non gia' presenti."""
    marker = "ALLOW_NO_PIN = {"
    idx = text.find(marker)
    if idx < 0:
        log.append("[warn] ALLOW_NO_PIN non trovato")
        return text
    # Trova la fine della definizione (prima '}' dopo idx)
    end = text.find("}", idx)
    if end < 0:
        return text
    block = text[idx:end + 1]
    already = block  # semplice check di stringa
    to_add = []
    for name in ALLOW_ADDITIONS:
        if f"'{name}'" not in already and f'"{name}"' not in already:
            to_add.append(f"'{name}'")
    if not to_add:
        log.append("[skip] ALLOW_NO_PIN gia' aggiornato")
        return text
    inserted = ", " + ", ".join(to_add) + "}"
    new_block = block.replace("}", inserted, 1)
    log.append(f"[ok]   ALLOW_NO_PIN: aggiunti {', '.join(to_add)}")
    return text.replace(block, new_block, 1)


def apply(text: str) -> tuple[str, list[str]]:
    log = []
    out = text

    # Patch 1: index()
    if INDEX_V3 in out:
        log.append("[skip] patch 1 (route /ore) gia' applicata")
    elif INDEX_V2 in out:
        out = out.replace(INDEX_V2, INDEX_V3, 1)
        log.append("[ok]   patch 1: migrata da v2 -> v3 (/ -> /ore, no subnav)")
    elif INDEX_V1 in out:
        out = out.replace(INDEX_V1, INDEX_V3, 1)
        log.append("[ok]   patch 1: migrata da v1 -> v3")
    elif INDEX_PLAIN in out:
        out = out.replace(INDEX_PLAIN, INDEX_V3, 1)
        log.append("[ok]   patch 1: applicata da xs_server originale")
    else:
        log.append("[warn] patch 1: index() non trovato in forma nota")

    # Patch 2: gate PIN
    if NEW_GATE_MARKER in out:
        log.append("[skip] patch 2 (gate esteso) gia' applicata")
    elif OLD_GATE in out:
        out = out.replace(OLD_GATE, NEW_GATE, 1)
        log.append("[ok]   patch 2: gate esteso")
    else:
        log.append("[warn] patch 2: gate non trovato")

    # Patch 3: ALLOW_NO_PIN
    out = _patch_allow_no_pin(out, log)

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
