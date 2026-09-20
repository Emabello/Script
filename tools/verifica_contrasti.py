"""
Controllo contrasti WCAG sui token del design system, in tutte le
combinazioni tema x accento.

Soglie: 4.5:1 per il testo normale, 3:1 per testo grande (>=24px o
>=19px bold), per il decorativo e per i bordi degli elementi
interattivi.

**Tutti i valori si leggono dal CSS vero**, nessuno riscritto qui. Prima
la palette e l'elenco degli accenti erano copiati dentro questo file:
cambiando `shared/design.py` il controllo continuava a misurare i colori
di prima e diceva "tutto ok" su una palette che non esisteva piu'. E'
successo davvero, convertendo il tema a SAP Horizon — due copie della
stessa verita', e quella che nessuno guarda e' sempre la piu' vecchia.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.design import CSS, ACCENTI  # noqa: E402


def hex_to_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba_over(valore, bg):
    """
    Colore risultante di un `rgba(r,g,b,a)` steso su uno sfondo opaco.
    Se `valore` e' gia' una tinta piena lo ritorna com'e': Horizon usa
    fondi pieni per i chip, i temi di prima usavano rgba, e il controllo
    deve reggere entrambi senza sapere quale sia in uso.
    """
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)",
                 valore.strip())
    if not m:
        return hex_to_rgb(valore)
    r, g, b = (float(m.group(i)) for i in (1, 2, 3))
    a = float(m.group(4)) if m.group(4) else 1.0
    return tuple(round(f * a + s * (1 - a)) for f, s in zip((r, g, b), bg))


def lum(rgb):
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (c(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# --- Lettura del CSS --------------------------------------------------
# I blocchi si raccolgono in ordine di documento, con la loro lista di
# selettori: risolvere un token vuol dire rigiocare la cascata sugli
# stessi selettori che applica il browser.
# I commenti si tolgono prima: `/* ... */` puo' contenere righe che
# sembrano un selettore, e il blocco vero gli finisce dentro.
_CSS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
BLOCCHI = [
    ([s.strip() for s in sel.split(",") if s.strip()], corpo)
    for sel, corpo in re.findall(r"([^{}]+)\{([^{}]*)\}", _CSS)
]


def risolvi(nome: str, selettori: list[str]) -> str | None:
    """Ultimo valore dichiarato per `nome` fra i blocchi che combaciano."""
    trovato = None
    attivi = set(selettori)
    for sels, corpo in BLOCCHI:
        if not attivi.intersection(sels):
            continue
        m = re.search(rf"{re.escape(nome)}\s*:\s*([^;]+);", corpo)
        if m:
            trovato = m.group(1).strip()
    return trovato


def selettori(tema: str, accento: str | None = None) -> list[str]:
    out = [":root"]
    if accento:
        out.append(f'html[data-accent="{accento}"]')
    if tema == "chiaro":
        out.append('html[data-theme="light"]')
        if accento:
            out.append(f'html[data-theme="light"][data-accent="{accento}"]')
    return out


TESTI = ["--ink", "--ink-2", "--ink-3", "--ink-4"]
SEMANTICI = ["--pos", "--neg", "--warn"]
SOGLIE = {"--ink-4": 3.0}

problemi = []
print(f"{'tema':7} {'coppia':34} {'rapporto':>9}  soglia  esito")
print("-" * 74)


def riga(tema, etichetta, r, soglia):
    ok = r >= soglia
    if not ok:
        problemi.append((tema, etichetta, r, soglia))
    print(f"{tema:7} {etichetta:34} {r:8.2f}:1  {soglia:.1f}    "
          f"{'ok' if ok else 'BASSO'}")


for tema in ("scuro", "chiaro"):
    base = selettori(tema)
    bg = hex_to_rgb(risolvi("--bg", base))
    surface = hex_to_rgb(risolvi("--surface", base))

    for nome in TESTI + SEMANTICI:
        col = hex_to_rgb(risolvi(nome, base))
        for sfondo, etichetta in ((bg, "sfondo"), (surface, "card")):
            riga(tema, f"{nome} su {etichetta}", ratio(col, sfondo),
                 SOGLIE.get(nome, 4.5))

    # Chip semantici: il testo sta sul proprio fondo tenue.
    for nome in SEMANTICI:
        col = hex_to_rgb(risolvi(nome, base))
        soft = rgba_over(risolvi(nome + "-soft", base), surface)
        riga(tema, f"chip {nome}", ratio(col, soft), 4.5)

    # L'indicatore critico vive in contesti grafici: gli basta 3:1.
    ind = risolvi("--warn-ind", base)
    if ind:
        riga(tema, "--warn-ind su card", ratio(hex_to_rgb(ind), surface), 3.0)

    for acc, _etichetta in ACCENTI:
        sel = selettori(tema, acc)
        col = hex_to_rgb(risolvi("--accent", sel))
        fill = hex_to_rgb(risolvi("--accent-fill", sel))
        on = hex_to_rgb(risolvi("--on-accent", sel))
        testo = hex_to_rgb(risolvi("--accent-text", sel))
        soft = rgba_over(risolvi("--accent-soft", sel), surface)

        riga(tema, f"testo su bottone {acc}", ratio(on, fill), 4.5)
        # L'accento come testo vive su numeri grandi e link, che hanno
        # sempre un secondo segnale: 3:1.
        riga(tema, f"accento {acc} testo su card", ratio(col, surface), 3.0)
        riga(tema, f"chip accento {acc}", ratio(testo, soft), 4.5)

print("-" * 74)
if problemi:
    print(f"\n{len(problemi)} combinazioni sotto soglia:")
    for t, c, r, s in problemi:
        print(f"  [{t}] {c}: {r:.2f}:1 (serve {s})")
    sys.exit(1)
print("\nTutte le combinazioni superano la soglia.")
