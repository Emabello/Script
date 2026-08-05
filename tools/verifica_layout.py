"""
Audit di overflow orizzontale.

Se il documento e' piu' largo del viewport, i browser mobili applicano lo
shrink-to-fit e l'intera pagina viene rimpicciolita: e' quello che fa
sembrare l'app "non adattiva". Qui si misura, pagina per pagina e
larghezza per larghezza, e si elencano gli elementi colpevoli.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 5090
BASE = f"http://127.0.0.1:{PORT}"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# Larghezze CSS reali dei telefoni piu' diffusi
LARGHEZZE = [320, 360, 390, 430]

PAGINE = [
    ("home",       "/"),
    ("fatture",    "/fatture/"),
    ("storico",    "/fatture/storico"),
    ("dettaglio",  "/fatture/1"),
    ("situazione", "/fatture/situazione"),
    ("editor",     "/fatture/nuova"),
    ("modifica",   "/fatture/7/modifica"),
    ("clienti",    "/fatture/clienti"),
    ("cliente",    "/fatture/clienti/1"),
    ("spesepiva",  "/fatture/spese-piva"),
    ("movimento",  "/fatture/spese-piva/1"),
    ("parametri",  "/fatture/parametri"),
    ("emittente",  "/fatture/emittente"),
    ("spese",      "/spese/"),
    ("ore",        "/ore"),
]

SONDA = """() => {
  const de = document.documentElement;
  const vw = de.clientWidth;
  const out = {vw, scrollWidth: de.scrollWidth, colpevoli: []};
  const visti = new Set();
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    // Elementi che sforano il bordo destro del viewport
    if (r.right > vw + 1) {
      // Ignora chi sfora solo perche' e' dentro un contenitore che scorre
      let p = el, saltare = false;
      while (p && p !== document.body) {
        const st = getComputedStyle(p);
        // Dentro un contenitore che scorre, o dentro un elemento fisso
        // (tab bar, FAB): non contribuiscono alla larghezza del documento.
        if (p !== el && (st.overflowX === 'auto' || st.overflowX === 'scroll')) {
          saltare = true; break;
        }
        if (st.position === 'fixed') { saltare = true; break; }
        p = p.parentElement;
      }
      if (saltare) return;
      const sel = el.tagName.toLowerCase()
        + (el.id ? '#' + el.id : '')
        + (el.className && typeof el.className === 'string'
           ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
      if (visti.has(sel)) return;
      visti.add(sel);
      out.colpevoli.push({
        sel,
        right: Math.round(r.right),
        width: Math.round(r.width),
        testo: (el.textContent || '').trim().slice(0, 48),
      });
    }
  });
  return out;
}"""


def serve():
    preview.application.run(host="127.0.0.1", port=PORT, debug=False,
                            use_reloader=False, threaded=True)


def main():
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(2)

    guasti = 0
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        for w in LARGHEZZE:
            ctx = b.new_context(viewport={"width": w, "height": 800},
                                device_scale_factor=3, is_mobile=True,
                                has_touch=True)
            pg = ctx.new_page()
            print(f"\n{'=' * 68}\n  VIEWPORT {w}px\n{'=' * 68}")
            for nome, url in PAGINE:
                pg.goto(BASE + url, wait_until="domcontentloaded", timeout=15000)
                pg.wait_for_timeout(350)
                d = pg.evaluate(SONDA)
                extra = d["scrollWidth"] - d["vw"]
                stato = "ok" if extra <= 0 else f"SFORA +{extra}px"
                print(f"  {nome:11} viewport {d['vw']:4}  documento {d['scrollWidth']:4}  {stato}")
                if extra > 0:
                    guasti += 1
                    for c in d["colpevoli"][:6]:
                        print(f"       -> {c['sel'][:66]}")
                        print(f"          largo {c['width']}px, bordo destro a {c['right']}px"
                              f"  «{c['testo']}»")
            ctx.close()
        b.close()

    print(f"\n{'=' * 68}")
    print("nessun overflow" if guasti == 0 else f"{guasti} pagine con overflow")
    return guasti


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
