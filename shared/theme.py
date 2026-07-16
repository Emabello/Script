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

.wrap{max-width:560px;margin:0 auto;
  padding:calc(18px + env(safe-area-inset-top,0px)) calc(18px + env(safe-area-inset-right,0px)) calc(90px + env(safe-area-inset-bottom,0px)) calc(18px + env(safe-area-inset-left,0px))}

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
.notice.bio{display:none;align-items:center;justify-content:space-between;gap:10px;
  margin-bottom:16px}
.notice.bio.show{display:flex}
.notice.bio button{color:var(--gold);font-weight:600;white-space:nowrap}

/* ---------- Form ---------- */
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.field label{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);font-weight:500}
.field .hint{font-size:11.5px;color:var(--faint);margin-top:2px}
.field input,.field select,.field textarea{
  font-family:inherit;font-size:14.5px;color:var(--ink);
  background:var(--input-bg);border:1px solid var(--line-strong);border-radius:12px;
  padding:11px 13px;transition:border-color .15s,background .15s;width:100%;min-height:44px}
.field input:focus,.field select:focus,.field textarea:focus{
  outline:none;border-color:var(--gold)}
.field textarea{min-height:80px;resize:vertical;font-family:inherit}
.field.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.field.row2>.field{margin-bottom:0}
.field-group{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.field-group.c3{grid-template-columns:2fr 1fr 1fr}
@media (max-width:420px){.field-group,.field-group.c3{grid-template-columns:1fr}}

/* Actions bar */
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.actions .btn{flex:1;min-width:100px}

/* Chip / badge */
.chip{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:999px;
  font-size:11.5px;font-weight:500;letter-spacing:.03em;
  background:rgba(124,108,255,.12);color:var(--gold)}
html[data-theme="light"] .chip{background:rgba(91,73,209,.1)}
.chip.g{background:rgba(45,212,191,.12);color:var(--emerald)}
.chip.r{background:rgba(255,107,129,.12);color:var(--danger)}
.chip.a{background:rgba(245,181,104,.14);color:var(--amber)}
.chip.n{background:rgba(139,143,163,.14);color:var(--muted)}

/* Lista di elementi cliccabili (clienti, fatture) */
.list{display:flex;flex-direction:column;gap:8px}
.list .item{display:flex;gap:12px;padding:14px;background:var(--card-grad);
  border:1px solid var(--line);border-radius:var(--r-sm);text-decoration:none;
  color:var(--ink);transition:.15s;box-shadow:var(--shadow-tile);min-height:60px;
  align-items:center}
.list .item:active{transform:scale(.985)}
@media (hover:hover){.list .item:hover{border-color:var(--gold);background:var(--tile-hover)}}
.list .item .info{flex:1;min-width:0}
.list .item .info .n{font-size:15px;font-weight:500;color:var(--ink);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:0 0 2px}
.list .item .info .m{font-size:12.5px;color:var(--muted);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list .item .m .tnum{font-variant-numeric:tabular-nums}
.list .item .end{flex-shrink:0;text-align:right}

/* Breadcrumb / sub-header */
.crumb{display:flex;gap:6px;align-items:center;font-size:12.5px;
  color:var(--muted);margin:-6px 0 14px;flex-wrap:wrap}
.crumb a{color:var(--gold);text-decoration:none}
.crumb a:hover{text-decoration:underline}
.crumb .sep{color:var(--faint)}

/* Empty state */
.empty{text-align:center;padding:38px 20px;color:var(--muted)}
.empty svg{width:44px;height:44px;stroke:currentColor;fill:none;stroke-width:1.4;
  opacity:.45;margin-bottom:8px}
.empty .t{font-family:var(--display);font-size:16px;color:var(--ink-dim);margin-bottom:6px}
.empty .s{font-size:13.5px;line-height:1.4}

/* FAB (floating action button) */
.fab{position:fixed;right:calc(20px + env(safe-area-inset-right,0px));
  bottom:calc(24px + env(safe-area-inset-bottom,0px));z-index:100;
  display:inline-flex;align-items:center;gap:8px;padding:14px 20px;
  background:var(--gold);color:var(--on-gold);border-radius:999px;text-decoration:none;
  font-weight:600;font-size:14px;
  box-shadow:0 16px 34px -14px rgba(124,108,255,.7),0 4px 12px -4px rgba(0,0,0,.3)}
.fab:active{transform:scale(.96)}
.fab svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2.2;
  stroke-linecap:round;stroke-linejoin:round}

/* Toast / feedback ephemera */
.toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom,0px));
  transform:translateX(-50%);
  padding:11px 18px;background:var(--panel);color:var(--ink);border:1px solid var(--line-strong);
  border-radius:999px;font-size:13.5px;box-shadow:var(--shadow);z-index:200;
  opacity:0;pointer-events:none;transition:opacity .2s}
.toast.show{opacity:1}
.toast.ok{border-color:var(--emerald)}
.toast.err{border-color:var(--danger);color:var(--danger)}

/* CTA sulla dashboard fatture */
.cta-list{display:flex;flex-direction:column;gap:10px;margin-top:6px}
.cta-list a{display:flex;align-items:center;gap:12px;padding:14px 16px;
  background:var(--card-grad);border:1px solid var(--line);border-radius:var(--r-sm);
  text-decoration:none;color:var(--ink);transition:.15s;min-height:56px;
  box-shadow:var(--shadow-tile)}
.cta-list a:active{transform:scale(.985)}
@media (hover:hover){.cta-list a:hover{border-color:var(--gold)}}
.cta-list a .ico{width:36px;height:36px;border-radius:10px;background:rgba(124,108,255,.12);
  color:var(--gold);display:grid;place-items:center;flex-shrink:0}
html[data-theme="light"] .cta-list a .ico{background:rgba(91,73,209,.1)}
.cta-list a .ico svg{width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
.cta-list a .lbl{flex:1;font-weight:500;font-size:14.5px}
.cta-list a .cnt{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.cta-list a .arw{color:var(--faint)}
.cta-list a .arw svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:2}

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


# ---------------------------------------------------------------------
# PIN gate (modal riusabile)
# ---------------------------------------------------------------------
# Snippet HTML+CSS+JS iniettato prima di </body> in tutte le pagine
# della hub (launchpad + sub-app). All'avvio chiama /api/status; se
# needs_pin && !unlocked, mostra il modal. Intercetta anche le fetch
# API che rispondono 401 (sessione scaduta) e riapre il modal.
# Il timesheet ha la sua UI di unlock propria: NON iniettiamo qui
# dentro il PAGE, ma solo nelle pagine che passano per render_page /
# render_launchpad.
_PIN_GATE = r"""
<style>
.pin-ov{position:fixed;inset:0;z-index:9999;background:rgba(11,12,16,.86);
  backdrop-filter:blur(8px);display:none;align-items:center;justify-content:center;
  padding:20px}
.pin-ov.show{display:flex}
html[data-theme="light"] .pin-ov{background:rgba(238,240,245,.9)}
.pin-card{width:100%;max-width:360px;background:var(--card-grad);
  border:1px solid var(--line-strong);border-radius:20px;padding:26px 22px;
  box-shadow:var(--shadow);text-align:center}
.pin-card .lock{width:52px;height:52px;border-radius:16px;background:rgba(124,108,255,.15);
  color:var(--gold);display:grid;place-items:center;margin:0 auto 14px}
html[data-theme="light"] .pin-card .lock{background:rgba(91,73,209,.13)}
.pin-card .lock svg{width:26px;height:26px;stroke:currentColor;fill:none;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
.pin-card h3{font-family:var(--display);font-weight:500;font-size:20px;
  margin:0 0 4px;letter-spacing:-.01em}
.pin-card p{color:var(--muted);font-size:13.5px;margin:0 0 18px}
.pin-input{width:100%;padding:14px 16px;border-radius:14px;
  background:var(--input-bg);border:1px solid var(--line-strong);
  color:var(--ink);font-family:'Space Grotesk',sans-serif;font-size:20px;
  letter-spacing:.4em;text-align:center;font-variant-numeric:tabular-nums;
  min-height:52px}
.pin-input:focus{outline:none;border-color:var(--gold)}
.pin-err{color:var(--danger);font-size:12.5px;margin-top:8px;min-height:16px}
.pin-actions{margin-top:14px}
.pin-actions .btn{width:100%}
.pin-bio{display:none;align-items:center;justify-content:center;gap:8px;
  width:100%;margin-top:10px;padding:12px 16px;border-radius:14px;
  background:transparent;border:1px solid var(--line-strong);color:var(--ink-dim);
  font-family:Inter,sans-serif;font-size:14px;font-weight:500}
.pin-bio.show{display:flex}
.pin-bio svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
</style>

<div class="pin-ov" id="pinOverlay" role="dialog" aria-modal="true" aria-label="Sblocco PIN">
  <div class="pin-card">
    <div class="lock">
      <svg viewBox="0 0 24 24">
        <rect x="4" y="10.5" width="16" height="10.5" rx="2.5"/>
        <path d="M7.5 10.5V7a4.5 4.5 0 0 1 9 0v3.5"/>
      </svg>
    </div>
    <h3>Accesso protetto</h3>
    <p>Inserisci il PIN per continuare</p>
    <input class="pin-input" id="pinInput" type="password"
           inputmode="numeric" pattern="[0-9]*" autocomplete="off"
           enterkeyhint="done" maxlength="12" placeholder="••••">
    <div class="pin-err" id="pinErr">&nbsp;</div>
    <div class="pin-actions">
      <button class="btn" id="pinSubmit" type="button">Sblocca</button>
      <button class="pin-bio" id="pinBioBtn" type="button">
        <svg viewBox="0 0 24 24">
          <path d="M12 11c0 2.5-.3 4.8-1.2 6.8M8.5 20.5A13.5 13.5 0 0 0 9.8 9.5M12 3.5a8.5 8.5 0 0 1 8.5 8.5c0 1.7-.2 3.3-.6 4.8M6.4 6.4A8.5 8.5 0 0 1 12 3.5M4.3 15.5c.4-1.3.7-2.7.7-4a7 7 0 0 1 .4-2.3M15.5 20.2c.5-1.2 1-2.7 1.3-4.2M12 7a5 5 0 0 1 5 5c0 1.2-.1 2.3-.3 3.3"/>
        </svg>
        Sblocca con impronta
      </button>
    </div>
  </div>
</div>

<script>
// Helper condivisi base64url <-> ArrayBuffer per WebAuthn (usati anche
// dal banner di registrazione nella launchpad).
window.b2fBase64urlToBuffer = function(b64url) {
  const pad = '='.repeat((4 - b64url.length % 4) % 4);
  const b64 = (b64url + pad).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const buf = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
  return buf.buffer;
};
window.b2fBufferToBase64url = function(buf) {
  const bytes = new Uint8Array(buf);
  let str = '';
  for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

(function() {
  const overlay = document.getElementById('pinOverlay');
  const input   = document.getElementById('pinInput');
  const errBox  = document.getElementById('pinErr');
  const button  = document.getElementById('pinSubmit');
  const bioBtn  = document.getElementById('pinBioBtn');

  function show() {
    overlay.classList.add('show');
    setTimeout(() => input.focus(), 50);
  }
  function hide() {
    overlay.classList.remove('show');
    input.value = ''; errBox.textContent = '\u00a0';
  }
  function setErr(m) { errBox.textContent = m || '\u00a0'; }

  function unlocked() {
    hide();
    if (window.__pinPending) {
      window.__pinPending();
      window.__pinPending = null;
    } else {
      location.reload();
    }
  }

  async function tryShowBioButton() {
    try {
      if (!window.PublicKeyCredential
          || !window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) return;
      const [st, avail] = await Promise.all([
        fetch('/api/webauthn/status', {credentials: 'same-origin'}).then(r => r.ok ? r.json() : null),
        PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(),
      ]);
      if (st && st.credentials_count > 0 && avail) bioBtn.classList.add('show');
    } catch (e) { /* niente bottone bio, resta solo il PIN */ }
  }

  async function bioUnlock() {
    bioBtn.disabled = true; setErr('\u00a0');
    try {
      const beginRes = await fetch('/api/webauthn/auth/begin', {
        method: 'POST', credentials: 'same-origin',
      });
      if (!beginRes.ok) throw new Error('begin failed');
      const options = await beginRes.json();
      options.challenge = b2fBase64urlToBuffer(options.challenge);
      if (options.allowCredentials) {
        options.allowCredentials = options.allowCredentials.map(c => ({
          ...c, id: b2fBase64urlToBuffer(c.id),
        }));
      }
      const cred = await navigator.credentials.get({publicKey: options});
      const payload = {
        id: cred.id,
        rawId: b2fBufferToBase64url(cred.rawId),
        type: cred.type,
        response: {
          clientDataJSON: b2fBufferToBase64url(cred.response.clientDataJSON),
          authenticatorData: b2fBufferToBase64url(cred.response.authenticatorData),
          signature: b2fBufferToBase64url(cred.response.signature),
          userHandle: cred.response.userHandle ? b2fBufferToBase64url(cred.response.userHandle) : null,
        },
      };
      const completeRes = await fetch('/api/webauthn/auth/complete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({credential: payload}),
      });
      if (completeRes.ok) {
        unlocked();
      } else {
        setErr('Sblocco con impronta non riuscito, usa il PIN');
      }
    } catch (e) {
      setErr('Sblocco con impronta annullato');
    } finally {
      bioBtn.disabled = false;
    }
  }

  bioBtn.addEventListener('click', bioUnlock);

  async function submitPin() {
    const pin = input.value.trim();
    if (!pin) { setErr('Inserisci il PIN'); return; }
    button.disabled = true; setErr('\u00a0');
    try {
      const r = await fetch('/api/unlock', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({pin}),
      });
      if (r.ok) {
        unlocked();
      } else {
        setErr('PIN errato');
        input.select();
      }
    } catch (e) {
      setErr('Errore di rete');
    } finally {
      button.disabled = false;
    }
  }

  button.addEventListener('click', submitPin);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); submitPin(); }
  });

  // Intercetta globalmente 401 sulle fetch API → mostra modal
  const _fetch = window.fetch;
  window.fetch = async function(...args) {
    const res = await _fetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    // Solo API interne, non chiamate esterne (fonts, jsPDF cdn, ecc.)
    if (res.status === 401 && (url.startsWith('/api/') || url.startsWith('/fatture/api/') || url.startsWith('/spese/api/'))) {
      show();
    }
    return res;
  };

  // Check iniziale: se serve PIN e non sono loggato → mostra subito
  fetch('/api/status', {credentials: 'same-origin'})
    .then(r => r.ok ? r.json() : null)
    .then(s => {
      if (s && s.needs_pin && !s.unlocked) { show(); tryShowBioButton(); }
    })
    .catch(() => {});
})();
</script>
"""


def _inject_pin_gate(html: str) -> str:
    """Inserisce lo snippet PIN gate subito prima di </body>."""
    if "</body>" in html:
        return html.replace("</body>", _PIN_GATE + "\n</body>", 1)
    return html + _PIN_GATE


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


def render_page(section: str, eyebrow: str, title_html: str, content: str,
                breadcrumb: list[tuple[str, str]] | None = None,
                fab: tuple[str, str] | None = None) -> str:
    """
    Pagina di sotto-app (Ore, Fatture, Spese).
    Header: logo B2F cliccabile (back to /) + titolo + toggle tema.

    Args:
      section    : chiave sezione (per titolo pagina)
      eyebrow    : maiuscoletto sopra il titolo
      title_html : H1 con <em>...</em> per l'accento
      content    : HTML del corpo
      breadcrumb : lista [(label, href), ...] mostrata sopra il titolo
      fab        : ("Nuova cosa", "/path/nuovo") aggiunge un FAB in basso a destra
    """
    title = f"{eyebrow} — B2F"
    head = _head(title)

    crumb_html = ""
    if breadcrumb:
        parts = []
        for i, (label, href) in enumerate(breadcrumb):
            if href:
                parts.append(f'<a href="{href}">{label}</a>')
            else:
                parts.append(f'<span>{label}</span>')
            if i < len(breadcrumb) - 1:
                parts.append('<span class="sep">›</span>')
        crumb_html = f'<div class="crumb">{"".join(parts)}</div>'

    fab_html = ""
    if fab:
        lbl, href = fab
        fab_html = f'''<a class="fab" href="{href}">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>{lbl}
        </a>'''

    html = f"""{head}
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
    {crumb_html}
    {content}
  </div>
  {fab_html}
</body>
</html>"""
    return _inject_pin_gate(html)


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

    html = f"""{head}
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

    <div class="notice bio" id="bioBanner">
      <span>Sblocco veloce disponibile</span>
      <span style="display:flex;gap:14px;flex-shrink:0">
        <button type="button" id="bioBannerDecline" style="color:var(--muted)">Non ora</button>
        <button type="button" id="bioBannerBtn">Attiva</button>
      </span>
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

<script>
// Banner "sblocco veloce": proposto solo dopo sblocco riuscito, se il device
// supporta un platform authenticator e non ci sono ancora credenziali salvate.
(async () => {{
  const banner  = document.getElementById('bioBanner');
  const btnGo   = document.getElementById('bioBannerBtn');
  const btnSkip = document.getElementById('bioBannerDecline');
  if (!banner) return;

  try {{
    if (localStorage.getItem('b2f-biometric-declined')) return;
    if (!window.PublicKeyCredential
        || !window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) return;

    const status = await fetch('/api/status', {{credentials: 'same-origin'}})
      .then(r => r.ok ? r.json() : null);
    if (!status || (status.needs_pin && !status.unlocked)) return;

    const [wa, avail] = await Promise.all([
      fetch('/api/webauthn/status', {{credentials: 'same-origin'}}).then(r => r.ok ? r.json() : null),
      PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(),
    ]);
    if (!wa || wa.credentials_count > 0 || !avail) return;

    banner.classList.add('show');
  }} catch (e) {{ /* niente banner, non è un problema */ }}

  btnSkip.addEventListener('click', () => {{
    localStorage.setItem('b2f-biometric-declined', '1');
    banner.classList.remove('show');
  }});

  btnGo.addEventListener('click', async () => {{
    btnGo.disabled = true;
    try {{
      const beginRes = await fetch('/api/webauthn/register/begin', {{
        method: 'POST', credentials: 'same-origin',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{device_name: navigator.userAgentData?.platform || navigator.platform || 'Telefono'}}),
      }});
      if (!beginRes.ok) throw new Error('begin failed');
      const options = await beginRes.json();
      options.challenge = b2fBase64urlToBuffer(options.challenge);
      options.user.id = b2fBase64urlToBuffer(options.user.id);
      if (options.excludeCredentials) {{
        options.excludeCredentials = options.excludeCredentials.map(c => ({{
          ...c, id: b2fBase64urlToBuffer(c.id),
        }}));
      }}
      const cred = await navigator.credentials.create({{publicKey: options}});
      const payload = {{
        id: cred.id,
        rawId: b2fBufferToBase64url(cred.rawId),
        type: cred.type,
        response: {{
          clientDataJSON: b2fBufferToBase64url(cred.response.clientDataJSON),
          attestationObject: b2fBufferToBase64url(cred.response.attestationObject),
          transports: cred.response.getTransports ? cred.response.getTransports() : [],
        }},
      }};
      const completeRes = await fetch('/api/webauthn/register/complete', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        credentials: 'same-origin',
        body: JSON.stringify({{credential: payload}}),
      }});
      if (!completeRes.ok) throw new Error('complete failed');
      banner.querySelector('span').textContent = 'Impronta salvata';
      setTimeout(() => banner.classList.remove('show'), 1800);
    }} catch (e) {{
      banner.querySelector('span').textContent = 'Configurazione non riuscita, riprova più tardi';
    }} finally {{
      btnGo.disabled = false;
    }}
  }});
}})();
</script>
</body>
</html>"""
    return _inject_pin_gate(html)
