"""
shared/caricamento.py — La tenda mosaico.

IL PROBLEMA
-----------
L'app sta su Render, piano gratuito: dopo un quarto d'ora senza
richieste il container va in letargo, e la prima richiesta dopo il
letargo paga il risveglio (mezzo minuto buono). In quella finestra chi
apre l'app non vede l'app: vede la pagina d'attesa di Render — marchio
loro, log del loro deploy, un invito a costruire su Render. E' l'unica
schermata dell'app che non e' dell'app.

LA SOLUZIONE
------------
Non si puo' sostituire quella pagina dal server (quando risponde Render
il nostro processo non c'e' ancora), ma si puo' rispondere *prima* di
Render: un service worker installato nel browser intercetta le
navigazioni e, quando la risposta non arriva dall'app, serve dalla cache
la nostra pagina d'attesa.

Come fa a sapere se la risposta e' dell'app? Ogni risposta dell'app
porta l'header `X-B2F: hub` (vedi app.py). L'interstiziale di Render, un
502, una pagina d'errore del proxy: nessuno di questi ce l'ha. Il
controllo e' su un fatto nostro, non sul riconoscere l'HTML altrui.

I PEZZI
-------
1. `SERVICE_WORKER` — servito su /sw.js. Intercetta le navigazioni, tiene
   in cache /attesa e i due font.
2. `render_attesa()` — la pagina d'attesa: la tenda che si compone,
   tessera dopo tessera, mentre bussa a /ping. Quando l'app risponde,
   ricarica la pagina vera.
3. `tenda_html()` + `TENDA_CSS` + `TENDA_JS` + `TENDA_BOOT` — la stessa
   tenda dentro l'app, gia' composta, che si alza al primo paint. E' quel
   che rende il passaggio una cosa sola: la tenda che hai visto comporsi
   durante l'attesa non sparisce al cambio pagina, si alza da dentro
   l'app.

LA TENDA
--------
Un mosaico di tessere piccole — ~22px sul telefono, ~30 sul desktop:
seicento e passa sul telefono, quasi duemila sul desktop — che copre lo
schermo. Mentre si aspetta le tessere si accendono una alla volta, senza
dissolvenza, dall'alto verso il basso con il bordo frastagliato: e'
l'avanzamento, ed e' un'immagine che si carica a blocchi come su un
modem. Quando l'app c'e', il mosaico completo si alza tutto insieme —
una tenda sola.

Il tono e' retro ma con i colori e i caratteri di casa: righe di
scansione da tubo catodico, vignettatura, testi di servizio in
monospaziato maiuscolo, avanzamento a blocchi invece che a barra
continua, cursore che lampeggia. Il titolo resta nel serif dell'app e
saluta come saluta la home: la tenda e' una schermata dell'app, non un
travestimento.

IL QUADRO
---------
Il mosaico non e' una texture fissa: ogni avvio ne dipinge uno nuovo.
Cinque generatori (onde di rumore, raggi, blocchi alla Bauhaus,
intreccio di diagonali, dune d'interferenza), la scelta la fa il seme —
e con lei le tinte, il taglio, l'ordine di accensione. Guardarne due
uguali e' un caso su parecchi.

I colori non sono una lista scritta a mano: nascono dall'accento scelto
nel pannello Aspetto. Nove tinte, ottenute ruotando la tonalita'
dell'accento (vicini stretti per l'armonia, due note lontane per il
contrasto) e tenendo la luminosita' nella fascia del tema — al buio
restano scure, in chiaro chiare — piu' un disturbo per tessera, cosi'
due tessere della stessa tinta non sono mai identiche. Cambi accento e
cambia la tavolozza: il quadro resta di casa qualunque colore scegli.

TESSERE, MOLTE
--------------
Le tessere le costruisce il JS, non il server: a duemila per pagina il
markup peserebbe piu' della pagina, e la griglia dev'essere quadrata
sullo schermo che c'e' davvero, non su quello che si immagina il CSS.
Lo script sta *dentro* il body subito dopo il contenitore, quindi gira
durante il parsing: il mosaico c'e' gia' al primo paint.

Il caso e' seminato (mulberry32): dal seme escono griglia, quadro,
tinte e ordine di accensione. La pagina d'attesa, quando passa la mano
all'app, le lascia il proprio seme in sessionStorage — cosi' la tenda
che si alza e' esattamente quella che si stava guardando, non un'altra.
"""

# Numero di blocchi del metro d'avanzamento. Sono pochi apposta: un
# avanzamento a blocchi si legge a colpo d'occhio ("tre quarti"), che e'
# tutto quel che serve sapere mentre si aspetta.
N_BLOCCHI = 24


# ---------------------------------------------------------------------------
# Stile
# ---------------------------------------------------------------------------

TENDA_CSS = r"""
/* --- La tenda mosaico ------------------------------------------------
   Sta sopra tutto (il gate del PIN e' a 900) e resta spenta finche'
   <html> non ha data-tenda: cosi' il markup puo' stare in ogni pagina
   senza che si veda mai dove non serve. */
.tenda{
  position:fixed;inset:0;z-index:1200;display:none;overflow:hidden;
  background:var(--bg);
  /* Rete di sicurezza: se il JS non parte (errore, script bloccato) la
     tenda si alza lo stesso, da sola, dopo 3,5s. Una tenda che resta
     giu' e' un'app morta. */
  animation:tenda-sicurezza .8s var(--ease) 3.5s forwards;
}
html[data-tenda] .tenda{display:block}
.tenda.resta{animation:none}   /* la pagina d'attesa aspetta quanto serve */

/* --- Il mosaico ------------------------------------------------------
   Righe e colonne le mette il JS in stile inline: dipendono dallo
   schermo. Qui c'e' solo come sono fatte le tessere. */
.tenda-mosaico{
  position:absolute;inset:-2px;display:grid;gap:1px;   /* la ritocca il JS */
}
.tenda-mosaico i{
  background:var(--surface-2);opacity:.5;
  /* Niente transizione: una tessera si accende, non sfuma. E' quel che
     fa sembrare il mosaico un'immagine che arriva a blocchi. */
}
/* --c e' il colore che quella tessera ha nel quadro: lo calcola il JS
   (vedi TENDA_JS) partendo dall'accento scelto. Spenta la tessera e'
   grigia, accesa mostra il suo pezzo di quadro. */
.tenda-mosaico i.on{background:var(--c);opacity:1}
/* In chiaro le superfici dell'app sono quasi tutte bianche: una tessera
   spenta di --surface non si distinguerebbe dal fondo, e il mosaico
   sparirebbe. Qui la tessera spenta e' un velo d'inchiostro sul chiaro. */
/* `:not(.on)` non e' un vezzo: senza, questa regola (che ha un attributo
   in piu') batterebbe per specificita' quella della tessera accesa, e in
   tema chiaro il quadro resterebbe grigio a mosaico completo. */
html[data-theme="light"] .tenda-mosaico i:not(.on){
  background:rgba(21,23,28,.09);opacity:1;
}

/* --- Il vetro: righe di scansione, vignettatura, spazzata ------------
   Il tubo catodico. Tre effetti in due elementi, nessuno dei quali
   tocca le tessere: qualunque sia il numero di tessere, qui si animano
   sempre e solo due nodi. */
.tenda-vetro{
  position:absolute;inset:0;pointer-events:none;
  background:
    repeating-linear-gradient(to bottom,
      rgba(0,0,0,.20) 0 1px, rgba(0,0,0,0) 1px 3px),
    radial-gradient(120% 90% at 50% 45%,
      rgba(0,0,0,0) 45%, rgba(0,0,0,.45) 100%);
}
html[data-theme="light"] .tenda-vetro{
  background:
    repeating-linear-gradient(to bottom,
      rgba(20,24,34,.10) 0 1px, rgba(0,0,0,0) 1px 3px),
    radial-gradient(120% 90% at 50% 45%,
      rgba(0,0,0,0) 48%, rgba(20,24,34,.20) 100%);
}
.tenda-spazzata{
  position:absolute;inset:-30% -70%;pointer-events:none;opacity:.55;
  background:linear-gradient(104deg,
    rgba(0,0,0,0) 42%, var(--accent-soft) 50%, rgba(0,0,0,0) 58%);
  animation:tenda-spazzata 6s linear infinite;
}
@keyframes tenda-spazzata{
  from{transform:translateX(-42%)}
  to{transform:translateX(42%)}
}

/* --- Il cartiglio ----------------------------------------------------
   Il testo steso sul mosaico non si legge: le tessere accese gli passano
   dietro e ogni riga cambia fondo. Serve una superficie piena — una
   targa appesa al muro di tessere. Angoli quasi vivi e un anello di
   fondo attorno: e' la cornice di uno schermo, non una card. */
.tenda-centro{
  position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);
  display:flex;justify-content:center;padding:var(--sp-6);
  transition:opacity .3s var(--ease), transform .3s var(--ease);
}
/* Toccando fuori dalla targa, la targa se ne va e resta il quadro: e'
   l'unico modo di vedere il mosaico intero mentre si aspetta. Un altro
   tocco e torna. */
.tenda-centro.via{
  opacity:0;pointer-events:none;
  transform:translateY(-50%) scale(.97);
}
.tenda-cartiglio{
  display:flex;flex-direction:column;align-items:center;text-align:center;
  gap:var(--sp-3);width:100%;max-width:330px;
  padding:var(--sp-6) var(--sp-5) var(--sp-5);
  background:var(--bg);border:1px solid var(--line-strong);border-radius:6px;
  box-shadow:0 0 0 5px var(--bg), var(--e3);
}
.tenda-marchio{
  width:52px;height:52px;flex:none;border-radius:6px;display:grid;place-items:center;
  background:var(--accent-soft);color:var(--accent);
  font-family:var(--mono);font-size:14px;font-weight:600;letter-spacing:.08em;
}
.tenda-titolo{font-family:var(--display);font-weight:400;font-size:27px;
  line-height:1.15;letter-spacing:-.01em;margin:0}
.tenda-fase{
  font-family:var(--mono);font-size:11px;font-weight:500;
  letter-spacing:.14em;text-transform:uppercase;color:var(--accent-text);
  display:flex;align-items:center;gap:6px;min-height:16px;
}
.tenda-caret{
  display:inline-block;width:7px;height:12px;background:var(--accent-text);
  animation:tenda-lampeggio 1.06s steps(1) infinite;
}
@keyframes tenda-lampeggio{0%,50%{opacity:1}50.01%,100%{opacity:0}}
.tenda-stato{color:var(--ink-3);font-size:13px;line-height:1.55;
  margin:0;min-height:62px}   /* 3 righe: i messaggi cambiano, la targa no */

/* Avanzamento a blocchi. Una barra continua promette una precisione che
   non abbiamo: di un risveglio si sa la direzione, non i secondi. */
.tenda-metro{display:flex;gap:2px;align-items:center}
.tenda-metro i{
  width:7px;height:12px;background:var(--surface-3);
  box-shadow:inset 0 0 0 1px var(--line);
}
.tenda-metro i.on{background:var(--accent);box-shadow:none}
@media (min-width:1024px){
  .tenda-cartiglio{max-width:390px;padding:var(--sp-7) var(--sp-6) var(--sp-6);
    gap:var(--sp-4)}
  .tenda-titolo{font-size:31px}
  .tenda-stato{font-size:14px}
}
.tenda-tempo{font-family:var(--mono);font-size:11px;color:var(--ink-4);
  letter-spacing:.1em;font-variant-numeric:tabular-nums;min-height:15px}
.tenda-riprova{display:none;margin-top:var(--sp-1)}
.tenda-riprova.show{display:inline-flex}

/* --- Il sipario ------------------------------------------------------
   Sale tutta la tenda, e il mosaico sale un altro po' dentro di lei:
   due nodi in movimento, non mille. Da fuori e' un movimento solo con
   dentro la sua profondita'. */
.tenda.su{
  animation:none;pointer-events:none;
  transform:translateY(-102%);
  transition:transform .8s var(--ease) .05s;
}
.tenda.su .tenda-mosaico{
  transform:translateY(-9vh);
  transition:transform .8s var(--ease);
}
.tenda.su .tenda-centro{opacity:0;transition:opacity .22s linear}
@keyframes tenda-sicurezza{to{transform:translateY(-102%)}}

/* Chi ha chiesto meno movimento non vuole un sipario: la tenda sfuma,
   e niente lampeggia. */
@media (prefers-reduced-motion:reduce){
  .tenda{animation:tenda-sicurezza-fade .5s linear 3.5s forwards}
  .tenda-spazzata,.tenda-caret{animation:none}
  .tenda-spazzata{display:none}
  .tenda.su{transform:none;opacity:0;transition:opacity .3s linear}
  .tenda.su .tenda-mosaico{transform:none;transition:none}
  @keyframes tenda-sicurezza-fade{to{opacity:0;visibility:hidden}}
}
"""


# ---------------------------------------------------------------------------
# Markup
# ---------------------------------------------------------------------------

_BLOCCHI_HTML = "<i></i>" * N_BLOCCHI


def tenda_html(attesa: bool = False, saluto: str = "") -> str:
    """
    La tenda.

    Senza argomenti e' quella di dentro l'app: mosaico gia' composto e
    marchio, si alza al primo paint. Con `attesa=True` e' quella della
    pagina d'attesa: si compone piano e aggiunge saluto, stato, metro,
    cronometro e bottone.

    `saluto` e' il "Ciao Emanuele" della home: la tenda dice la stessa
    cosa che dira' la pagina sotto, cosi' alzandosi non cambia discorso.
    Le altre pagine passano il solo marchio, senza targa attorno: una
    cornice vuota con dentro un bollino sembra un errore.

    `aria-hidden` solo nella versione di dentro l'app: li' la tenda e'
    decorazione sopra una pagina che esiste gia', e leggerla ad alta voce
    sarebbe rumore. Nella pagina d'attesa invece la tenda *e'* la pagina:
    quel che dice va letto.
    """
    aria = "" if attesa else ' aria-hidden="true"'
    classe = "tenda resta" if attesa else "tenda"
    spazzata = '<div class="tenda-spazzata"></div>' if attesa else ""
    corpo = ""
    if not attesa and saluto:
        corpo = f'<h1 class="tenda-titolo">{saluto}</h1>'
    if attesa:
        corpo = f"""
      <h1 class="tenda-titolo" id="tendaTitolo">Un attimo</h1>
      <div class="tenda-fase"><span id="tendaFase">Risveglio in corso</span
        ><b class="tenda-caret"></b></div>
      <p class="tenda-stato" id="tendaStato" role="status" aria-live="polite">
        Sto accendendo le luci.</p>
      <div class="tenda-metro" id="tendaMetro" aria-hidden="true">{_BLOCCHI_HTML}</div>
      <div class="tenda-tempo" id="tendaTempo"></div>
      <button type="button" class="btn ghost tenda-riprova" id="tendaRiprova">
        Riprova adesso
      </button>"""
    # Lo script sta qui, in linea, subito dopo il contenitore: gira
    # durante il parsing, quindi il mosaico e' gia' fatto al primo paint.
    marchio = '<div class="tenda-marchio">B2F</div>'
    centro = (f'<div class="tenda-cartiglio">{marchio}{corpo}</div>'
              if corpo else marchio)
    return f"""<div class="{classe}" id="tenda"{aria}>
  <div class="tenda-mosaico" id="tendaMosaico"></div>
  <div class="tenda-vetro"></div>{spazzata}
  <div class="tenda-centro">
    {centro}
  </div>
</div>
<script>b2fTenda.costruisci({"false" if attesa else "true"});</script>"""


# ---------------------------------------------------------------------------
# Il costruttore del mosaico — serve a tutte e due le tende
# ---------------------------------------------------------------------------

TENDA_JS = """<script>
window.b2fTenda = (function(){
  // Caso seminato (mulberry32). Il seme decide *tutto* il quadro: se la
  // pagina d'attesa e la pagina vera partono dallo stesso seme, il
  // mosaico e' identico e il passaggio non si vede. Cambiando seme
  // cambia il quadro — uno diverso a ogni avvio.
  function dado(seme){
    return function(){
      seme |= 0; seme = seme + 0x6D2B79F5 | 0;
      var t = Math.imul(seme ^ seme >>> 15, 1 | seme);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // --- La tavolozza --------------------------------------------------
  // Nasce dall'accento scelto nel pannello Aspetto, non da una lista di
  // colori scritta qui: cambi accento e cambia tutto il quadro, restando
  // in casa. Nove tinte — l'accento, i suoi vicini di tonalita' e due
  // note lontane — con luminosita' tenuta nella fascia del tema: al buio
  // resta buio, in chiaro resta chiaro.
  function hslDaHex(h){
    h = h.trim().replace('#','');
    if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
    var r = parseInt(h.slice(0,2),16)/255,
        g = parseInt(h.slice(2,4),16)/255,
        b = parseInt(h.slice(4,6),16)/255;
    var max = Math.max(r,g,b), min = Math.min(r,g,b), d = max - min;
    var l = (max + min) / 2, sa = 0, hu = 0;
    if (d){
      sa = l > .5 ? d / (2 - max - min) : d / (max + min);
      hu = max === r ? ((g - b) / d + (g < b ? 6 : 0))
         : max === g ? (b - r) / d + 2
         :             (r - g) / d + 4;
      hu *= 60;
    }
    return [hu, sa, l];
  }

  function tavolozza(caso, chiaro){
    var css = getComputedStyle(document.documentElement);
    var acc = hslDaHex(css.getPropertyValue('--accent') || '#6f5cf0');

    // Non una manciata di tinte sparse: una rampa. Parte da un colore
    // appena diverso dal secondario del tema — la stessa luminosita'
    // delle superfici, ma con un'ombra della tonalita' dell'accento —
    // e arriva al massimo all'accento stesso. Niente sale piu' in alto:
    // il colore principale resta il punto piu' alto del quadro.
    // Il capo "secondario". In chiaro non puo' essere chiaro quanto le
    // superfici dell'app (sono quasi bianche): a quel punto meta' quadro
    // sparirebbe nel fondo pagina. Sta un gradino sotto, quel tanto che
    // basta perche' la tessera si veda.
    var giu = chiaro ? .80 : .13;
    var su  = chiaro ? Math.max(acc[2], .40)      // il capo "accento"
                     : Math.min(acc[2], .54);
    // Con l'accento grafite (grigio voluto) la rampa resterebbe piatta:
    // un pavimento di saturazione le lascia un filo di colore.
    var sMax = Math.max(acc[1], .26);
    // Quanto colore ha gia' il capo basso della rampa: in chiaro serve
    // piu' tinta, se no le tessere piu' chiare diventano grigio carta.
    var sMin = chiaro ? .40 : .16;

    // Il percorso della tonalita' cambia a ogni avvio: parte spostata di
    // qualche grado e si incurva prima di chiudere sull'accento. E' il
    // motivo per cui due quadri della stessa famiglia non sono mai la
    // stessa sfumatura.
    var scarto = (caso() - .5) * 44;              // +-22 gradi in partenza
    var arco   = (caso() - .5) * 30;              // la pancia della curva
    // >1: la rampa sta bassa piu' a lungo, e l'accento resta un punto di
    // luce invece di diventare la parete. Un quadro dove il colore
    // principale copre mezzo schermo non e' un quadro, e' un fondale.
    var curva  = .95 + caso() * .9;

    var N = 20, tinte = [];
    for (var i = 0; i < N; i++){
      var t = i / (N - 1);
      var e = Math.pow(t, curva);
      tinte.push([
        (acc[0] + scarto * (1 - t) + arco * Math.sin(Math.PI * t) + 360) % 360,
        sMax * (sMin + (1 - sMin) * e),
        giu + (su - giu) * e
      ]);
    }
    return tinte;
  }

  // --- I quadri ------------------------------------------------------
  // Ognuno riempie una mappa col x rig di indici di tavolozza. Sono
  // cinque modi diversi di sporcare una griglia: quale tocchi lo decide
  // il seme, quindi il mosaico di stasera non e' quello di stamattina.

  // Rumore di valore: valori casuali sui nodi di una griglia larga,
  // interpolati in mezzo. E' la base delle onde e serve anche altrove.
  function rumore(caso){
    var g = {};
    function nodo(i, j){
      var k = i + ',' + j;
      if (!(k in g)) g[k] = caso();
      return g[k];
    }
    return function(x, y){
      var i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j;
      var sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
      var a = nodo(i, j)     + (nodo(i+1, j)     - nodo(i, j))     * sx;
      var b = nodo(i, j + 1) + (nodo(i+1, j + 1) - nodo(i, j + 1)) * sx;
      return a + (b - a) * sy;
    };
  }

  function onde(col, rig, caso, n){
    var r1 = rumore(caso), r2 = rumore(caso);
    var s = .05 + caso() * .06, m = new Uint8Array(col * rig);
    for (var y = 0; y < rig; y++) for (var x = 0; x < col; x++){
      var v = r1(x * s, y * s) * .74 + r2(x * s * 2.4, y * s * 2.4) * .26;
      m[y * col + x] = Math.min(n - 1, Math.floor(v * n * 1.15));
    }
    return m;
  }

  function raggi(col, rig, caso, n){
    var cx = col * (.2 + caso() * .6), cy = rig * (.2 + caso() * .6);
    var settori = 2 + Math.floor(caso() * 5), passo = .015 + caso() * .05;
    var r1 = rumore(caso), m = new Uint8Array(col * rig);
    for (var y = 0; y < rig; y++) for (var x = 0; x < col; x++){
      var a = Math.atan2(y - cy, x - cx) / (Math.PI * 2) + .5;
      var d = Math.hypot(x - cx, y - cy);
      // Il rumore serve a sporcare il bordo fra un raggio e l'altro, non
      // a rimescolare la carta: pesa poco apposta.
      var v = a * settori + d * passo + r1(x * .07, y * .07) * .35;
      m[y * col + x] = Math.floor(((v % 1) + 1) % 1 * n) % n;
    }
    return m;
  }

  function blocchi(col, rig, caso, n){
    // Suddivisione ricorsiva: un rettangolo si taglia in due finche' non
    // diventa piccolo. Ne esce una parete alla Bauhaus, tutta ad angoli
    // retti, che con le tessere quadrate sta bene.
    var m = new Uint8Array(col * rig);
    // Tre tinte sole, sorteggiate per questo quadro: una parete Bauhaus
    // con sei colori diventa un mosaico da bar.
    var uso = [Math.floor(caso() * n), Math.floor(caso() * n),
               Math.floor(caso() * n), Math.floor(caso() * n)];
    (function taglia(x0, y0, w, h, prof){
      if (prof > 6 || (w <= 2 || h <= 2) || (w * h <= 9 && caso() < .6)){
        var c = uso[Math.floor(caso() * uso.length)];
        for (var y = y0; y < y0 + h; y++)
          for (var x = x0; x < x0 + w; x++) m[y * col + x] = c;
        return;
      }
      if (w >= h){
        var t = 1 + Math.floor(caso() * (w - 1));
        taglia(x0, y0, t, h, prof + 1); taglia(x0 + t, y0, w - t, h, prof + 1);
      } else {
        var u = 1 + Math.floor(caso() * (h - 1));
        taglia(x0, y0, w, u, prof + 1); taglia(x0, y0 + u, w, h - u, prof + 1);
      }
    })(0, 0, col, rig, 0);
    return m;
  }

  function intreccio(col, rig, caso, n){
    // Piastrelle di Truchet: ogni cella e' tagliata da una diagonale, e
    // le diagonali di celle vicine si inseguono. Da lontano si legge
    // come uno schizzo a tratti.
    var lato = 3 + Math.floor(caso() * 4), m = new Uint8Array(col * rig);
    var celle = {};
    function cella(i, j){
      var k = i + ',' + j;
      if (!(k in celle)){
        // Le due meta' della cella prendono tinte vicine: due colori
        // qualsiasi darebbero rumore, due vicini danno un tratto.
        var a = Math.floor(caso() * n);
        celle[k] = [caso() < .5, a,
                    Math.min(n - 1, a + 2 + Math.floor(caso() * 5))];
      }
      return celle[k];
    }
    for (var y = 0; y < rig; y++) for (var x = 0; x < col; x++){
      var i = Math.floor(x / lato), j = Math.floor(y / lato);
      var c = cella(i, j), fx = (x % lato) / lato, fy = (y % lato) / lato;
      var sopra = c[0] ? (fx + fy < 1) : (fx < fy);
      m[y * col + x] = sopra ? c[1] : c[2];
    }
    return m;
  }

  function dune(col, rig, caso, n){
    // Interferenza di due onde: bande che si piegano. E' il quadro piu'
    // "morbido" del gruppo, quello che sembra una fotografia sfocata.
    var a = .08 + caso() * .18, b = .06 + caso() * .16;
    var c = 1 + caso() * 3, d = 1 + caso() * 3, giro = caso() * 6.28;
    var m = new Uint8Array(col * rig);
    for (var y = 0; y < rig; y++) for (var x = 0; x < col; x++){
      var v = Math.sin(x * a + Math.sin(y * b + giro) * c)
            + Math.sin(y * b * 1.7 + Math.sin(x * a * .8) * d);
      m[y * col + x] = Math.min(n - 1, Math.floor((v + 2) / 4 * n));
    }
    return m;
  }

  var QUADRI = [onde, raggi, blocchi, intreccio, dune];
  var NOMI   = ['onde', 'raggi', 'blocchi', 'intreccio', 'dune'];

  var api = {tessere: [], ordine: [], accese: 0, seme: 0, quadro: ''};

  api.costruisci = function(tutte, seme){
    var box = document.getElementById('tendaMosaico');
    if (!box) return;

    // Il seme: quello passato, quello lasciato dalla pagina d'attesa, o
    // uno nuovo. E' l'unica cosa casuale di tutto il modulo.
    if (seme == null){
      seme = (window.__b2fSeme != null) ? window.__b2fSeme
                                        : Math.floor(Math.random() * 1e9);
    }
    api.seme = seme;

    var vw = document.documentElement.clientWidth  || window.innerWidth  || 390;
    var vh = document.documentElement.clientHeight || window.innerHeight || 800;

    // Tessere minute: ~15px sul telefono, ~19 sul desktop. Piu' sono
    // fitte e piu' la rampa di colori ha spazio per fare un'immagine
    // invece di una scacchiera. Il tetto a 4000 e' il punto oltre il
    // quale il browser inizia a soffrire per niente: da li' in su la
    // tessera si ingrossa invece di moltiplicarsi.
    var lato = vw < 480 ? 15 : (vw < 1024 ? 17 : 19);
    var col, rig;
    for (;;){
      col = Math.max(8, Math.round(vw / lato));
      rig = Math.max(8, Math.round(vh / lato));
      if (col * rig <= 4000 || lato > 96) break;
      lato += 2;
    }

    var n = col * rig;
    var caso = dado(seme);
    var chiaro = document.documentElement.dataset.theme === 'light';
    var tinte = tavolozza(caso, chiaro);
    var scelto = Math.floor(caso() * QUADRI.length);
    api.quadro = NOMI[scelto];
    var mappa = QUADRI[scelto](col, rig, caso, tinte.length);

    var pezzi = new Array(n), chiavi = new Array(n);
    for (var i = 0; i < n; i++){
      var t = tinte[mappa[i]];
      // Un pizzico di luminosita' a caso per tessera: due tessere della
      // stessa tinta non sono mai identiche, ed e' quello che fa sembrare
      // il mosaico fatto a mano invece che stampato.
      var l = Math.max(.05, Math.min(.94, t[2] + (caso() - .5) * .045));
      pezzi[i] = '<i style="--c:hsl(' + t[0].toFixed(0) + ','
               + (t[1] * 100).toFixed(0) + '%,' + (l * 100).toFixed(1) + '%)"></i>';
      // Ordine di accensione: dall'alto in basso, ma con abbastanza
      // disordine da far frastagliare il bordo invece di calare come
      // una saracinesca.
      chiavi[i] = [i + (caso() - .5) * n * .28, i];
    }
    box.style.gridTemplateColumns = 'repeat(' + col + ',1fr)';
    box.style.gridTemplateRows    = 'repeat(' + rig + ',1fr)';
    // Con la tessera minuta anche la fuga va stretta, se no si vede piu'
    // griglia che quadro.
    box.style.gap = lato < 20 ? '1px' : '2px';
    box.innerHTML = pezzi.join('');

    chiavi.sort(function(a, b){ return a[0] - b[0]; });
    api.tessere = Array.prototype.slice.call(box.children);
    api.ordine  = chiavi.map(function(k){ return k[1]; });
    api.accese  = 0;
    if (tutte) api.componi(1);
  };

  // Accende le tessere fino alla quota data. Va solo in avanti: chiamarla
  // due volte con la stessa quota non costa niente.
  api.componi = function(quota){
    var n = Math.round(quota * api.ordine.length);
    while (api.accese < n){
      api.tessere[api.ordine[api.accese++]].classList.add('on');
    }
  };

  return api;
})();
</script>"""


# ---------------------------------------------------------------------------
# Il pezzo che gira dentro l'app
# ---------------------------------------------------------------------------
# Va nel <head>, prima del primo paint: decide se la tenda si vede
# (l'attributo data-tenda) e la alza appena la pagina e' in piedi.
# Registra anche il service worker — prima stava solo nella pagina delle
# ore, quindi chi non passava mai da li' non l'aveva installato.

TENDA_BOOT = """<script>
(function(){
  var d = document.documentElement;

  // Arrivo dalla pagina d'attesa: la tenda era gia' giu', deve restare
  // giu' e alzarsi da qui. Il flag si consuma subito, vale un passaggio.
  try{
    if (sessionStorage.getItem('b2f-tenda') === '1'){
      sessionStorage.removeItem('b2f-tenda');
      d.setAttribute('data-tenda','1');
      // Lo stesso seme dell'attesa: stesso quadro, stesse tinte. Senza,
      // alzandosi la tenda sarebbe un'altra tenda.
      var sm = sessionStorage.getItem('b2f-seme');
      if (sm !== null) window.__b2fSeme = parseInt(sm, 10);
      sessionStorage.removeItem('b2f-seme');
    }
    // Sono dentro l'app: il conto dei giri d'attesa riparte da zero.
    sessionStorage.removeItem('b2f-attese');
  }catch(e){}

  var APERTA = Date.now();

  function alza(){
    var el = document.getElementById('tenda');
    if (!el || el.classList.contains('su')) return;
    // Minimo 300ms in scena: sotto si legge come uno sfarfallio, non
    // come una tenda che si alza.
    var manca = 300 - (Date.now() - APERTA);
    if (manca > 0){ setTimeout(alza, manca); return; }
    el.classList.add('su');
    setTimeout(function(){
      if (el.parentNode) el.parentNode.removeChild(el);
      d.removeAttribute('data-tenda');
    }, 1000);
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', alza);
  } else {
    alza();
  }
  // Se qualcosa nel DOMContentLoaded esplode, la tenda si alza comunque
  // (e in ogni caso c'e' l'animazione di sicurezza nel CSS).
  setTimeout(alza, 2600);

  if ('serviceWorker' in navigator){
    window.addEventListener('load', function(){
      try{
        navigator.serviceWorker.register('/sw.js').then(function(){
          // Un colpetto al worker: se la tenda non e' finita in cache
          // (installazione andata a vuoto perche' il servizio dormiva)
          // se la rimette adesso che l'app risponde. Il messaggio parte
          // da qui e non dal worker perche' li' dentro il momento buono
          // per rifare la cache non arriva mai da solo: l'install gira
          // una volta e basta.
          return navigator.serviceWorker.ready;
        }).then(function(reg){
          if (reg && reg.active) reg.active.postMessage('rammenda');
        }).catch(function(){});
      }catch(e){}
    });
  }
})();
</script>"""


# ---------------------------------------------------------------------------
# La pagina d'attesa
# ---------------------------------------------------------------------------

_ATTESA_JS = """<script>
(function(){
  var fase    = document.getElementById('tendaFase');
  var stato   = document.getElementById('tendaStato');
  var metro   = Array.prototype.slice.call(
                  document.getElementById('tendaMetro').children);
  var tempo   = document.getElementById('tendaTempo');
  var riprova = document.getElementById('tendaRiprova');

  var inizio  = Date.now();
  var sveglio = false;
  var quota   = 0;

  // Il nome lo lascia la home in localStorage (shared/theme.py): questa
  // pagina vive in cache e di dati non ne ha nessuno, ma il saluto è
  // l'unica cosa che vale la pena di ricordarsi — cosi' anche l'attesa
  // sa chi sta aspettando.
  try{
    var nome = localStorage.getItem('b2f-nome');
    if (nome) document.getElementById('tendaTitolo').textContent = 'Ciao ' + nome;
  }catch(e){}

  // Quante volte ho gia' mostrato questa pagina in questa sessione. Se
  // /ping risponde ma la pagina vera non si apre lo stesso, ricaricare
  // all'infinito e' un cane che si morde la coda: dopo tre giri mi fermo
  // e lascio decidere a chi guarda.
  var giri = 1;
  try{
    giri = (parseInt(sessionStorage.getItem('b2f-attese'), 10) || 0) + 1;
    sessionStorage.setItem('b2f-attese', String(giri));
  }catch(e){}

  // Le frasi. Una ogni quattro secondi e mezzo, in ordine sparso: chi
  // aspetta trenta secondi ne legge sei o sette, e non sono mai le
  // stesse dell'altra volta. L'attesa non si accorcia, ma si passa
  // meglio in compagnia.
  var FRASI = [
    "Sto accendendo le luci.",
    "Metto su il caffè, intanto.",
    "Il server dormiva della grossa.",
    "Cerco le chiavi dell'ufficio.",
    "Tiro fuori i conti dal cassetto.",
    "Spolvero le fatture del mese.",
    "Rimetto le tessere al loro posto.",
    "Conto i saldi con le dita.",
    "Apro le finestre, si respira.",
    "Riscaldo le valvole.",
    "Do una passata al registro delle ore.",
    "Sistemo gli scontrini in ordine."
  ];
  var FRASI_LUNGHE = [
    "Ok, questa volta ci sta mettendo un po'.",
    "Giuro che di solito è più sveglio.",
    "Ancora un momento e siamo dentro."
  ];

  // Ordine sparso, seme dall'orologio: attese diverse, frasi diverse.
  var sparse = FRASI.slice();
  for (var k = sparse.length - 1; k > 0; k--){
    var j = Math.floor(Math.random() * (k + 1));
    var tmp = sparse[k]; sparse[k] = sparse[j]; sparse[j] = tmp;
  }

  // Lo stato in monospaziato: quello sì che dice a che punto siamo.
  var FASI = [
    [0,  "Risveglio in corso"],
    [24, "Ci siamo quasi"],
    [50, "Più del solito"]
  ];

  function orologio(sec){
    var m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function mostra(q){
    quota = q;
    b2fTenda.componi(q);
    var n = Math.round(q * metro.length);
    for (var i = 0; i < metro.length; i++){
      metro[i].classList.toggle('on', i < n);
    }
  }

  function battito(){
    if (sveglio) return;
    var sec = (Date.now() - inizio) / 1000;
    // Asintotica: si ferma al 92% e l'ultimo tratto lo fa il risveglio
    // vero. Una barra che arriva in fondo e poi aspetta e' una bugia.
    mostra(Math.min(.92, 1 - Math.exp(-sec / 14)));
    for (var i = 0; i < FASI.length; i++){
      if (sec >= FASI[i][0]) fase.textContent = FASI[i][1];
    }
    var giro = Math.floor(sec / 4.5);
    var frase = giro < sparse.length
      ? sparse[giro]
      : FRASI_LUNGHE[(giro - sparse.length) % FRASI_LUNGHE.length];
    if (stato.textContent !== frase) stato.textContent = frase;
    tempo.textContent = sec >= 5 ? orologio(sec) : '';
    if (sec >= 45) riprova.classList.add('show');
  }

  function arrivato(){
    if (sveglio) return;
    sveglio = true;
    mostra(1);
    tempo.textContent = '';
    if (giri > 3){
      // L'app risponde ma continuo a tornare qui: non ricarico piu' da
      // solo, dico cosa sta succedendo.
      fase.textContent  = "Qualcosa non torna";
      stato.textContent = "Il server risponde, ma la pagina non si apre. "
                        + "Riprova, o riapri l'app fra un minuto.";
      riprova.classList.add('show');
      return;
    }
    fase.textContent  = "Sveglio";
    stato.textContent = "Eccoci.";
    // La tenda non si alza qui: si alza dentro l'app, un attimo dopo il
    // caricamento. E' lo stesso mosaico, ed e' un movimento solo.
    try{
      sessionStorage.setItem('b2f-tenda', '1');
      sessionStorage.setItem('b2f-seme', String(b2fTenda.seme));
    }catch(e){}
    setTimeout(function(){ location.reload(); }, 480);
  }

  async function bussa(){
    if (sveglio) return;
    try{
      var r = await fetch('/ping?t=' + Date.now(),
                          {cache: 'no-store', credentials: 'same-origin'});
      // "Sveglio" non vuol dire "mi ha risposto di sì": vuol dire che ha
      // risposto l'app e non il proxy di Render. L'header sta su ogni
      // risposta nostra, anche su un 401 — cosi' se un domani /ping
      // finisse dietro il PIN il risveglio si vedrebbe lo stesso, e a
      // chiedere il codice ci penserebbe il gate della pagina vera.
      if (r.headers.get('X-B2F')){ arrivato(); return; }
      if (!r.ok) return;
      // Senza header: o e' una risposta vecchia dell'app o e' il proxy,
      // che risponde HTML — e li' il parse JSON fallisce, che e'
      // esattamente il segnale che serve.
      var j = await r.json();
      if (j && j.b2f) arrivato();
    }catch(e){ /* dorme ancora */ }
  }

  // Girata la schermo, la griglia non e' piu' quadrata: si rifa', e le
  // tessere gia' accese si riaccendono subito (componi va solo avanti).
  var attesaGiro;
  window.addEventListener('resize', function(){
    clearTimeout(attesaGiro);
    attesaGiro = setTimeout(function(){
      b2fTenda.costruisci(false, b2fTenda.seme);   // stesso quadro, altra griglia
      b2fTenda.componi(quota);
    }, 250);
  });

  riprova.addEventListener('click', function(e){
    e.stopPropagation();
    location.reload();
  });

  // Tocco fuori dalla targa: la targa sparisce e si guarda il mosaico
  // per intero. Tocco di nuovo (ovunque, la targa nascosta non prende
  // piu' i click) e torna.
  var centro = document.querySelector('.tenda-centro');
  document.getElementById('tenda').addEventListener('click', function(e){
    if (centro.classList.contains('via')){ centro.classList.remove('via'); return; }
    if (e.target.closest('.tenda-cartiglio')) return;   // sulla targa, no
    centro.classList.add('via');
  });
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) bussa();
  });

  battito();
  setInterval(battito, 250);
  bussa();
  setInterval(bussa, 2000);
})();
</script>"""


def render_attesa() -> str:
    """
    La pagina servita dal service worker quando l'app non risponde.

    Vive in cache, quindi si carica anche a server spento: da li' bussa a
    /ping finche' non risponde qualcuno dei nostri, e allora ricarica.
    """
    # Import qui e non in testa: theme importa questo modulo per la tenda
    # (TENDA_CSS, TENDA_JS, TENDA_BOOT), e in testa i due si morderebbero
    # la coda.
    from .theme import page_head
    return f"""{page_head("B2F — un attimo", attesa=True)}
<body>
<style>html,body{{overflow:hidden}}</style>
{tenda_html(attesa=True)}
{_ATTESA_JS}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Il service worker
# ---------------------------------------------------------------------------

def _versione() -> str:
    """
    Impronta della pagina d'attesa, usata come nome della cache.

    Il browser reinstalla il service worker solo se /sw.js cambia byte.
    Con un nome fisso, una tenda ridisegnata resterebbe in cache per
    sempre: la si vedrebbe cambiare solo cambiando anche il worker, e
    prima o poi ci si dimentica. Cosi' invece basta toccare la tenda (o
    i token del design, che ci finiscono dentro) e il nome cambia da
    solo: nuovo worker, nuova cache, e l'activate butta la vecchia.
    """
    from hashlib import sha1
    return sha1(render_attesa().encode("utf-8")).hexdigest()[:10]

SERVICE_WORKER = r"""
// sw.js — generato da shared/caricamento.py
//
// Fa una cosa sola: quando una navigazione non riceve risposta
// dall'app, serve la pagina d'attesa invece della schermata di Render.
//
// "Risposta dell'app" = risposta con l'header X-B2F. Non si prova a
// riconoscere l'HTML di Render (cambia quando vogliono loro): si
// riconosce il nostro, che cambia quando vogliamo noi.

const CACHE  = '__CACHE__';
const ATTESA = '/attesa';
const CORREDO = [
  ATTESA,
  '/static/fonts/inter-normal.woff2',
  '/static/fonts/instrument-serif-normal.woff2'
];

// Mette in cache una risorsa, ma solo se e' quella giusta. Per /attesa
// "giusta" vuol dire che dentro c'e' davvero la tenda: se l'app e'
// protetta dal PIN e un domani quella rotta finisse dietro il gate, qui
// arriverebbe la shell del PIN — e verrebbe servita al posto della tenda
// proprio quando il server dorme, cioe' quando sbloccare e' impossibile.
// Meglio nessuna cache che una cache che inchioda.
async function metti(c, u){
  const r = await fetch(u, {cache: 'reload'});
  if (!r.ok) return;
  if (u === ATTESA){
    const testo = await r.clone().text();
    // Il metro d'avanzamento esiste **solo** nella pagina d'attesa: il
    // mosaico invece sta in ogni pagina, shell del PIN compresa, quindi
    // cercare quello non distinguerebbe niente.
    if (testo.indexOf('id="tendaMetro"') < 0) return;
  }
  await c.put(u, r);
}

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(CACHE);
    // Uno per uno: se un font non c'e', l'attesa deve restare in cache
    // lo stesso (con addAll basterebbe un 404 per buttare via tutto).
    await Promise.all(CORREDO.map(u => metti(c, u).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const nomi = await caches.keys();
    await Promise.all(nomi.filter(n => n !== CACHE).map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try{ url = new URL(req.url); }catch(err){ return; }
  if (url.origin !== self.location.origin) return;

  // I caratteri dalla cache: a server spento la pagina d'attesa deve
  // avere i suoi, non ripiegare sul font di sistema a meta' schermata.
  if (url.pathname.startsWith('/static/fonts/')){
    e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
    return;
  }

  if (req.mode !== 'navigate') return;
  e.respondWith(navigazione(req));
});

// La pagina, appena l'app le risponde, manda un colpetto: se la tenda
// non e' in cache (installazione fatta mentre il servizio dormiva: l'add
// fallisce, e l'install non gira una seconda volta) e' il momento buono
// per rimettercela. Qui waitUntil si puo' chiamare — nel fetch, dopo un
// await, l'evento non e' piu' vivo e la chiamata fallirebbe.
self.addEventListener('message', (e) => {
  if (e.data === 'rammenda') e.waitUntil(rammenda());
});

async function navigazione(req){
  let rete = null;
  try{
    rete = await fetch(req);
    // I redirect delle navigazioni tornano opachi: niente header da
    // leggere, e non c'e' niente da decidere. Passano.
    if (rete.type === 'opaqueredirect' || rete.redirected) return rete;
    if (rete.headers.get('X-B2F')){
      return rete;
    }
  }catch(err){ /* rete assente, o servizio che non risponde affatto */ }

  // Non ha risposto l'app: interstiziale di Render, 502, offline.
  const tenda = await caches.match(ATTESA);
  if (tenda) return tenda;

  // Senza tenda in cache tanto vale far vedere quel che c'e'.
  if (rete) return rete;
  return fetch(req);
}

async function rammenda(){
  try{
    const c = await caches.open(CACHE);
    if (await c.match(ATTESA)) return;
    await Promise.all(CORREDO.map(u => metti(c, u).catch(() => {})));
  }catch(err){ /* ritentera' alla prossima navigazione */ }
}
"""


def service_worker_js() -> str:
    return SERVICE_WORKER.replace("__CACHE__", "b2f-tenda-" + _versione())
