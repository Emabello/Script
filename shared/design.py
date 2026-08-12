"""
shared/design.py — Design system B2F.

Un unico foglio di stile condiviso da tutte le aree dell'app (launchpad,
Ore, Fatture, Spese). Qui dentro non c'e' markup di pagina: solo token,
reset, layout shell e componenti. Il markup della shell sta in
shared/theme.py.

PRINCIPI
--------
1. Superfici piatte. Niente gradienti decorativi ne' ombre profonde: la
   gerarchia nasce da spaziatura, bordi e dimensione del testo.
2. Il colore significa. L'accento e' riservato a cio' che e' interattivo
   e al numero-chiave della schermata; verde/rosso/ambra restano per
   positivo/negativo/scadenza. Un colore che non significa nulla e'
   colore sprecato.
3. Mobile-first ma non mobile-only. Sotto i 1024px: colonna singola +
   tab bar in basso. Sopra: sidebar persistente + griglia che usa la
   larghezza davvero.
4. Personalizzabile. `data-theme` (dark/light) e `data-accent`
   (indigo/blue/violet/graphite) sull'elemento <html>, persistiti in
   localStorage.

TIPOGRAFIA
----------
Inter per l'interfaccia (cifre tabulari eccellenti), Instrument Serif
per i titoli e per il corsivo d'accento nei titoli ("Le mie *fatture*").
"""

# I caratteri sono ospitati dall'app (static/fonts) invece che presi da
# Google Fonts: risparmia due connessioni esterne al primo caricamento, va
# in cache col service worker (quindi funziona offline) e non manda l'IP
# dell'utente a un terzo. Solo subset "latin": copre U+0000-00FF, cioe'
# tutte le accentate italiane e le umlaut. In tutto 89 KB.
FONT_FILES = (
    "/static/fonts/inter-normal.woff2",
    "/static/fonts/instrument-serif-normal.woff2",
)

_UNICODE_RANGE = "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+2000-206F, U+2074, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215"

_FONT_FACES = f"""
@font-face{{
  font-family:'Inter';font-style:normal;font-weight:100 900;font-display:swap;
  src:url('/static/fonts/inter-normal.woff2') format('woff2');
  unicode-range:{_UNICODE_RANGE};
}}
@font-face{{
  font-family:'Instrument Serif';font-style:normal;font-weight:400;font-display:swap;
  src:url('/static/fonts/instrument-serif-normal.woff2') format('woff2');
  unicode-range:{_UNICODE_RANGE};
}}
@font-face{{
  font-family:'Instrument Serif';font-style:italic;font-weight:400;font-display:swap;
  src:url('/static/fonts/instrument-serif-italic.woff2') format('woff2');
  unicode-range:{_UNICODE_RANGE};
}}
"""

# Accenti disponibili nel selettore: (chiave, etichetta)
ACCENTI = (
    ("indigo",   "Indaco"),
    ("blue",     "Blu"),
    ("violet",   "Viola"),
    ("graphite", "Grafite"),
)


CSS = _FONT_FACES + r"""
/* =====================================================================
   1. TOKEN
   ===================================================================== */

:root{
  /* Fa rendere ai controlli nativi (checkbox, frecce delle select, date
     picker) la variante scura. Senza, in tema scuro le checkbox restano
     bianche e stonano. */
  color-scheme:dark;

  /* --- Neutri, tema scuro (default) --------------------------------- */
  --bg:#0c0d10;
  --surface:#131519;
  --surface-2:#181b20;
  --surface-3:#1f2329;
  --line:rgba(255,255,255,.075);
  --line-strong:rgba(255,255,255,.14);

  --ink:#f1f2f5;      /* testo primario   */
  --ink-2:#b7bac2;    /* testo secondario */
  --ink-3:#868a94;    /* etichette        */
  --ink-4:#5f636d;    /* decorativo       */

  /* --- Semantici (NON usare come accento) --------------------------- */
  --pos:#35bf8e;      --pos-soft:rgba(53,191,142,.14);
  --neg:#f2637b;      --neg-soft:rgba(242,99,123,.14);
  --warn:#e2a54c;     --warn-soft:rgba(226,165,76,.14);

  /* --- Spaziatura (scala 4px) --------------------------------------- */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px;
  --sp-6:24px; --sp-7:32px; --sp-8:40px; --sp-9:56px;

  /* --- Raggi --------------------------------------------------------- */
  --r-xs:8px; --r-sm:12px; --r-md:16px; --r-lg:20px; --r-full:999px;

  /* --- Elevazione: tre livelli, tutti leggeri ------------------------ */
  --e1:0 1px 2px rgba(0,0,0,.24);
  --e2:0 4px 16px -8px rgba(0,0,0,.5);
  --e3:0 20px 48px -24px rgba(0,0,0,.65);

  /* --- Tipografia ---------------------------------------------------- */
  --sans:Inter,system-ui,-apple-system,sans-serif;
  --display:'Instrument Serif',Georgia,serif;

  /* --- Layout -------------------------------------------------------- */
  --rail-w:248px;
  --content-max:640px;      /* sotto i 1024px */
  --content-max-lg:1140px;  /* sopra          */
  --tabbar-h:60px;

  --dur:.18s;
  --ease:cubic-bezier(.32,.72,0,1);
}

html[data-theme="light"]{
  color-scheme:light;
  --bg:#f6f7f9;
  --surface:#ffffff;
  --surface-2:#ffffff;
  --surface-3:#eef0f3;
  --line:rgba(12,14,20,.09);
  --line-strong:rgba(12,14,20,.16);

  --ink:#15171c;
  --ink-2:#474b55;
  --ink-3:#6d717c;
  --ink-4:#8a8f9b;

  --pos:#0a7954;      --pos-soft:rgba(10,121,84,.12);
  --neg:#c82743;      --neg-soft:rgba(200,39,67,.12);
  --warn:#906111;     --warn-soft:rgba(144,97,17,.12);

  --e1:0 1px 2px rgba(16,20,30,.06);
  --e2:0 4px 14px -8px rgba(16,20,30,.18);
  --e3:0 20px 44px -26px rgba(16,20,30,.26);
}

/* --- Accenti ---------------------------------------------------------
   Un solo colore non puo' fare tutto: come grafica gli basta 3:1, come
   testo piccolo gliene servono 4.5. Da qui tre varianti per accento:

     --accent       icone, bordi, barre, numeri grandi     (>= 3:1)
     --accent-fill  superfici piene: bottoni, FAB          (bianco >= 4.5:1)
     --accent-text  testo piccolo: chip, link              (>= 4.5:1, anche
                    steso sul proprio fondo tenue --accent-soft)

   Piu' --accent-hi (hover), --accent-soft (tinta), --on-accent.
   Nessuno di questi e' verde o rosso: quei due restano semantici.      */

:root,
html[data-accent="indigo"]{
  --accent:#6f5cf0; --accent-hi:#8272ff; --accent-soft:rgba(111,92,240,.15);
  --accent-fill:#6f5cf0; --accent-fill-hi:#8272ff; --accent-text:#8b7cf3;
  --on-accent:#ffffff;
}
html[data-theme="light"][data-accent="indigo"],
html[data-theme="light"]{
  --accent:#5343cf; --accent-hi:#4535b8; --accent-soft:rgba(83,67,207,.11);
  --accent-fill:#5343cf; --accent-fill-hi:#4535b8; --accent-text:#5343cf;
  --on-accent:#ffffff;
}

html[data-accent="blue"]{
  --accent:#3b8ef0; --accent-hi:#5aa2f5; --accent-soft:rgba(59,142,240,.15);
  --accent-fill:#1273e6; --accent-fill-hi:#3b8ef0; --accent-text:#3b8ef0;
  --on-accent:#ffffff;
}
html[data-theme="light"][data-accent="blue"]{
  --accent:#1f6fd0; --accent-hi:#175bb0; --accent-soft:rgba(31,111,208,.11);
  --accent-fill:#1f6fd0; --accent-fill-hi:#175bb0; --accent-text:#1e6bc9;
}

html[data-accent="violet"]{
  --accent:#a06bf0; --accent-hi:#b485f7; --accent-soft:rgba(160,107,240,.15);
  --accent-fill:#9052ed; --accent-fill-hi:#a06bf0; --accent-text:#a572f1;
  --on-accent:#ffffff;
}
html[data-theme="light"][data-accent="violet"]{
  --accent:#7c45c8; --accent-hi:#68389f; --accent-soft:rgba(124,69,200,.11);
  --accent-fill:#7c45c8; --accent-fill-hi:#68389f; --accent-text:#7c45c8;
}

html[data-accent="graphite"]{
  --accent:#d6d9e0; --accent-hi:#eceef2; --accent-soft:rgba(214,217,224,.12);
  --accent-fill:#d6d9e0; --accent-fill-hi:#eceef2; --accent-text:#d6d9e0;
  --on-accent:#14161b;
}
html[data-theme="light"][data-accent="graphite"]{
  --accent:#2b2f38; --accent-hi:#151820; --accent-soft:rgba(43,47,56,.09);
  --accent-fill:#2b2f38; --accent-fill-hi:#151820; --accent-text:#2b2f38;
  --on-accent:#ffffff;
}


/* =====================================================================
   2. RESET E BASE
   ===================================================================== */

*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--bg);
  color:var(--ink);
  font-family:var(--sans);
  font-size:15px;
  line-height:1.5;
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  -webkit-tap-highlight-color:transparent;
  min-height:100dvh;
  transition:background-color var(--dur),color var(--dur);
}
a{color:inherit;text-decoration:none}
button{font:inherit;color:inherit;background:none;border:none;padding:0;cursor:pointer}
input,select,textarea{font:inherit;color:inherit}
svg{display:block}
h1,h2,h3,h4,p{margin:0}
ul,ol{margin:0;padding:0;list-style:none}

/* Focus visibile e coerente ovunque: requisito di accessibilita', non
   un dettaglio. Solo da tastiera, per non disturbare il tocco. */
:focus{outline:none}
:focus-visible{
  outline:2px solid var(--accent);
  outline-offset:2px;
  border-radius:var(--r-xs);
}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{
    animation-duration:.01ms !important;animation-iteration-count:1 !important;
    transition-duration:.01ms !important;scroll-behavior:auto !important;
  }
}


/* =====================================================================
   3. TIPOGRAFIA
   ===================================================================== */

.display{
  font-family:var(--display);font-weight:400;
  font-size:clamp(30px,7vw,42px);line-height:1.08;letter-spacing:-.015em;
}
.h1{
  font-family:var(--display);font-weight:400;
  font-size:clamp(23px,5vw,30px);line-height:1.14;letter-spacing:-.01em;
}
.h2{font-size:17px;font-weight:600;line-height:1.3;letter-spacing:-.01em}
.h3{font-size:15px;font-weight:600;line-height:1.35}

/* Il corsivo d'accento nei titoli: "Le mie <em>fatture</em>" */
.display em,.h1 em{font-style:italic;color:var(--accent)}

.eyebrow{
  font-size:11px;font-weight:500;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-3);
}
.muted{color:var(--ink-3)}
.small{font-size:13px}
.micro{font-size:11.5px}

/* Cifre: sempre tabulari, sempre allineate in colonna. */
.tnum{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}

.pos{color:var(--pos)}
.neg{color:var(--neg)}
.warn{color:var(--warn)}
/* Utility per testo: usa la variante leggibile, non quella grafica. */
.accent{color:var(--accent-text)}


/* =====================================================================
   4. SHELL — sotto 1024px: colonna + tab bar. Sopra: sidebar + griglia.
   ===================================================================== */

.app{display:flex;align-items:flex-start;min-height:100dvh}

/* --- Sidebar (solo desktop) ------------------------------------------ */
.rail{display:none}

@media (min-width:1024px){
  .rail{
    display:flex;flex-direction:column;gap:var(--sp-6);
    width:var(--rail-w);flex:0 0 var(--rail-w);
    position:sticky;top:0;height:100dvh;
    padding:var(--sp-6) var(--sp-4);
    border-right:1px solid var(--line);
    background:var(--surface);
  }
}

.rail-brand{display:flex;align-items:center;gap:var(--sp-3);padding:0 var(--sp-2)}
.brand-mark{
  width:38px;height:38px;flex:none;border-radius:11px;
  display:grid;place-items:center;
  background:var(--accent-soft);color:var(--accent);
  font-family:var(--display);font-size:14px;letter-spacing:.02em;
}
.brand-name{display:block;font-family:var(--display);font-size:20px;line-height:1.1}
.brand-sub{display:block;font-size:11.5px;color:var(--ink-3);margin-top:2px}

.rail-nav{display:flex;flex-direction:column;gap:2px;flex:1}
.rail-link{
  display:flex;align-items:center;gap:var(--sp-3);
  padding:10px var(--sp-3);border-radius:var(--r-sm);
  color:var(--ink-2);font-size:14.5px;font-weight:500;
  transition:background-color var(--dur),color var(--dur);
}
.rail-link svg{width:19px;height:19px;flex:none;
  stroke:currentColor;fill:none;stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round}
.rail-link:hover{background:var(--surface-3);color:var(--ink)}
.rail-link.is-active{background:var(--accent-soft);color:var(--accent-text)}

.rail-foot{display:flex;flex-direction:column;gap:var(--sp-3);
  padding-top:var(--sp-4);border-top:1px solid var(--line)}

/* --- Colonna principale ---------------------------------------------- */
.main{flex:1;min-width:0;max-width:100%;display:flex;flex-direction:column}

.topbar{
  display:flex;align-items:center;gap:var(--sp-3);
  padding:calc(var(--sp-4) + env(safe-area-inset-top,0px))
          calc(var(--sp-4) + env(safe-area-inset-right,0px))
          var(--sp-3)
          calc(var(--sp-4) + env(safe-area-inset-left,0px));
  max-width:var(--content-max);margin:0 auto;width:100%;
}
.topbar-title{flex:1;min-width:0}
.topbar-title .eyebrow{white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.topbar-title .h1{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.topbar-actions{display:flex;align-items:center;gap:var(--sp-2);flex:none}

.content{
  flex:1;width:100%;max-width:var(--content-max);margin:0 auto;
  padding:0 calc(var(--sp-4) + env(safe-area-inset-right,0px))
          calc(var(--tabbar-h) + var(--sp-8) + env(safe-area-inset-bottom,0px))
          calc(var(--sp-4) + env(safe-area-inset-left,0px));
}

@media (min-width:1024px){
  .topbar,.content{max-width:var(--content-max-lg)}
  .topbar{padding-top:var(--sp-7);padding-left:var(--sp-7);padding-right:var(--sp-7)}
  .content{padding-left:var(--sp-7);padding-right:var(--sp-7);padding-bottom:var(--sp-9)}
  /* Pagine pensate per una colonna sola (il timesheet): stirarle su 1140px
     non aggiunge informazione, allunga solo le righe. */
  .topbar.single,.content.single{max-width:760px;margin-left:0}
}

/* --- Tab bar (solo mobile/tablet) ------------------------------------ */
.tabbar{
  position:fixed;left:0;right:0;bottom:0;z-index:60;
  display:flex;
  padding:var(--sp-1) var(--sp-2) calc(var(--sp-1) + env(safe-area-inset-bottom,0px));
  background:color-mix(in srgb,var(--surface) 88%,transparent);
  backdrop-filter:saturate(180%) blur(18px);
  -webkit-backdrop-filter:saturate(180%) blur(18px);
  border-top:1px solid var(--line);
}
.tab{
  flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;min-height:52px;padding:6px 4px;border-radius:var(--r-sm);
  color:var(--ink-3);font-size:10.5px;font-weight:500;letter-spacing:.01em;
  transition:color var(--dur);
}
.tab svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round}
.tab.is-active{color:var(--accent-text)}
.tab:active{transform:scale(.94)}

@media (min-width:1024px){
  .tabbar{display:none}
}

/* --- Breadcrumb ------------------------------------------------------- */
.crumb{
  display:flex;flex-wrap:wrap;align-items:center;gap:6px;
  max-width:var(--content-max);margin:0 auto;width:100%;
  padding:0 calc(var(--sp-4) + env(safe-area-inset-left,0px)) var(--sp-3);
  font-size:12.5px;color:var(--ink-3);
}
.crumb a{color:var(--ink-2)}
.crumb a:hover{color:var(--accent-text)}
.crumb .sep{color:var(--ink-4)}
@media (min-width:1024px){
  .crumb{max-width:var(--content-max-lg);padding-left:var(--sp-7);padding-right:var(--sp-7)}
}


/* =====================================================================
   5. GRIGLIA
   ===================================================================== */

.stack{display:flex;flex-direction:column;gap:var(--sp-3);min-width:0}
.stack>*{min-width:0}
.stack.gap-lg{gap:var(--sp-5)}

.grid{display:grid;gap:var(--sp-3);min-width:0}
.grid>*{min-width:0}
/* Tessere KPI: si dispongono da sole, nessun breakpoint da mantenere. */
.grid.kpi{grid-template-columns:repeat(auto-fit,minmax(132px,1fr))}
/* Con tre tessere su schermo stretto, due righe da 2+1 lasciano l'ultima
   spaiata. Con .lead la prima prende tutta la riga e le altre due si
   affiancano sotto: la gerarchia diventa anche visiva. */
@media (max-width:719px){
  .grid.kpi.lead>:first-child{grid-column:1/-1}
}
.grid.cols-2{grid-template-columns:minmax(0,1fr)}
.grid.cols-3{grid-template-columns:minmax(0,1fr)}
@media (min-width:720px){
  .grid.cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}
  .grid.cols-3{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (min-width:1024px){
  .grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
}
/* Colonna larga + colonna stretta, tipica delle dashboard desktop */
.grid.split{grid-template-columns:minmax(0,1fr)}
@media (min-width:1024px){
  .grid.split{grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:var(--sp-4)}
}


/* =====================================================================
   6. COMPONENTI
   ===================================================================== */

/* --- Card ------------------------------------------------------------- */
.card{
  min-width:0;
  background:var(--surface);
  border:1px solid var(--line);
  border-radius:var(--r-md);
  padding:var(--sp-4);
  box-shadow:var(--e1);
}
.card-head{display:flex;align-items:center;justify-content:space-between;
  gap:var(--sp-3);margin-bottom:var(--sp-3)}
.card-head .eyebrow{margin:0}
.card-link{display:block;transition:border-color var(--dur),background-color var(--dur)}
@media (hover:hover){.card-link:hover{border-color:var(--line-strong)}}
.card.flush{padding:0;overflow:hidden}
.card.quiet{background:transparent;box-shadow:none}

/* --- Statistica -------------------------------------------------------- */
.stat{display:flex;flex-direction:column;gap:2px}
.stat .val{
  font-family:var(--display);font-weight:400;
  font-size:clamp(26px,5.5vw,34px);line-height:1.05;letter-spacing:-.015em;
  font-variant-numeric:tabular-nums;
}
.stat .lbl{font-size:12px;color:var(--ink-3)}
.stat .hint{font-size:12px;color:var(--ink-3);margin-top:2px}
.stat.sm .val{font-size:22px}

/* --- Righe tabellari ----------------------------------------------------
   Flex e non grid: cosi' la riga funziona sia con due figli (etichetta +
   valore) sia con tre (data + testo + valore) senza varianti.          */
.rows{display:flex;flex-direction:column;min-width:0}
.row{
  display:flex;align-items:center;gap:var(--sp-3);
  padding:11px 0;border-bottom:1px solid var(--line);
}
.row:last-child{border-bottom:0}
.row .k{flex:none;font-size:12.5px;color:var(--ink-3);white-space:nowrap;
  font-variant-numeric:tabular-nums}
.row .t{display:block;flex:1;min-width:0;font-size:14px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .t .sub{display:block;font-size:12px;color:var(--ink-3);
  overflow:hidden;text-overflow:ellipsis}
.row .v{flex:none;text-align:right;font-size:14px;font-weight:500;
  font-variant-numeric:tabular-nums;white-space:nowrap}
/* Righe esplicative: il testo puo' andare a capo, niente ellissi. */
.rows.detail .row{align-items:flex-start}
.rows.detail .row .t{white-space:normal;overflow:visible}
.rows.detail .row .t .sub{white-space:normal;line-height:1.4;margin-top:2px}

/* --- Lista di elementi cliccabili ---------------------------------------- */
.list{display:flex;flex-direction:column;gap:var(--sp-2);min-width:0}
.item{
  display:flex;align-items:center;gap:var(--sp-3);
  padding:13px var(--sp-4);min-height:62px;
  background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-sm);box-shadow:var(--e1);
  transition:border-color var(--dur),background-color var(--dur),transform var(--dur);
}
.item:active{transform:scale(.99)}
@media (hover:hover){.item:hover{border-color:var(--line-strong);background:var(--surface-2)}}
.item .body{display:block;flex:1;min-width:0}
.item .body .n{display:block;font-size:14.5px;font-weight:500;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .body .m{display:block;font-size:12.5px;color:var(--ink-3);margin-top:1px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .end{flex:none;text-align:right;display:flex;flex-direction:column;
  align-items:flex-end;gap:4px}
.item .end .amt{font-size:14.5px;font-weight:500;font-variant-numeric:tabular-nums}

/* Icona quadrata a sinistra (menu, categorie) */
.ico{
  width:38px;height:38px;flex:none;border-radius:11px;display:grid;place-items:center;
  background:var(--accent-soft);color:var(--accent);
}
.ico svg{width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round}
.ico.lg{width:46px;height:46px;border-radius:13px}
.ico.lg svg{width:23px;height:23px}
.ico.neutral{background:var(--surface-3);color:var(--ink-2)}
.ico.pos{background:var(--pos-soft);color:var(--pos)}
.ico.neg{background:var(--neg-soft);color:var(--neg)}
.ico.warn{background:var(--warn-soft);color:var(--warn)}

.chev{flex:none;color:var(--ink-4)}
.chev svg{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:1.8;
  stroke-linecap:round;stroke-linejoin:round}

/* --- Bottoni -------------------------------------------------------------- */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:var(--sp-2);
  min-height:44px;padding:11px var(--sp-5);border-radius:var(--r-full);
  background:var(--accent-fill);color:var(--on-accent);
  font-size:14.5px;font-weight:600;letter-spacing:.005em;
  transition:background-color var(--dur),transform var(--dur),opacity var(--dur);
}
.btn svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.9;
  stroke-linecap:round;stroke-linejoin:round}
.btn:active{transform:scale(.98)}
@media (hover:hover){.btn:hover{background:var(--accent-fill-hi)}}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--line-strong)}
@media (hover:hover){.btn.ghost:hover{background:var(--surface-3)}}
.btn.subtle{background:var(--surface-3);color:var(--ink)}
.btn.danger{background:transparent;color:var(--neg);border:1px solid var(--neg-soft)}
@media (hover:hover){.btn.danger:hover{background:var(--neg-soft)}}
.btn.block{width:100%}
.btn[disabled],.btn.is-disabled{opacity:.45;pointer-events:none}

.actions{display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:var(--sp-4)}
.actions .btn{flex:1;min-width:130px}
.actions.col{flex-direction:column}
.actions.col .btn{width:100%}

/* Bottone icona (barra in alto) */
.icon-btn{
  width:40px;height:40px;flex:none;border-radius:var(--r-full);
  display:grid;place-items:center;color:var(--ink-2);
  border:1px solid var(--line);
  transition:border-color var(--dur),color var(--dur),background-color var(--dur);
}
.icon-btn svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
@media (hover:hover){.icon-btn:hover{color:var(--ink);background:var(--surface-3)}}
.icon-btn:active{transform:scale(.94)}

/* FAB: sopra la tab bar su mobile, in basso a destra su desktop */
.fab{
  position:fixed;z-index:70;
  right:calc(var(--sp-4) + env(safe-area-inset-right,0px));
  bottom:calc(var(--tabbar-h) + var(--sp-4) + env(safe-area-inset-bottom,0px));
  display:inline-flex;align-items:center;gap:var(--sp-2);
  min-height:52px;padding:0 var(--sp-5);border-radius:var(--r-full);
  background:var(--accent-fill);color:var(--on-accent);
  font-size:14.5px;font-weight:600;box-shadow:var(--e3),var(--e1);
}
.fab svg{width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:2.2;
  stroke-linecap:round;stroke-linejoin:round}
.fab:active{transform:scale(.97)}
@media (min-width:1024px){
  .fab{bottom:calc(var(--sp-6) + env(safe-area-inset-bottom,0px));right:var(--sp-6)}
}

/* --- Chip ------------------------------------------------------------------ */
.chip{
  display:inline-flex;align-items:center;gap:5px;
  padding:3px 10px;border-radius:var(--r-full);
  font-size:11.5px;font-weight:500;letter-spacing:.02em;
  background:var(--surface-3);color:var(--ink-2);white-space:nowrap;
}
.chip.accent{background:var(--accent-soft);color:var(--accent-text)}
.chip.pos{background:var(--pos-soft);color:var(--pos)}
.chip.neg{background:var(--neg-soft);color:var(--neg)}
.chip.warn{background:var(--warn-soft);color:var(--warn)}

/* --- Avvisi ---------------------------------------------------------------- */
.notice{
  padding:13px var(--sp-4);border-radius:var(--r-sm);
  border:1px solid var(--line);background:var(--surface);
  color:var(--ink-2);font-size:13.5px;line-height:1.5;
}
.notice.warn{border-color:var(--warn-soft);background:var(--warn-soft);color:var(--ink)}
.notice.err{border-color:var(--neg-soft);background:var(--neg-soft);color:var(--ink)}
.notice.info{border-color:var(--accent-soft);background:var(--accent-soft);color:var(--ink)}
.notice code{
  font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:12.5px;
  padding:1px 5px;border-radius:5px;background:var(--surface-3);
}
.notice-row{display:flex;align-items:center;justify-content:space-between;
  gap:var(--sp-3);flex-wrap:wrap}
.notice-row button{color:var(--accent-text);font-weight:600;white-space:nowrap}

/* --- Form -------------------------------------------------------------------- */
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:var(--sp-3)}
/* Le etichette dei campi restano in minuscolo: il maiuscoletto e' gia'
   usato dalle intestazioni di sezione (.eyebrow), e due livelli di
   maiuscolo nello stesso modulo appiattiscono la gerarchia. */
.field label{font-size:12.5px;font-weight:500;color:var(--ink-3)}
.field .hint{font-size:12px;color:var(--ink-3)}
.field input,.field select,.field textarea,.input{
  width:100%;min-height:44px;padding:11px var(--sp-3);
  background:var(--bg);color:var(--ink);
  border:1px solid var(--line-strong);border-radius:var(--r-sm);
  font-size:15px;
  transition:border-color var(--dur),box-shadow var(--dur);
}
html[data-theme="light"] .field input,
html[data-theme="light"] .field select,
html[data-theme="light"] .field textarea,
html[data-theme="light"] .input{background:var(--surface-3)}
.field input::placeholder,.field textarea::placeholder{color:var(--ink-4)}
.field input:focus,.field select:focus,.field textarea:focus,.input:focus{
  outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft);
}
.field input[disabled],.field select[disabled],.field textarea[disabled]{opacity:.55;cursor:not-allowed}
.field textarea{min-height:84px;resize:vertical;line-height:1.5}
.field.inline{flex-direction:row;align-items:center;gap:var(--sp-3)}
.field.inline label{font-size:14px;font-weight:400;color:var(--ink);margin:0}
.field.inline input[type=checkbox]{width:20px;height:20px;min-height:0;flex:none;
  accent-color:var(--accent)}

.field-group{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--sp-3)}
@media (min-width:520px){
  .field-group{grid-template-columns:repeat(2,minmax(0,1fr))}
  .field-group.c3{grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)}
}
.field-group>.field{margin-bottom:0}

/* Select compatta usata nelle toolbar di filtro */
.select-pill{
  min-height:40px;padding:8px var(--sp-4) 8px var(--sp-3);
  background:var(--surface);color:var(--ink);
  border:1px solid var(--line-strong);border-radius:var(--r-full);
  font-size:13.5px;
}
.select-pill:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft)}
.toolbar{display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-bottom:var(--sp-3)}

/* Controllo segmentato */
.segmented{
  display:inline-flex;padding:3px;gap:2px;
  background:var(--surface-3);border-radius:var(--r-full);
}
.segmented button{
  padding:7px var(--sp-4);border-radius:var(--r-full);
  font-size:13px;font-weight:500;color:var(--ink-3);
  transition:background-color var(--dur),color var(--dur);
}
.segmented button.is-active{background:var(--surface);color:var(--ink);
  box-shadow:var(--e1)}

/* --- Barra di avanzamento ------------------------------------------------------ */
.meter{height:7px;border-radius:var(--r-full);background:var(--surface-3);
  overflow:hidden}
.meter>i{display:block;height:100%;border-radius:var(--r-full);
  background:var(--accent);transition:width .5s var(--ease)}
.meter>i.pos{background:var(--pos)}
.meter>i.warn{background:var(--warn)}
.meter>i.neg{background:var(--neg)}

/* Barra a segmenti: scompone un importo in quote (es. tuo / INPS / imposta) */
.bar-split{display:flex;height:10px;border-radius:var(--r-full);overflow:hidden;
  background:var(--surface-3)}
.bar-split>span{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:var(--sp-3);margin-top:var(--sp-3)}
.legend>div{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2)}
.legend .dot{width:9px;height:9px;border-radius:3px;flex:none}

/* --- Stato vuoto ---------------------------------------------------------------- */
.empty{text-align:center;padding:var(--sp-9) var(--sp-5);color:var(--ink-3)}
.empty svg{width:40px;height:40px;margin:0 auto var(--sp-3);
  stroke:currentColor;fill:none;stroke-width:1.3;opacity:.5}
.empty .t{font-family:var(--display);font-size:19px;color:var(--ink-2);
  margin-bottom:5px}
.empty .s{font-size:13.5px;max-width:34ch;margin:0 auto}

/* --- Modal (foglio dal basso su mobile, centrato su desktop) ---------------------- */
.sheet-ov{
  position:fixed;inset:0;z-index:400;display:none;
  align-items:flex-end;justify-content:center;
  background:rgba(6,7,10,.6);
  backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
}
html[data-theme="light"] .sheet-ov{background:rgba(30,34,44,.34)}
.sheet-ov.show{display:flex}
.sheet{
  width:100%;max-width:520px;max-height:88dvh;overflow-y:auto;
  background:var(--surface);border:1px solid var(--line-strong);
  border-radius:var(--r-lg) var(--r-lg) 0 0;
  padding:var(--sp-5) var(--sp-5) calc(var(--sp-5) + env(safe-area-inset-bottom,0px));
  box-shadow:var(--e3);
}
@media (min-width:640px){
  .sheet-ov{align-items:center;padding:var(--sp-5)}
  .sheet{border-radius:var(--r-lg);padding-bottom:var(--sp-5)}
}
.sheet h3{font-family:var(--display);font-size:22px;font-weight:400;
  letter-spacing:-.01em;margin-bottom:4px}
.sheet .sheet-sub{font-size:13.5px;color:var(--ink-3);margin-bottom:var(--sp-4)}

/* --- Toast --------------------------------------------------------------------- */
.toast{
  position:fixed;left:50%;z-index:500;
  bottom:calc(var(--tabbar-h) + var(--sp-4) + env(safe-area-inset-bottom,0px));
  transform:translateX(-50%) translateY(8px);
  padding:11px var(--sp-5);border-radius:var(--r-full);
  background:var(--surface);color:var(--ink);
  border:1px solid var(--line-strong);box-shadow:var(--e3);
  font-size:13.5px;max-width:calc(100vw - 32px);
  opacity:0;pointer-events:none;
  transition:opacity var(--dur),transform var(--dur);
}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.toast.ok{border-color:var(--pos)}
.toast.err{border-color:var(--neg)}
@media (min-width:1024px){
  .toast{bottom:calc(var(--sp-6) + env(safe-area-inset-bottom,0px))}
}

/* --- Selettore accento (nelle impostazioni / sidebar) ---------------------------- */
.accent-pick{display:flex;gap:var(--sp-2);flex-wrap:wrap}
/* 44px pieni: sotto quella soglia il bersaglio non e' afferrabile col
   pollice. Il pallino colorato resta piccolo, l'area attiva no. */
.accent-pick button{
  width:44px;height:44px;border-radius:var(--r-full);
  border:2px solid transparent;
  display:grid;place-items:center;
  transition:border-color var(--dur),transform var(--dur);
}
.accent-pick button>i{display:block;width:24px;height:24px;
  border-radius:var(--r-full);pointer-events:none}
.accent-pick button.is-active{border-color:var(--ink-3)}
.accent-pick button:active{transform:scale(.9)}

/* --- Skeleton di caricamento ------------------------------------------------------ */
.skel{
  display:inline-block;height:.85em;width:7em;border-radius:5px;vertical-align:-2px;
  background:linear-gradient(90deg,var(--surface-3),var(--line-strong),var(--surface-3));
  background-size:200% 100%;animation:skel 1.3s linear infinite;
}
@keyframes skel{0%{background-position:200% 0}100%{background-position:-200% 0}}

/* --- Tabella larga: scorre da sola invece di sfondare la pagina ------------------- */
.scroll-x{overflow-x:auto;-webkit-overflow-scrolling:touch}
.table{width:100%;border-collapse:collapse;font-size:13.5px}
.table th{
  text-align:left;font-size:11px;font-weight:500;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-3);
  padding:0 var(--sp-3) var(--sp-2);white-space:nowrap;
}
.table td{padding:10px var(--sp-3);border-top:1px solid var(--line);white-space:nowrap}
.table td.num,.table th.num{text-align:right;font-variant-numeric:tabular-nums}
.table tbody tr:hover{background:var(--surface-2)}
.table tfoot td{border-top:1px solid var(--line-strong);font-weight:600}

/* --- Blocco esplicativo apribile -------------------------------------------------- */
.explain{border-top:1px solid var(--line);padding-top:var(--sp-3)}
.explain>summary{
  list-style:none;cursor:pointer;
  display:flex;align-items:center;gap:6px;
  font-size:13px;color:var(--ink-3);
  padding:2px 0;min-height:28px;
}
.explain>summary::-webkit-details-marker{display:none}
.explain>summary::after{
  content:"";width:7px;height:7px;flex:none;margin-left:2px;
  border-right:1.6px solid currentColor;border-bottom:1.6px solid currentColor;
  transform:rotate(45deg) translate(-2px,-2px);
  transition:transform var(--dur);
}
.explain[open]>summary::after{transform:rotate(-135deg) translate(-2px,-2px)}
@media (hover:hover){.explain>summary:hover{color:var(--ink-2)}}

/* --- Card accantonamento ----------------------------------------------------------- */
.acc-card .card-head{flex-direction:column;align-items:stretch;gap:var(--sp-3)}
.acc-seg{display:flex;width:100%}
.acc-seg button{flex:1;padding:7px var(--sp-2)}
@media (min-width:560px){
  .acc-card .card-head{flex-direction:row;align-items:center}
  .acc-seg{width:auto}
  .acc-seg button{flex:none;padding:7px var(--sp-4)}
}
.acc-main{display:flex;align-items:flex-end;justify-content:space-between;
  gap:var(--sp-4);flex-wrap:wrap}
.acc-netto{text-align:right}
.acc-netto .lbl{margin-bottom:1px}
.stat-hint{margin-top:var(--sp-3)}

/* --- Utility minime --------------------------------------------------------------- */
.row-between{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3)}
/* I moduli non vanno letti su 1100px di larghezza: le righe troppo lunghe
   stancano e i campi diventano bersagli sproporzionati. */
.narrow{max-width:680px}
.narrow.center{margin-left:auto;margin-right:auto}
.mt-0{margin-top:0}.mt-2{margin-top:var(--sp-2)}.mt-3{margin-top:var(--sp-3)}
.mt-4{margin-top:var(--sp-4)}.mt-5{margin-top:var(--sp-5)}
.mb-2{margin-bottom:var(--sp-2)}.mb-3{margin-bottom:var(--sp-3)}
.mb-4{margin-bottom:var(--sp-4)}
.hide-mobile{display:none}
@media (min-width:1024px){
  .hide-mobile{display:revert}
  .hide-desktop{display:none}
}
"""


# ---------------------------------------------------------------------------
# Icone — tratto 1.6, viewBox 24, senza fill. Il colore arriva da currentColor.
# ---------------------------------------------------------------------------

ICONS = {
    "home":    '<path d="M3.5 10.5 12 4l8.5 6.5V19a1.5 1.5 0 0 1-1.5 1.5h-4v-6h-6v6H5A1.5 1.5 0 0 1 3.5 19z"/>',
    "ore":     '<rect x="3.5" y="5" width="17" height="15" rx="3"/><path d="M3.5 9.5h17M8 3v3.5M16 3v3.5"/><circle cx="12" cy="14.8" r="2.8"/><path d="M12 13.4v1.5l1.1.9"/>',
    "fatture": '<path d="M6 3.5h8.5L19 8v12.5H6z"/><path d="M14 3.5V8h5"/><path d="M9 12.5h6M9 15.5h6M9 18h4"/>',
    "spese":   '<path d="M3.5 7.5A2.5 2.5 0 0 1 6 5h12a2.5 2.5 0 0 1 2.5 2.5v9A2.5 2.5 0 0 1 18 19H6a2.5 2.5 0 0 1-2.5-2.5z"/><path d="M3.5 10h17"/><circle cx="16.8" cy="15" r="1.1"/>',
    "fiscale": '<rect x="5" y="3.5" width="14" height="17" rx="2.5"/><path d="M8.5 8h7M8.5 12h7M8.5 16h4"/>',
    "clienti": '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20.5c0-3.8 3.4-6 7.5-6s7.5 2.2 7.5 6"/>',
    "plus":    '<path d="M12 5v14M5 12h14"/>',
    "chevron": '<path d="M9 5.5 15.5 12 9 18.5"/>',
    "back":    '<path d="M15 5.5 8.5 12 15 18.5"/>',
    "download":'<path d="M12 3.5v12M7.5 11 12 15.5 16.5 11M4.5 20.5h15"/>',
    "moon":    '<path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"/>',
    "sun":     '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
    # "Aspetto" usa il simbolo del contrasto e non l'ingranaggio: nel
    # timesheet l'ingranaggio e' gia' preso dalle impostazioni dell'app,
    # e due ingranaggi affiancati non dicono niente a nessuno.
    "contrast":'<circle cx="12" cy="12" r="8.6"/><path d="M12 3.4a8.6 8.6 0 0 1 0 17.2z" fill="currentColor" stroke="none"/>',
    "settings":'<circle cx="12" cy="12" r="3"/><path d="M19.4 14.5a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1h-.2a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h.1a1.6 1.6 0 0 0 1-1.5v-.2a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v.1a1.6 1.6 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
    "lock":    '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M7.8 10.5V7a4.2 4.2 0 0 1 8.4 0v3.5"/>',
    "wallet":  '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5z"/><path d="M20 10.5h-4a1.8 1.8 0 0 0 0 3.6h4"/>',
    "piggy":   '<path d="M4 12.5c0-3.6 3.4-6.5 8-6.5 1.2 0 2.4.2 3.4.6l2.6-1.6v3.2c1.1 1 1.8 2.3 2 3.8h1.5v3h-2a6.6 6.6 0 0 1-2.5 2.6V20h-3v-1.3a11 11 0 0 1-4 0V20h-3v-2A6.7 6.7 0 0 1 4 12.5z"/><circle cx="16" cy="11.5" r=".9"/>',
    "calendar":'<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 9.5h17M8 3v3.5M16 3v3.5"/>',
    "alert":   '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4M12 16.6v.1"/>',
    "check":   '<path d="M5 12.5 10 17.5 19.5 7"/>',
    "empty-doc":'<path d="M6 3.5h8.5L19 8v12.5H6z"/><path d="M14 3.5V8h5"/>',
}


def icon(name: str, cls: str = "") -> str:
    """SVG inline dell'icona richiesta. Ritorna stringa vuota se sconosciuta."""
    path = ICONS.get(name)
    if not path:
        return ""
    c = f' class="{cls}"' if cls else ""
    return (f'<svg{c} viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{path}</svg>')
