"""
shared/theme.py — Tema visivo condiviso B2F.

Estrae il design system del timesheet "Le mie ore" (Space Grotesk +
Inter, palette dark con accento indaco/violetto, superfici scure
profonde e page-bg radiale) e lo espone come funzione `render_page()`
riusabile dalle sezioni fatture e spese.

Il tema segue automaticamente `data-theme` in localStorage sotto la
chiave `xs-theme` (default `dark`), la stessa usata dal timesheet:
cambi tema una volta, cambia dappertutto.
"""

# CSS del tema — estratto e ridotto dal PAGE di xs_server.
# Le classi qui replicate: .wrap .top .brand .eyebrow .serif .rule
# .icon-btn .card .btn .subnav.
_CSS = r"""
:root{
  --bg:#0b0c10; --panel:#13151c; --card:#171a21; --ink:#f3f4f9; --ink-dim:#c4c7d4;
  --muted:#8b8fa3; --faint:#565a6b; --line:rgba(255,255,255,.07); --line-strong:rgba(255,255,255,.13);
  --gold:#7c6cff; --gold-deep:#5a49d1; --emerald:#2dd4bf; --danger:#ff6b81;
  --on-gold:#ffffff; --input-bg:#0f1117; --card-grad:linear-gradient(180deg,#191c25,#14161d);
  --page-bg:radial-gradient(1100px 620px at 82% -12%,rgba(124,108,255,.16),transparent 60%),
            radial-gradient(880px 520px at 4% 2%,rgba(45,212,191,.08),transparent 55%),#0b0c10;
  --display:'Space Grotesk',system-ui,sans-serif;
  --r:20px; --r-sm:13px;
  --shadow:0 30px 70px -34px rgba(0,0,0,.75),0 4px 14px -6px rgba(0,0,0,.5);
}
html[data-theme="light"]{
  --bg:#eef0f5; --panel:#ffffff; --card:#ffffff; --ink:#181a22; --ink-dim:#414556;
  --muted:#6c7182; --faint:#a6abbb; --line:rgba(20,22,33,.08); --line-strong:rgba(20,22,33,.15);
  --gold:#5b49d1; --gold-deep:#4534ad; --emerald:#0d9488; --danger:#e11d48;
  --on-gold:#ffffff; --input-bg:#f5f6fb; --card-grad:linear-gradient(180deg,#ffffff,#f7f7fd);
  --page-bg:radial-gradient(1100px 620px at 82% -12%,rgba(91,73,209,.12),transparent 60%),
            radial-gradient(880px 520px at 4% 2%,rgba(13,148,136,.07),transparent 55%),#eef0f5;
  --shadow:0 28px 60px -34px rgba(40,34,90,.4),0 3px 12px -6px rgba(0,0,0,.12);
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);
  font-family:Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
  line-height:1.5;-webkit-tap-highlight-color:transparent}
body{min-height:100vh;background:var(--page-bg);transition:background .3s,color .3s}
a{color:inherit}
.serif{font-family:var(--display);letter-spacing:-.01em}
.eyebrow{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);font-weight:500}
.tnum{font-variant-numeric:tabular-nums}
button{font:inherit;cursor:pointer;border:none;background:none;color:inherit}
.wrap{max-width:600px;margin:0 auto;padding:26px 18px 80px}

.top{display:flex;align-items:flex-end;gap:16px}
.brand .eyebrow{margin-bottom:5px}
.brand h1{font-family:var(--display);font-weight:400;font-size:32px;line-height:1;
  margin:0;letter-spacing:-.01em}
.brand h1 em{font-style:italic;color:var(--gold)}
.spacer{flex:1}
.icon-btn{width:42px;height:42px;border-radius:50%;border:1px solid var(--line-strong);
  display:grid;place-items:center;color:var(--ink-dim);transition:.2s}
.icon-btn:active{transform:scale(.92)}
.icon-btn:hover{border-color:var(--gold);color:var(--gold)}
.icon-btn svg{width:19px;height:19px}
.rule{height:1px;background:linear-gradient(90deg,var(--gold-deep),transparent 70%);
  opacity:.5;margin:18px 0 20px}

/* Sub-navigazione fra le 3 aree */
.subnav{display:flex;gap:6px;padding:5px;background:var(--card-grad);
  border:1px solid var(--line);border-radius:999px;box-shadow:var(--shadow);
  margin:0 0 22px}
.subnav a{flex:1;text-align:center;text-decoration:none;color:var(--ink-dim);
  font-size:13px;font-weight:500;padding:9px 6px;border-radius:999px;
  transition:.18s;letter-spacing:.01em}
.subnav a:hover{color:var(--ink)}
.subnav a.is-active{background:var(--gold);color:var(--on-gold);
  box-shadow:0 6px 18px -8px rgba(124,108,255,.6)}
html[data-theme="light"] .subnav a.is-active{
  box-shadow:0 6px 18px -8px rgba(91,73,209,.55)}

/* Card generica */
.card{background:var(--card-grad);border:1px solid var(--line);border-radius:var(--r);
  padding:20px;box-shadow:var(--shadow);margin-bottom:14px}
.card h2{font-family:var(--display);font-weight:500;font-size:18px;margin:0 0 6px;
  letter-spacing:-.01em}
.card .lead{color:var(--ink-dim);font-size:14px;margin:0 0 12px}

/* Statistica grande */
.stat{display:flex;align-items:baseline;gap:12px}
.stat .num{font-family:var(--display);font-size:42px;line-height:1;color:var(--gold);
  font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat .lbl{color:var(--muted);font-size:12px;letter-spacing:.14em;text-transform:uppercase}

/* Griglia di card compatte */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid .card{margin:0;padding:16px}
.grid .num{font-size:28px}

/* Riga tabellare (ultime spese, righe lista) */
.rows{display:flex;flex-direction:column}
.row{display:grid;grid-template-columns:auto 1fr auto;gap:12px;padding:11px 4px;
  border-bottom:1px solid var(--line);align-items:center}
.row:last-child{border-bottom:0}
.row .d{font-family:var(--display);font-size:12px;color:var(--muted);white-space:nowrap;
  font-variant-numeric:tabular-nums}
.row .t{font-size:14px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .a{font-variant-numeric:tabular-nums;font-size:14px;font-weight:500}
.row .a.neg{color:var(--danger)}
.row .a.pos{color:var(--emerald)}

/* Bottoni */
.btn{display:inline-flex;align-items:center;gap:8px;padding:11px 18px;
  background:var(--gold);color:var(--on-gold);border-radius:999px;text-decoration:none;
  font-weight:600;font-size:14px;transition:.15s;
  box-shadow:0 12px 30px -14px rgba(124,108,255,.6)}
.btn:hover{transform:translateY(-1px);background:var(--gold-deep)}
.btn.ghost{background:transparent;border:1px solid var(--line-strong);color:var(--ink-dim);
  box-shadow:none}
.btn.ghost:hover{border-color:var(--gold);color:var(--gold)}
.btn[disabled],.btn.is-disabled{opacity:.45;pointer-events:none}

/* Alert / warn */
.notice{padding:14px 16px;border-radius:var(--r-sm);border:1px solid var(--line);
  background:rgba(124,108,255,.06);color:var(--ink-dim);font-size:13.5px;line-height:1.5}
.notice.warn{border-color:rgba(255,180,80,.28);background:rgba(255,180,80,.08);color:var(--ink-dim)}
.notice.err{border-color:rgba(255,107,129,.28);background:rgba(255,107,129,.08);color:var(--danger)}
.notice code{font-family:ui-monospace,'JetBrains Mono',monospace;font-size:12.5px;
  padding:1px 6px;border-radius:4px;background:rgba(255,255,255,.06)}
html[data-theme="light"] .notice code{background:rgba(0,0,0,.05)}

/* Placeholder icons/svg helpers */
.i{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.75;
  stroke-linecap:round;stroke-linejoin:round;vertical-align:-3px}
"""

_HEAD = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<script>document.documentElement.dataset.theme=localStorage.getItem("xs-theme")||"dark";</script>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITLE__</title>
<meta name="theme-color" content="#0b0c10">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="B2F">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>__CSS__</style>
</head>
"""

_SUBNAV = """
<nav class="subnav" aria-label="Sezioni">
  <a href="/"        class="__CLS_ORE__">Ore</a>
  <a href="/fatture" class="__CLS_FAT__">Fatture</a>
  <a href="/spese"   class="__CLS_SPE__">Spese</a>
</nav>
"""

_HEADER = """
<div class="top">
  <div class="brand">
    <div class="eyebrow">__EYEBROW__</div>
    <h1 class="serif">__TITLE_HTML__</h1>
  </div>
  <div class="spacer"></div>
  <button class="icon-btn" id="themeToggle" title="Cambia tema"
          onclick="const h=document.documentElement;const n=h.dataset.theme==='dark'?'light':'dark';h.dataset.theme=n;localStorage.setItem('xs-theme',n);">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>
    </svg>
  </button>
</div>
<div class="rule"></div>
"""


def render_page(section: str, eyebrow: str, title_html: str, content: str) -> str:
    """
    Renderizza una pagina completa in stile timesheet.

    Args:
      section     : 'ore' | 'fatture' | 'spese' — evidenzia la subnav
      eyebrow     : la stringa piccola in maiuscolo sopra il titolo
      title_html  : il testo del titolo H1 (puoi usare <em>...</em>)
      content     : HTML del corpo pagina (di solito .card...)
    """
    head = _HEAD.replace("__TITLE__", eyebrow.title() + " — B2F").replace("__CSS__", _CSS)
    subnav = (_SUBNAV
              .replace("__CLS_ORE__", "is-active" if section == "ore" else "")
              .replace("__CLS_FAT__", "is-active" if section == "fatture" else "")
              .replace("__CLS_SPE__", "is-active" if section == "spese" else ""))
    header = _HEADER.replace("__EYEBROW__", eyebrow).replace("__TITLE_HTML__", title_html)
    return f"""{head}
<body>
  <div class="wrap">
    {subnav}
    {header}
    {content}
  </div>
</body>
</html>"""
