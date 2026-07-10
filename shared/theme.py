"""
shared/theme.py v2 — Tema visivo condiviso B2F, in stile Fiori Launchpad.

Struttura:
  /              -> render_launchpad() : hero con 3 tile in colonna + KPI live
  /ore /fatture /spese
                 -> render_page()      : header con logo B2F cliccabile
                                         (back-to-home) + toggle tema

Design system:
  - Font: Space Grotesk (display) + Inter (body)
  - Palette: dark (default) con --gold indaco; light disponibile tramite
    toggle in alto a destra, persistita in localStorage 'xs-theme'.
  - Mobile-first: max-width 560px, padding compatti, touch target >= 44px.
"""

_CSS = r"""
:root{
  --bg:#0b0c10; --panel:#13151c; --card:#171a21; --ink:#f3f4f9; --ink-dim:#c4c7d4;
  --muted:#8b8fa3; --faint:#565a6b;
  --line:rgba(255,255,255,.07); --line-strong:rgba(255,255,255,.13);
  --gold:#7c6cff; --gold-deep:#5a49d1; --emerald:#2dd4bf; --danger:#ff6b81; --amber:#f5b568;
  --on-gold:#ffffff; --input-bg:#0f1117;
  --card-grad:linear-gradient(180deg,#191c25,#14161d);
  --tile-hover:linear-gradient(180deg,#1e2130,#17192a);
  --page-bg:radial-gradient(1100px 620px at 82% -12%,rgba(124,108,255,.16),transparent 60%),
            radial-gradient(880px 520px at 4% 2%,rgba(45,212,191,.08),transparent 55%),#0b0c10;
  --display:'Space Grotesk',system-ui,sans-serif;
  --r:20px; --r-sm:13px;
  --shadow:0 30px 70px -34px rgba(0,0,0,.75),0 4px 14px -6px rgba(0,0,0,.5);
  --shadow-tile:0 20px 44px -22px rgba(0,0,0,.6),0 2px 8px -4px rgba(0,0,0,.4);
}
html[data-theme="light"]{
  --bg:#eef0f5; --panel:#ffffff; --card:#ffffff; --ink:#181a22; --ink-dim:#414556;
  --muted:#6c7182; --faint:#a6abbb;
  --line:rgba(20,22,33,.08); --line-strong:rgba(20,22,33,.15);
  --gold:#5b49d1; --gold-deep:#4534ad; --emerald:#0d9488; --danger:#e11d48; --amber:#c48214;
  --on-gold:#ffffff; --input-bg:#f5f6fb;
  --card-grad:linear-gradient(180deg,#ffffff,#f7f7fd);
  --tile-hover:linear-gradient(180deg,#f7f7fd,#eef0fb);
  --page-bg:radial-gradient(1100px 620px at 82% -12%,rgba(91,73,209,.12),transparent 60%),
            radial-gradient(880px 520px at 4% 2%,rgba(13,148,136,.07),transparent 55%),#eef0f5;
  --shadow:0 28px 60px -34px rgba(40,34,90,.4),0 3px 12px -6px rgba(0,0,0,.12);
  --shadow-tile:0 18px 40px -22px rgba(40,34,90,.28),0 2px 8px -4px rgba(0,0,0,.08);
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

.wrap{max-width:560px;margin:0 auto;padding:18px 18px 90px}

/* ---------- Header comune (app + launchpad) ---------- */
.apphead{display:flex;align-items:center;gap:14px;margin:0 0 22px;min-height:44px}
.applogo{width:44px;height:44px;border-radius:14px;background:var(--card-grad);
  border:1px solid var(--line-strong);display:grid;place-items:center;
  color:var(--ink);text-decoration:none;transition:.18s;flex-shrink:0;
  box-shadow:var(--shadow-tile)}
.applogo:active{transform:scale(.94)}
.applogo:hover{border-color:var(--gold);color:var(--gold)}
.applogo .mono{font-family:var(--display);font-weight:600;font-size:14px;letter-spacing:.02em}
.applogo.brand-only{cursor:default}
.applogo.brand-only:hover{border-color:var(--line-strong);color:var(--ink)}
.appttl{flex:1;min-width:0}
.appttl .eyebrow{margin-bottom:2px}
.appttl h1{font-family:var(--display);font-weight:400;font-size:24px;line-height:1.1;
  margin:0;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.appttl h1 em{font-style:italic;color:var(--gold)}
.icon-btn{width:44px;height:44px;border-radius:50%;border:1px solid var(--line-strong);
  display:grid;place-items:center;color:var(--ink-dim);transition:.2s;background:transparent;
  flex-shrink:0}
.icon-btn:active{transform:scale(.92)}
.icon-btn:hover{border-color:var(--gold);color:var(--gold)}
.icon-btn svg{width:19px;height:19px}

/* ---------- Launchpad hero + tile ---------- */
.hero{margin:8px 0 26px}
.hero .greet{font-family:var(--display);font-weight:400;font-size:28px;line-height:1.15;
  letter-spacing:-.01em;color:var(--ink);margin:0}
.hero .greet em{font-style:italic;color:var(--gold)}
.hero .sub{color:var(--muted);font-size:14px;margin-top:4px}

.tiles{display:flex;flex-direction:column;gap:12px}
.tile{display:flex;align-items:center;gap:14px;padding:18px;
  background:var(--card-grad);border:1px solid var(--line);border-radius:var(--r);
  box-shadow:var(--shadow-tile);text-decoration:none;color:var(--ink);
  min-height:88px;transition:transform .18s ease,background .18s;position:relative}
.tile:active{transform:scale(.985)}
@media (hover:hover){.tile:hover{background:var(--tile-hover);border-color:var(--line-strong)}}
.tile .ic{width:52px;height:52px;border-radius:var(--r-sm);background:rgba(124,108,255,.12);
  color:var(--gold);display:grid;place-items:center;flex-shrink:0}
html[data-theme="light"] .tile .ic{background:rgba(91,73,209,.1)}
.tile .ic svg{width:26px;height:26px;stroke:currentColor;fill:none;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
.tile .info{flex:1;min-width:0}
.tile .info .name{font-family:var(--display);font-weight:500;font-size:19px;
  line-height:1.15;color:var(--ink);margin:0 0 3px;letter-spacing:-.005em}
.tile .info .kpi{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;
  transition:color .18s}
.tile .info .kpi strong{color:var(--ink-dim);font-weight:500}
.tile .info .kpi.pos strong{color:var(--emerald)}
.tile .info .kpi.neg strong{color:var(--danger)}
.tile .go{color:var(--faint);flex-shrink:0}
.tile .go svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;
  stroke-linecap:round;stroke-linejoin:round}
@media (hover:hover){.tile:hover .go{color:var(--gold)}}

/* ---------- Card generica ---------- */
.card{background:var(--card-grad);border:1px solid var(--line);border-radius:var(--r);
  padding:18px;box-shadow:var(--shadow);margin-bottom:12px}
.card h2{font-family:var(--display);font-weight:500;font-size:17px;margin:0 0 6px;
  letter-spacing:-.01em}

/* Statistica grande */
.stat{display:flex;align-items:baseline;gap:12px}
.stat .num{font-family:var(--display);font-size:38px;line-height:1;color:var(--gold);
  font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat .lbl{color:var(--muted);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase}

.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid2 .card{margin:0;padding:14px}
.grid2 .num{font-size:26px}

/* Righe tabellari */
.rows{display:flex;flex-direction:column}
.row{display:grid;grid-template-columns:auto 1fr auto;gap:12px;padding:10px 2px;
  border-bottom:1px solid var(--line);align-items:center}
.row:last-child{border-bottom:0}
.row .d{font-family:var(--display);font-size:12px;color:var(--muted);white-space:nowrap;
  font-variant-numeric:tabular-nums}
.row .t{font-size:14px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .a{font-variant-numeric:tabular-nums;font-size:14px;font-weight:500}
.row .a.neg{color:var(--danger)}
.row .a.pos{color:var(--emerald)}

/* Bottoni */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;
  padding:12px 18px;background:var(--gold);color:var(--on-gold);border-radius:999px;
  text-decoration:none;font-weight:600;font-size:14px;transition:.15s;min-height:44px;
  box-shadow:0 12px 30px -14px rgba(124,108,255,.6)}
.btn:active{transform:translateY(1px)}
@media (hover:hover){.btn:hover{background:var(--gold-deep)}}
.btn.ghost{background:transparent;border:1px solid var(--line-strong);color:var(--ink-dim);
  box-shadow:none}
@media (hover:hover){.btn.ghost:hover{border-color:var(--gold);color:var(--gold)}}
.btn[disabled],.btn.is-disabled{opacity:.45;pointer-events:none}

.notice{padding:13px 15px;border-radius:var(--r-sm);border:1px solid var(--line);
  background:rgba(124,108,255,.06);color:var(--ink-dim);font-size:13.5px;line-height:1.5}
.notice.warn{border-color:rgba(245,181,104,.28);background:rgba(245,181,104,.08);color:var(--ink-dim)}
.notice.err{border-color:rgba(255,107,129,.28);background:rgba(255,107,129,.08);color:var(--danger)}
.notice code{font-family:ui-monospace,'JetBrains Mono',monospace;font-size:12.5px;
  padding:1px 6px;border-radius:4px;background:rgba(255,255,255,.06)}
html[data-theme="light"] .notice code{background:rgba(0,0,0,.05)}

/* Skeleton per KPI in caricamento */
.skel{display:inline-block;height:.75em;width:6em;border-radius:4px;vertical-align:-1px;
  background:linear-gradient(90deg,rgba(255,255,255,.06),rgba(255,255,255,.14),rgba(255,255,255,.06));
  background-size:200% 100%;animation:sk 1.2s linear infinite}
html[data-theme="light"] .skel{
  background:linear-gradient(90deg,rgba(0,0,0,.05),rgba(0,0,0,.12),rgba(0,0,0,.05));
  background-size:200% 100%}
@keyframes sk{0%{background-position:200% 0}100%{background-position:-200% 0}}
"""

_HEAD_TPL = """<!DOCTYPE html>
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
__PREFETCH__
<style>__CSS__</style>
</head>"""

_MOON_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>')

_THEME_TOGGLE = f"""<button class="icon-btn" title="Cambia tema"
  onclick="const h=document.documentElement;const n=h.dataset.theme==='dark'?'light':'dark';
  h.dataset.theme=n;localStorage.setItem('xs-theme',n);">
  {_MOON_SVG}
</button>"""


def _head(title: str, prefetch: list[str] | None = None) -> str:
    pf = "".join(f'<link rel="prefetch" href="{u}">' for u in (prefetch or []))
    return (_HEAD_TPL
            .replace("__TITLE__", title)
            .replace("__CSS__", _CSS)
            .replace("__PREFETCH__", pf))


def inject_app_header(page_html: str, eyebrow: str, title_html: str) -> str:
    """
    Inietta nel PAGE del timesheet l'header B2F (logo cliccabile back
    + toggle tema esterno), subito dentro <div class="wrap">.

    Il timesheet ha gia' i suoi font, palette e toggle tema propri.
    Iniettiamo solo il logo B2F cliccabile in alto a sx come back
    button, con uno stile compatto che riprende le variabili del
    timesheet (--gold, --line, --ink, --card-grad). Nessuna
    ridefinizione di font o palette.
    """
    del eyebrow, title_html  # riservati per estensioni future
    # Blocco: piccolo pill B2F cliccabile che riporta a /
    header = """<style>
.b2f-back{display:inline-flex;align-items:center;gap:8px;padding:6px 12px 6px 6px;
  border:1px solid var(--line-strong);border-radius:999px;text-decoration:none;
  color:var(--ink-dim);background:var(--card-grad);
  font-size:12.5px;font-weight:500;letter-spacing:.02em;
  margin:0 0 16px;transition:.18s}
.b2f-back:active{transform:scale(.96)}
.b2f-back:hover{border-color:var(--gold);color:var(--gold)}
.b2f-back .glyph{width:26px;height:26px;border-radius:50%;background:rgba(124,108,255,.16);
  color:var(--gold);display:grid;place-items:center;
  font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:10.5px;letter-spacing:.02em}
html[data-theme="light"] .b2f-back .glyph{background:rgba(91,73,209,.14)}
</style>
<a class="b2f-back" href="/" aria-label="Torna alla home">
  <span class="glyph">B2F</span>
  <span>Home</span>
</a>
"""
    return page_html.replace(
        '<div class="wrap">',
        '<div class="wrap">\n' + header,
        1,
    )


def render_page(section: str, eyebrow: str, title_html: str, content: str) -> str:
    """
    Pagina di sotto-app (Ore, Fatture, Spese).
    Header: logo B2F cliccabile (back to /) + titolo + toggle tema.
    """
    title = f"{eyebrow} — B2F"
    head = _head(title)
    return f"""{head}
<body>
  <div class="wrap">
    <div class="apphead">
      <a href="/" class="applogo" aria-label="Torna alla home">
        <span class="mono">B2F</span>
      </a>
      <div class="appttl">
        <div class="eyebrow">{eyebrow}</div>
        <h1 class="serif">{title_html}</h1>
      </div>
      {_THEME_TOGGLE}
    </div>
    {content}
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------
# Launchpad
# ---------------------------------------------------------------------

# Icone SVG delle 3 app
_ICON_ORE = ('<svg viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="16" rx="3"/>'
             '<path d="M3 9h18"/><path d="M8 3v3M16 3v3"/>'
             '<circle cx="12" cy="14.5" r="3.2"/><path d="M12 13v1.6l1.2 1"/></svg>')
_ICON_FAT = ('<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/>'
             '<path d="M14 3v4h5"/><path d="M9 12h6M9 15h6M9 18h4"/></svg>')
_ICON_SPE = ('<svg viewBox="0 0 24 24"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h13A2.5 2.5 0 0 1 21 6.5V8H3z"/>'
             '<path d="M3 8v9.5A2.5 2.5 0 0 0 5.5 20h13a2.5 2.5 0 0 0 2.5-2.5V8"/>'
             '<circle cx="16.5" cy="14" r="1.3"/></svg>')

_CHEVRON = ('<svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>')


def render_launchpad(greet_name: str | None = None) -> str:
    """
    Home / Launchpad in stile Fiori.
    KPI live vengono caricati asincroni dopo il rendering (fetch a
    /api/kpi/fatture e /api/kpi/spese). Le Ore hanno sottotitolo statico.
    """
    who = (greet_name or "").strip()
    hi = f'Ciao <em>{who}</em>' if who else 'Ciao <em>tu</em>'
    head = _head("B2F — Home", prefetch=["/ore", "/fatture", "/spese"])

    return f"""{head}
<body>
  <div class="wrap">
    <div class="apphead">
      <div class="applogo brand-only" aria-hidden="true">
        <span class="mono">B2F</span>
      </div>
      <div class="appttl">
        <div class="eyebrow">Launchpad</div>
        <h1 class="serif">Hub</h1>
      </div>
      {_THEME_TOGGLE}
    </div>

    <div class="hero">
      <div class="greet">{hi}</div>
      <div class="sub">Scegli un'app per iniziare.</div>
    </div>

    <div class="tiles">
      <a class="tile" href="/ore" data-app="ore">
        <div class="ic">{_ICON_ORE}</div>
        <div class="info">
          <div class="name">Ore</div>
          <div class="kpi">Consulta e inserisci le ore lavorate</div>
        </div>
        <div class="go">{_CHEVRON}</div>
      </a>

      <a class="tile" href="/fatture" data-app="fatture">
        <div class="ic">{_ICON_FAT}</div>
        <div class="info">
          <div class="name">Fatture</div>
          <div class="kpi" id="kpi-fatture"><span class="skel"></span></div>
        </div>
        <div class="go">{_CHEVRON}</div>
      </a>

      <a class="tile" href="/spese" data-app="spese">
        <div class="ic">{_ICON_SPE}</div>
        <div class="info">
          <div class="name">Spese</div>
          <div class="kpi" id="kpi-spese"><span class="skel"></span></div>
        </div>
        <div class="go">{_CHEVRON}</div>
      </a>
    </div>
  </div>

<script>
// KPI live: fetch in parallelo dopo il render della pagina
(async () => {{
  const fmtEur = (v) => new Intl.NumberFormat('it-IT',
      {{style:'decimal', minimumFractionDigits:2, maximumFractionDigits:2}}).format(Math.abs(v));

  const setKpi = (id, html, sign) => {{
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = html;
    if (sign === 'pos') el.classList.add('pos');
    if (sign === 'neg') el.classList.add('neg');
  }};

  // Fatture: n. quest'anno, totale imponibile
  fetch('/api/kpi/fatture', {{cache:'no-store'}})
    .then(r => r.ok ? r.json() : null)
    .then(d => {{
      if (!d) return setKpi('kpi-fatture', 'Nuova fattura, storico, clienti');
      const n = d.count_anno ?? 0;
      const anno = d.anno ?? new Date().getFullYear();
      const parts = [`<strong>${{n}}</strong> fattur${{n===1?'a':'e'}} nel ${{anno}}`];
      if (d.imponibile_mese != null) parts.push(`+€ <strong>${{fmtEur(d.imponibile_mese)}}</strong> questo mese`);
      setKpi('kpi-fatture', parts.join(' · '));
    }})
    .catch(() => setKpi('kpi-fatture', 'Nuova fattura, storico, clienti'));

  // Spese: saldo mese corrente
  fetch('/api/kpi/spese', {{cache:'no-store'}})
    .then(r => r.ok ? r.json() : null)
    .then(d => {{
      if (!d) return setKpi('kpi-spese', 'Movimenti, filtri, inserimento');
      const s = d.saldo_mese;
      const sign = s > 0 ? 'pos' : s < 0 ? 'neg' : null;
      const symbol = s >= 0 ? '+' : '\u2212';
      setKpi('kpi-spese',
        `Saldo mese <strong>${{symbol}}€ ${{fmtEur(s)}}</strong>`, sign);
    }})
    .catch(() => setKpi('kpi-spese', 'Movimenti, filtri, inserimento'));
}})();
</script>
</body>
</html>"""
