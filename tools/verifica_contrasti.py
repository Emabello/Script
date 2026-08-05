"""
Controllo contrasti WCAG sui token del design system, in tutte le
combinazioni tema x accento.

Soglie: 4.5:1 per il testo normale, 3:1 per testo grande (>=24px o
>=19px bold) e per i bordi degli elementi interattivi.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.design import CSS  # noqa: E402


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba_over(fg, alpha, bg):
    """Colore risultante di un rgba() steso su uno sfondo opaco."""
    return tuple(round(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))


def lum(rgb):
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (c(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# Token estratti dal CSS reale, non riscritti a mano.
def token(blocco, nome):
    m = re.search(re.escape(blocco) + r"\{(.*?)\n\}", CSS, re.S)
    if not m:
        m = re.search(re.escape(blocco) + r"\{(.*?)\}", CSS, re.S)
    corpo = m.group(1)
    v = re.search(rf"{re.escape(nome)}\s*:\s*([^;]+);", corpo)
    return v.group(1).strip() if v else None


TEMI = {
    "scuro": {
        "blocco": ":root", "bg": "#0c0d10", "surface": "#131519",
        "accenti": {"indigo": "#6f5cf0", "blue": "#3b8ef0",
                    "violet": "#a06bf0", "graphite": "#d6d9e0"},
        "fill": {"indigo": "#6f5cf0", "blue": "#1273e6",
                 "violet": "#9052ed", "graphite": "#d6d9e0"},
        "soft_alpha": 0.15,
        "testo": {"indigo": "#8b7cf3", "blue": "#3b8ef0",
                  "violet": "#a572f1", "graphite": "#d6d9e0"},
        "on_accent": {"indigo": "#ffffff", "blue": "#ffffff",
                      "violet": "#ffffff", "graphite": "#14161b"},
    },
    "chiaro": {
        "blocco": 'html[data-theme="light"]', "bg": "#f6f7f9", "surface": "#ffffff",
        "accenti": {"indigo": "#5343cf", "blue": "#1f6fd0",
                    "violet": "#7c45c8", "graphite": "#2b2f38"},
        "fill": {"indigo": "#5343cf", "blue": "#1f6fd0",
                 "violet": "#7c45c8", "graphite": "#2b2f38"},
        "soft_alpha": 0.11,
        "testo": {"indigo": "#5343cf", "blue": "#1e6bc9",
                  "violet": "#7c45c8", "graphite": "#2b2f38"},
        "on_accent": {"indigo": "#ffffff", "blue": "#ffffff",
                      "violet": "#ffffff", "graphite": "#ffffff"},
    },
}

TESTI = ["--ink", "--ink-2", "--ink-3", "--ink-4"]
SEMANTICI = ["--pos", "--neg", "--warn"]

problemi = []
print(f"{'tema':7} {'coppia':34} {'rapporto':>9}  soglia  esito")
print("-" * 74)

for tema, cfg in TEMI.items():
    bg = hex_to_rgb(cfg["bg"])
    surface = hex_to_rgb(cfg["surface"])

    for nome in TESTI + SEMANTICI:
        val = token(cfg["blocco"], nome)
        col = hex_to_rgb(val)
        for sfondo, etichetta in ((bg, "sfondo"), (surface, "card")):
            r = ratio(col, sfondo)
            # ink-4 e' testo disabilitato/decorativo: soglia 3:1
            soglia = 3.0 if nome == "--ink-4" else 4.5
            ok = r >= soglia
            if not ok:
                problemi.append((tema, f"{nome} su {etichetta}", r, soglia))
            print(f"{tema:7} {nome + ' su ' + etichetta:34} {r:8.2f}:1  {soglia:.1f}    "
                  f"{'ok' if ok else 'BASSO'}")

    for nome, alpha in (("--pos", .14), ("--neg", .14), ("--warn", .14)):
        col = hex_to_rgb(token(cfg["blocco"], nome))
        soft = rgba_over(col, .12 if tema == "chiaro" else alpha, surface)
        r = ratio(col, soft)
        ok = r >= 4.5
        if not ok:
            problemi.append((tema, f"chip {nome}", r, 4.5))
        print(f"{tema:7} {'chip ' + nome:34} {r:8.2f}:1  4.5    "
              f"{'ok' if ok else 'BASSO'}")

    for acc, val in cfg["accenti"].items():
        col = hex_to_rgb(val)
        on = hex_to_rgb(cfg["on_accent"][acc])
        fill = hex_to_rgb(cfg["fill"][acc])
        # testo bianco/nero sul bottone pieno (usa --accent-fill)
        r = ratio(on, fill)
        ok = r >= 4.5
        if not ok:
            problemi.append((tema, f"testo su bottone {acc}", r, 4.5))
        print(f"{tema:7} {'testo su bottone ' + acc:34} {r:8.2f}:1  4.5    "
              f"{'ok' if ok else 'BASSO'}")
        # accento come testo su card (link, valori evidenziati)
        r = ratio(col, surface)
        soglia = 3.0   # usato su numeri grandi e link con altro segnale
        ok = r >= soglia
        if not ok:
            problemi.append((tema, f"accento {acc} testo su card", r, soglia))
        print(f"{tema:7} {'accento ' + acc + ' testo su card':34} {r:8.2f}:1  3.0    "
              f"{'ok' if ok else 'BASSO'}")
        # chip: --accent-text sul proprio fondo tenue
        testo = hex_to_rgb(cfg["testo"][acc])
        soft = rgba_over(col, cfg["soft_alpha"], surface)
        r = ratio(testo, soft)
        ok = r >= 4.5
        if not ok:
            problemi.append((tema, f"chip accento {acc}", r, 4.5))
        print(f"{tema:7} {'chip accento ' + acc:34} {r:8.2f}:1  4.5    "
              f"{'ok' if ok else 'BASSO'}")

print("-" * 74)
if problemi:
    print(f"\n{len(problemi)} combinazioni sotto soglia:")
    for t, c, r, s in problemi:
        print(f"  [{t}] {c}: {r:.2f}:1 (serve {s})")
else:
    print("\nTutte le combinazioni superano la soglia.")
