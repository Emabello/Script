"""
shared/theme.py — Shell applicativa B2F.

I token e i componenti stanno in shared/design.py. Qui c'e' il markup:
head, sidebar (desktop), tab bar (mobile), topbar, pannello aspetto e
gate PIN.

API pubblica (invariata rispetto alla versione precedente, cosi' le
pagine esistenti continuano a funzionare):

    render_page(section, eyebrow, title_html, content, breadcrumb, fab)
    render_launchpad(greet_name)
    inject_app_header(page_html, eyebrow, title_html)

Aggiunte:
    page_head(title, prefetch)   -> <head> completo, per chi genera
                                    markup proprio (es. il timesheet)
    app_shell(...)               -> shell completa attorno a un contenuto
"""
from .design import CSS, FONT_FILES, ACCENTI, icon

# ---------------------------------------------------------------------------
# Navigazione: unica sorgente di verita' per sidebar e tab bar.
# ---------------------------------------------------------------------------

NAV = (
    # (chiave sezione, etichetta, href, icona)
    ("home",    "Home",    "/",        "home"),
    ("ore",     "Ore",     "/ore",     "ore"),
    ("fatture", "Fatture", "/fatture", "fatture"),
    ("spese",   "Spese",   "/spese",   "spese"),
    ("saldi",   "Saldi",   "/saldi",   "wallet"),
)


# ---------------------------------------------------------------------------
# Bootstrap tema — deve girare prima del primo paint, altrimenti si vede
# il lampo bianco. Legge le preferenze e le applica su <html>.
# Migra anche la vecchia chiave 'xs-theme' usata dal timesheet.
# ---------------------------------------------------------------------------

_THEME_BOOTSTRAP = """<script>
(function(){
  var d=document.documentElement, ls;
  try{ ls=localStorage }catch(e){ ls=null }
  var pref=(ls&&(ls.getItem('b2f-theme')||ls.getItem('xs-theme')))||'auto';
  var acc=(ls&&ls.getItem('b2f-accent'))||'indigo';
  function resolve(p){
    if(p==='auto'){
      return window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches
        ? 'light' : 'dark';
    }
    return p;
  }
  d.dataset.themePref=pref;
  d.dataset.theme=resolve(pref);
  d.dataset.accent=acc;
  window.b2fResolveTheme=resolve;
})();
</script>"""


_HEAD = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
__BOOTSTRAP__
<title>__TITLE__</title>
<meta name="theme-color" content="#0c0d10" id="metaThemeColor">
<meta name="color-scheme" content="dark light">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="B2F">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
__FONTS__
__PREFETCH__
<style>__CSS__</style>
</head>"""


_FONT_PRELOAD = "".join(
    f'<link rel="preload" href="{f}" as="font" type="font/woff2" crossorigin>'
    for f in FONT_FILES
)


def page_head(title: str, prefetch: list[str] | None = None) -> str:
    """<head> completo con token, componenti e bootstrap del tema."""
    pf = "".join(f'<link rel="prefetch" href="{u}">' for u in (prefetch or []))
    return (_HEAD
            .replace("__BOOTSTRAP__", _THEME_BOOTSTRAP)
            .replace("__TITLE__", title)
            .replace("__FONTS__", _FONT_PRELOAD)
            .replace("__PREFETCH__", pf)
            .replace("__CSS__", CSS))


# Alias storico, usato internamente
_head = page_head


# ---------------------------------------------------------------------------
# Pannello "Aspetto": tema + accento. Presente in ogni pagina, aperto dal
# bottone ingranaggio nella topbar (mobile) o dalla sidebar (desktop).
# ---------------------------------------------------------------------------

def _accent_swatches() -> str:
    out = []
    for key, label in ACCENTI:
        out.append(
            f'<button type="button" data-accent-set="{key}" title="{label}" '
            f'aria-label="Accento {label}"><i data-swatch="{key}"></i></button>'
        )
    return "".join(out)


_APPEARANCE_SHEET = f"""
<style>
/* I campioni del selettore accento mostrano il colore reale di ciascun
   tema, quindi li dichiariamo qui invece che nel design system. */
[data-swatch="indigo"]{{background:#6f5cf0}}
[data-swatch="blue"]{{background:#3b8ef0}}
[data-swatch="violet"]{{background:#a06bf0}}
[data-swatch="graphite"]{{background:#9aa0ad}}
html[data-theme="light"] [data-swatch="indigo"]{{background:#5343cf}}
html[data-theme="light"] [data-swatch="blue"]{{background:#1f6fd0}}
html[data-theme="light"] [data-swatch="violet"]{{background:#7c45c8}}
html[data-theme="light"] [data-swatch="graphite"]{{background:#2b2f38}}
</style>

<div class="sheet-ov" id="apprSheet" role="dialog" aria-modal="true" aria-label="Aspetto">
  <div class="sheet">
    <h3>Aspetto</h3>
    <div class="sheet-sub">Le preferenze restano su questo dispositivo.</div>

    <div class="field">
      <label>Tema</label>
      <div class="segmented" id="themeSeg">
        <button type="button" data-theme-set="auto">Auto</button>
        <button type="button" data-theme-set="light">Chiaro</button>
        <button type="button" data-theme-set="dark">Scuro</button>
      </div>
    </div>

    <div class="field">
      <label>Accento</label>
      <div class="accent-pick" id="accentPick">{_accent_swatches()}</div>
    </div>

    <div class="actions">
      <button type="button" class="btn ghost" data-close="apprSheet">Chiudi</button>
    </div>
  </div>
</div>

<script>
(function(){{
  var d=document.documentElement;
  var meta=document.getElementById('metaThemeColor');
  var COLORS={{dark:'#0c0d10', light:'#f6f7f9'}};

  function syncMeta(){{ if(meta) meta.content = COLORS[d.dataset.theme] || COLORS.dark; }}

  function paintState(){{
    var pref=d.dataset.themePref||'auto', acc=d.dataset.accent||'indigo';
    document.querySelectorAll('[data-theme-set]').forEach(function(b){{
      b.classList.toggle('is-active', b.dataset.themeSet===pref);
    }});
    document.querySelectorAll('[data-accent-set]').forEach(function(b){{
      b.classList.toggle('is-active', b.dataset.accentSet===acc);
    }});
  }}

  window.b2fSetTheme=function(pref){{
    d.dataset.themePref=pref;
    d.dataset.theme=window.b2fResolveTheme(pref);
    try{{ localStorage.setItem('b2f-theme',pref);
          localStorage.setItem('xs-theme',d.dataset.theme); }}catch(e){{}}
    syncMeta(); paintState();
  }};
  window.b2fSetAccent=function(a){{
    d.dataset.accent=a;
    try{{ localStorage.setItem('b2f-accent',a) }}catch(e){{}}
    paintState();
  }};
  window.b2fOpenAppearance=function(){{
    var el=document.getElementById('apprSheet');
    if(el) el.classList.add('show');
  }};

  document.addEventListener('click', function(e){{
    var t=e.target.closest('[data-theme-set]');
    if(t){{ window.b2fSetTheme(t.dataset.themeSet); return; }}
    var a=e.target.closest('[data-accent-set]');
    if(a){{ window.b2fSetAccent(a.dataset.accentSet); return; }}
    var c=e.target.closest('[data-close]');
    if(c){{ var el=document.getElementById(c.dataset.close);
            if(el) el.classList.remove('show'); return; }}
    // Tap fuori dal foglio = chiudi
    if(e.target.classList && e.target.classList.contains('sheet-ov')){{
      e.target.classList.remove('show');
    }}
  }});
  document.addEventListener('keydown', function(e){{
    if(e.key==='Escape'){{
      document.querySelectorAll('.sheet-ov.show').forEach(function(el){{
        el.classList.remove('show');
      }});
    }}
  }});

  // Se il tema e' su "auto", segue il cambio di impostazione di sistema.
  if(window.matchMedia){{
    var mq=window.matchMedia('(prefers-color-scheme: light)');
    var onChange=function(){{
      if((d.dataset.themePref||'auto')==='auto'){{
        d.dataset.theme=window.b2fResolveTheme('auto'); syncMeta();
      }}
    }};
    if(mq.addEventListener) mq.addEventListener('change',onChange);
    else if(mq.addListener) mq.addListener(onChange);
  }}

  syncMeta(); paintState();
}})();
</script>
"""


# ---------------------------------------------------------------------------
# Pezzi della shell
# ---------------------------------------------------------------------------

def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_CURRENT = ' aria-current="page"'


def _rail(active: str) -> str:
    """Sidebar persistente, visibile solo da 1024px in su."""
    links = "".join(
        f'<a class="rail-link{" is-active" if key == active else ""}" href="{href}"'
        f'{_CURRENT if key == active else ""}>'
        f'{icon(ic)}<span>{label}</span></a>'
        for key, label, href, ic in NAV
    )
    return f"""<aside class="rail">
  <a class="rail-brand" href="/">
    <span class="brand-mark">B2F</span>
    <span>
      <span class="brand-name">Hub</span>
      <span class="brand-sub">Ore · Fatture · Spese</span>
    </span>
  </a>
  <nav class="rail-nav" aria-label="Sezioni">{links}</nav>
  <div class="rail-foot">
    <button type="button" class="btn ghost block" onclick="b2fOpenAppearance()">
      {icon("contrast")}Aspetto
    </button>
  </div>
</aside>"""


def _tabbar(active: str) -> str:
    """Tab bar fissa in basso, nascosta da 1024px in su."""
    tabs = "".join(
        f'<a class="tab{" is-active" if key == active else ""}" href="{href}"'
        f'{_CURRENT if key == active else ""}>'
        f'{icon(ic)}<span>{label}</span></a>'
        for key, label, href, ic in NAV
    )
    return f'<nav class="tabbar" aria-label="Sezioni">{tabs}</nav>'


def _topbar(eyebrow: str, title_html: str, back: str | None,
            actions_html: str = "") -> str:
    back_btn = ""
    if back:
        back_btn = (f'<a class="icon-btn hide-desktop" href="{back}" '
                    f'aria-label="Indietro">{icon("back")}</a>')
    eyebrow_html = f'<div class="eyebrow">{eyebrow}</div>' if eyebrow else ""
    return f"""<header class="topbar">
  {back_btn}
  <div class="topbar-title">
    {eyebrow_html}
    <h1 class="h1">{title_html}</h1>
  </div>
  <div class="topbar-actions">
    {actions_html}
    <button type="button" class="icon-btn hide-desktop" aria-label="Aspetto"
            onclick="b2fOpenAppearance()">{icon("contrast")}</button>
  </div>
</header>"""


def _crumb(breadcrumb) -> str:
    if not breadcrumb:
        return ""
    parts = []
    for i, (label, href) in enumerate(breadcrumb):
        parts.append(f'<a href="{href}">{label}</a>' if href else f'<span>{label}</span>')
        if i < len(breadcrumb) - 1:
            parts.append('<span class="sep">›</span>')
    return f'<nav class="crumb" aria-label="Percorso">{"".join(parts)}</nav>'


def _fab(fab) -> str:
    if not fab:
        return ""
    label, href = fab
    return f'<a class="fab" href="{href}">{icon("plus")}{label}</a>'


# ---------------------------------------------------------------------------
# Shell completa
# ---------------------------------------------------------------------------

def app_shell(section: str, eyebrow: str, title_html: str, content: str,
              title: str | None = None,
              breadcrumb=None, fab=None, actions_html: str = "",
              back: str | None = None, prefetch=None,
              extra_body: str = "") -> str:
    """
    Compone una pagina completa: head + sidebar + topbar + contenuto +
    tab bar + pannello aspetto + gate PIN.
    """
    head = page_head(title or f"{eyebrow or 'B2F'} — B2F", prefetch=prefetch)
    html = f"""{head}
<body>
  <div class="app">
    {_rail(section)}
    <div class="main">
      {_topbar(eyebrow, title_html, back, actions_html)}
      {_crumb(breadcrumb)}
      <main class="content">
{content}
      </main>
    </div>
  </div>
  {_tabbar(section)}
  {_fab(fab)}
  {extra_body}
  {_APPEARANCE_SHEET}
</body>
</html>"""
    return _inject_pin_gate(html)


_SECTION_BY_PREFIX = (
    ("/fatture", "fatture"),
    ("/spese",   "spese"),
    ("/ore",     "ore"),
)


def render_page(section: str, eyebrow: str, title_html: str, content: str,
                breadcrumb: list[tuple[str, str]] | None = None,
                fab: tuple[str, str] | None = None,
                actions_html: str = "",
                back: str | None = None) -> str:
    """
    Pagina di sotto-app (Ore, Fatture, Spese). Firma compatibile con la
    versione precedente; `actions_html` e `back` sono aggiunte opzionali.

    Se `back` non e' indicato, viene dedotto dal breadcrumb: la voce con
    href piu' vicina alla fine e' il naturale "indietro" su mobile.
    """
    if back is None and breadcrumb:
        for label, href in reversed(breadcrumb):
            if href:
                back = href
                break
    return app_shell(section=section, eyebrow=eyebrow, title_html=title_html,
                     content=content, breadcrumb=breadcrumb, fab=fab,
                     actions_html=actions_html, back=back)


# ---------------------------------------------------------------------------
# Gate PIN
# ---------------------------------------------------------------------------
# Overlay bloccante iniettato prima di </body> in tutte le pagine della
# hub. All'avvio interroga /api/status; se serve il PIN e la sessione non
# e' sbloccata, si mostra. Intercetta anche le fetch API che rispondono
# 401 (sessione scaduta) e si riapre.

_PIN_GATE = r"""
<style>
.gate{position:fixed;inset:0;z-index:900;display:none;
  align-items:center;justify-content:center;padding:var(--sp-5);
  background:var(--bg)}
.gate.show{display:flex}
.gate-card{width:100%;max-width:360px;text-align:center}
.gate-lock{width:54px;height:54px;border-radius:16px;margin:0 auto var(--sp-4);
  display:grid;place-items:center;background:var(--accent-soft);color:var(--accent)}
.gate-lock svg{width:26px;height:26px;stroke:currentColor;fill:none;stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round}
.gate h2{font-family:var(--display);font-weight:400;font-size:26px;
  letter-spacing:-.01em;margin-bottom:4px}
.gate p{color:var(--ink-3);font-size:13.5px;margin-bottom:var(--sp-5)}
.gate-input{width:100%;min-height:54px;padding:14px var(--sp-4);
  background:var(--surface);border:1px solid var(--line-strong);
  border-radius:var(--r-md);color:var(--ink);
  font-family:var(--sans);font-size:20px;font-weight:500;
  letter-spacing:.5em;text-align:center;font-variant-numeric:tabular-nums}
.gate-input:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft)}
.gate-err{color:var(--neg);font-size:12.5px;margin-top:var(--sp-2);min-height:18px}
.gate-bio{display:none;width:100%;margin-top:var(--sp-2)}
.gate-bio.show{display:inline-flex}
</style>

<div class="gate" id="pinOverlay" role="dialog" aria-modal="true" aria-label="Sblocco">
  <div class="gate-card">
    <div class="gate-lock">
      <svg viewBox="0 0 24 24"><rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/>
      <path d="M7.8 10.5V7a4.2 4.2 0 0 1 8.4 0v3.5"/></svg>
    </div>
    <h2>Accesso protetto</h2>
    <p>Inserisci il PIN per continuare</p>
    <input class="gate-input" id="pinInput" type="password"
           inputmode="numeric" pattern="[0-9]*" autocomplete="off"
           enterkeyhint="done" maxlength="12" placeholder="••••">
    <div class="gate-err" id="pinErr">&nbsp;</div>
    <button class="btn block" id="pinSubmit" type="button">Sblocca</button>
    <button class="btn ghost gate-bio" id="pinBioBtn" type="button">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 11c0 2.5-.3 4.8-1.2 6.8M8.5 20.5A13.5 13.5 0 0 0 9.8 9.5M12 3.5a8.5 8.5 0 0 1 8.5 8.5c0 1.7-.2 3.3-.6 4.8M6.4 6.4A8.5 8.5 0 0 1 12 3.5M4.3 15.5c.4-1.3.7-2.7.7-4a7 7 0 0 1 .4-2.3M15.5 20.2c.5-1.2 1-2.7 1.3-4.2M12 7a5 5 0 0 1 5 5c0 1.2-.1 2.3-.3 3.3"/>
      </svg>
      Sblocca con impronta
    </button>
  </div>
</div>

<script>
// Helper base64url <-> ArrayBuffer per WebAuthn, condivisi con il banner
// di registrazione della home.
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

  function show() { overlay.classList.add('show'); setTimeout(() => input.focus(), 50); }
  function hide() { overlay.classList.remove('show'); input.value=''; setErr(''); }
  function setErr(m) { errBox.textContent = m || ' '; }

  function unlocked() {
    hide();
    if (window.__pinPending) { window.__pinPending(); window.__pinPending = null; }
    else { location.reload(); }
  }

  async function tryShowBioButton() {
    try {
      if (!window.PublicKeyCredential
          || !window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) return;
      const [st, avail] = await Promise.all([
        fetch('/api/webauthn/status', {credentials:'same-origin'}).then(r => r.ok ? r.json() : null),
        PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(),
      ]);
      if (st && st.credentials_count > 0 && avail) bioBtn.classList.add('show');
    } catch (e) { /* resta solo il PIN */ }
  }

  async function bioUnlock() {
    bioBtn.disabled = true; setErr('');
    try {
      const beginRes = await fetch('/api/webauthn/auth/begin', {
        method:'POST', credentials:'same-origin'});
      if (!beginRes.ok) throw new Error('begin failed');
      const options = await beginRes.json();
      options.challenge = b2fBase64urlToBuffer(options.challenge);
      if (options.allowCredentials) {
        options.allowCredentials = options.allowCredentials.map(c => ({
          ...c, id: b2fBase64urlToBuffer(c.id)}));
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
        method:'POST', headers:{'Content-Type':'application/json'},
        credentials:'same-origin', body: JSON.stringify({credential: payload})});
      if (completeRes.ok) unlocked();
      else setErr('Sblocco con impronta non riuscito, usa il PIN');
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
    button.disabled = true; setErr('');
    try {
      const r = await fetch('/api/unlock', {
        method:'POST', headers:{'Content-Type':'application/json'},
        credentials:'same-origin', body: JSON.stringify({pin})});
      if (r.ok) unlocked();
      else { setErr('PIN errato'); input.select(); }
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

  // 401 su una API interna = sessione scaduta -> riapri il gate
  const _fetch = window.fetch;
  window.fetch = async function(...args) {
    const res = await _fetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (res.status === 401 && (url.startsWith('/api/') || url.startsWith('/fatture/api/')
                               || url.startsWith('/spese/api/'))) {
      show();
    }
    return res;
  };

  fetch('/api/status', {credentials:'same-origin'})
    .then(r => r.ok ? r.json() : null)
    .then(s => { if (s && s.needs_pin && !s.unlocked) { show(); tryShowBioButton(); } })
    .catch(() => {});
})();
</script>
"""


def _inject_pin_gate(html: str) -> str:
    if "</body>" in html:
        return html.replace("</body>", _PIN_GATE + "\n</body>", 1)
    return html + _PIN_GATE


def locked_shell() -> str:
    """
    Pagina servita al posto di una rotta protetta, quando manca una
    sessione sbloccata: stessa occhiata (tema, font) della pagina vera ma
    a corpo vuoto — solo il gate del PIN, nessun dato.

    Chi sblocca (PIN o impronta) ricarica la stessa URL: arriva stavolta
    con la sessione valida e il server rende il contenuto vero. Niente
    redirect ne' pagina dedicata da tenere allineata: e' la stessa shell
    di sempre, semplicemente senza `content`.
    """
    return page_head("B2F Hub") + f"<body>{_PIN_GATE}</body></html>"


# ---------------------------------------------------------------------------
# Timesheet: la pagina /ore genera markup proprio. inject_app_header la
# avvolge nella shell condivisa senza toccarne la logica.
# ---------------------------------------------------------------------------

def inject_app_header(page_html: str, eyebrow: str = "Timesheet",
                      title_html: str = 'Le mie <em>ore</em>',
                      actions_html: str = "") -> str:
    """
    Avvolge il markup del timesheet nella shell B2F (head condiviso +
    sidebar + topbar + tab bar + pannello aspetto).

    Il timesheet genera markup proprio e ha `<div class="wrap">` come
    contenitore: lo sostituiamo con l'apertura della shell e la chiudiamo
    prima di </body>, lasciando intatto tutto quello che c'e' in mezzo.
    """
    page_html = page_html.replace("__HEAD__", page_head("Ore — B2F"), 1)

    open_marker = '<div class="wrap">'
    if open_marker not in page_html:
        return page_html

    # Il timesheet e' una pagina a colonna singola: la shell non la stira
    # sull'intera larghezza del desktop.
    topbar = _topbar(eyebrow, title_html, None, actions_html).replace(
        '<header class="topbar">', '<header class="topbar single">', 1)
    shell_open = f"""<div class="app">
  {_rail("ore")}
  <div class="main">
    {topbar}
    <main class="content single">"""
    shell_close = f"""    </main>
  </div>
</div>
{_tabbar("ore")}
{_APPEARANCE_SHEET}"""

    html = page_html.replace(open_marker, shell_open, 1)

    # Chiude la shell dove finiva il vecchio .wrap: subito prima di </body>.
    if "</body>" in html:
        html = html.replace("</body>", shell_close + "\n</body>", 1)
    else:
        html += shell_close
    return html


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
# La home non e' piu' un elenco di tre tile: con la tab bar la navigazione
# e' sempre a portata di pollice, quindi lo spazio della home puo' dire
# qualcosa di utile. Diventa una dashboard: saldo, accantonamento,
# scadenze, ultimi movimenti.

_BIO_BANNER = """
<div class="notice info notice-row mb-3" id="bioBanner" style="display:none">
  <span>Sblocco veloce disponibile su questo dispositivo</span>
  <span style="display:flex;gap:16px;flex-shrink:0">
    <button type="button" id="bioBannerDecline" class="muted">Non ora</button>
    <button type="button" id="bioBannerBtn">Attiva</button>
  </span>
</div>
"""

_GIORNI = ("Lunedì", "Martedì", "Mercoledì", "Giovedì",
           "Venerdì", "Sabato", "Domenica")
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
         "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")


def _oggi_esteso() -> str:
    from datetime import date
    d = date.today()
    return f"{_GIORNI[d.weekday()]} {d.day} {_MESI[d.month - 1]}"


def _kpi(valore: str, etichetta: str, hint: str = "",
         classe: str = "", href: str = "") -> str:
    """Tessera KPI. Cliccabile se `href` e' valorizzato."""
    hint_html = f'<div class="hint">{hint}</div>' if hint else ""
    inner = (f'<div class="stat"><div class="val tnum {classe}">{valore}</div>'
             f'<div class="lbl">{etichetta}</div>{hint_html}</div>')
    if href:
        return f'<a class="card card-link" href="{href}">{inner}</a>'
    return f'<div class="card">{inner}</div>'


def _blocco_saldi(saldi: dict) -> str:
    """
    I due conti, in cima alla home.

    Le altre pagine rispondono a domande diverse — quanto e' entrato e
    uscito questo mese, quanto quest'anno. Questa risponde a "quanto ho
    adesso", con la scomposizione aperta a richiesta: un saldo di cui non
    si vede la formazione non e' verificabile.
    """
    from .fmt import eur, data_it

    piva = saldi.get("piva") or {}
    pers = saldi.get("personale") or {}
    rev = saldi.get("revolut") or {}
    if not (piva.get("disponibile") or pers.get("disponibile")
            or rev.get("disponibile")):
        return ""

    def saldo_txt(v: float) -> str:
        """Un saldo e' un livello, non una variazione: il "+" davanti non
        aggiunge nulla e si legge come un aumento. Il meno invece serve."""
        return ("−" if v < 0 else "") + eur(abs(v))

    def tile(dati: dict, etichetta: str, href: str, hint: str) -> str:
        if not dati.get("disponibile"):
            return (f'<div class="card"><div class="stat">'
                    f'<div class="val tnum muted">—</div>'
                    f'<div class="lbl">{etichetta}</div>'
                    f'<div class="hint">saldo non disponibile</div></div></div>')
        v = float(dati.get("saldo") or 0)
        cls = "pos" if v >= 0 else "neg"
        return (f'<a class="card card-link" href="{href}"><div class="stat">'
                f'<div class="val tnum {cls}">€ {saldo_txt(v)}</div>'
                f'<div class="lbl">{etichetta}</div>'
                f'<div class="hint">{hint}</div></div></a>')

    rivalsa = float(piva.get("rivalsa_incassata") or 0)
    hint_piva = (f'di cui € {eur(rivalsa)} di rivalsa INPS incassata'
                 if rivalsa > 0 else 'movimenti P.IVA, giroconti già usciti')
    hint_pers = f'{pers.get("movimenti", 0)} movimenti, al netto dei risparmi'

    tiles = (tile(piva, "WeBank P.IVA", "/fatture/spese-piva", hint_piva)
             + tile(pers, "WeBank Personale", "/spese", hint_pers))

    # Revolut compare solo se e' stato collegato: una tessera a zero
    # sembrerebbe un conto vuoto invece di un conto mai registrato.
    if rev.get("disponibile"):
        pezzi = [f'risparmi € {eur(rev.get("risparmi", 0))}']
        if rev.get("investimenti"):
            pezzi.append(f'investimenti € {eur(rev["investimenti"])}')
        # Uno snapshot vecchio non e' sbagliato, e' vecchio: dirlo evita
        # di leggerlo come se fosse aggiornato a stamattina.
        if (rev.get("giorni") or 0) > 45:
            pezzi.append(f'fermo da {rev["giorni"]} giorni')
        tiles += tile(rev, "Revolut", "/spese/revolut", " · ".join(pezzi))

    # Il totale ha senso solo se tutti i saldi in gioco sono veri:
    # sommarne una parte darebbe un numero che sembra completo e non lo e'.
    presenti = [c for c in (piva, pers, rev) if c.get("disponibile")]
    if len(presenti) > 1:
        tot = round(sum(float(c["saldo"]) for c in presenti), 2)
        quanti = {2: "due", 3: "tre"}.get(len(presenti), str(len(presenti)))
        tiles += (f'<div class="card"><div class="stat">'
                  f'<div class="val tnum">€ {saldo_txt(tot)}</div>'
                  f'<div class="lbl">Totale sui {quanti} conti</div>'
                  f'<div class="hint">non è tutto tuo: vedi «da accantonare»</div>'
                  f'</div></div>')

    quando = data_it(piva.get("al") or pers.get("al")) or "oggi"

    righe = ""
    if piva.get("disponibile"):
        righe += f'''
      <div class="row"><span class="t">WeBank P.IVA
        <span class="sub">entrate € {eur(piva["entrate"])} − uscite € {eur(piva["uscite"])}
        − giroconti al personale € {eur(piva["girati"])}</span></span>
        <span class="v tnum">€ {eur(piva["saldo"])}</span></div>'''
        if rivalsa > 0:
            righe += f'''
      <div class="row"><span class="t">di cui rivalsa INPS
        <span class="sub">incassata dai clienti dentro il corrispettivo: resta qui,
        è già dentro la quota da accantonare</span></span>
        <span class="v tnum">€ {eur(rivalsa)}</span></div>'''
    if pers.get("disponibile"):
        risparmiato = float(pers.get("risparmiato") or 0)
        meno_risp = (f' − risparmi messi via € {eur(risparmiato)}'
                     if risparmiato else "")
        righe += f'''
      <div class="row"><span class="t">WeBank Personale
        <span class="sub">apertura € {eur(pers["saldo_iniziale"])}
        + entrate € {eur(pers["entrate"])} − uscite € {eur(pers["uscite"])}{meno_risp}</span></span>
        <span class="v tnum">€ {eur(pers["saldo"])}</span></div>'''
    if rev.get("disponibile"):
        righe += f'''
      <div class="row"><span class="t">Revolut
        <span class="sub">liquidità € {eur(rev["conto"])}
        + risparmi € {eur(rev["risparmi"])}
        + investimenti € {eur(rev["investimenti"])}
        · saldi al {data_it(rev.get("data"))}</span></span>
        <span class="v tnum">€ {eur(rev["saldo"])}</span></div>'''

    nota_risparmi = ""
    if float(pers.get("risparmiato") or 0):
        nota_risparmi = (
            " Il risparmio che registri sulla pagina Risparmi esce dal conto "
            "personale e finisce nei salvadanai Revolut: per questo viene "
            "sottratto di qua e compare di là, non è sparito.")

    return f'''
    <div class="grid kpi mb-3">{tiles}</div>
    <details class="explain card mb-4">
      <summary>Come si formano questi saldi</summary>
      <div class="rows detail mt-2">{righe}</div>
      <p class="small muted mt-3">
        Saldi al {quando}: contano tutti i movimenti registrati fino a oggi,
        non solo quelli del mese o dell'anno in corso. I movimenti con data
        futura restano fuori. Sul conto P.IVA il giroconto è un'uscita —
        quei soldi sono già sull'altro conto, e contarli due volte
        gonfierebbe il totale.{nota_risparmi}
        {"Revolut è uno snapshot dall'estratto conto, non un saldo dal vivo."
         if rev.get("disponibile") else ""}
      </p>
    </details>'''


def render_launchpad(greet_name: str | None = None, dati: dict | None = None) -> str:
    """
    Home. Non e' piu' un elenco di tre tile: con la tab bar la navigazione
    e' sempre disponibile, quindi la home puo' dire qualcosa di utile.

    `dati` e' opzionale: senza, la pagina mostra comunque azioni e stato,
    solo senza numeri. Chiavi attese (tutte facoltative):
      saldi {piva, personale} (dict di fiscale.saldo_piva / dati.saldo_conto),
      incassato_mese, saldo_spese_mese, n_fatture_anno, anno,
      accantonamento (dict di fatture.accantonamento.scomponi),
      accantonamento_html, scadenze [(data_iso, descrizione, importo)],
      ultime_fatture [(numero, cliente, data_iso, totale, stato)],
      ultimi_movimenti [(descrizione, data_iso, importo, tipo)],
      errore (stringa da mostrare come avviso)
    """
    from .fmt import eur, eur_segno, data_it, data_breve

    d = dati or {}
    who = (greet_name or "").strip()
    saluto = f'Ciao <em>{who}</em>' if who else 'Ciao <em>tu</em>'

    blocchi = [_BIO_BANNER]

    if d.get("errore"):
        blocchi.append(f'<div class="notice warn mb-3">{d["errore"]}</div>')

    # In cima a tutto: quanto c'e' sui due conti, adesso.
    if d.get("saldi"):
        blocchi.append(_blocco_saldi(d["saldi"]))

    # --- Tessere KPI -------------------------------------------------------
    acc = d.get("accantonamento") or {}
    pref = acc.get("scenario_preferito", "consigliato")
    kpi = []
    if d.get("incassato_mese") is not None:
        kpi.append(_kpi(f'€ {eur(d["incassato_mese"], 0)}', "Incassato questo mese",
                        href="/fatture/storico"))
    if acc.get("importi"):
        kpi.append(_kpi(f'€ {eur(acc["importi"][pref], 0)}', "Da accantonare",
                        hint="sull'incassato del mese", classe="accent",
                        href="/fatture/situazione"))
    if d.get("saldo_spese_mese") is not None:
        s = float(d["saldo_spese_mese"])
        kpi.append(_kpi(f'€ {eur_segno(s, 0)}', "Saldo spese del mese",
                        classe="pos" if s >= 0 else "neg", href="/spese"))
    if d.get("n_fatture_anno") is not None:
        anno = d.get("anno", "")
        kpi.append(_kpi(str(d["n_fatture_anno"]), f"Fatture nel {anno}",
                        href="/fatture/storico"))
    if kpi:
        blocchi.append(f'<div class="grid kpi mb-4">{"".join(kpi)}</div>')

    # --- Card accantonamento ------------------------------------------------
    if d.get("accantonamento_html"):
        blocchi.append(f'<div class="mb-4">{d["accantonamento_html"]}</div>')

    # --- Due colonne su desktop --------------------------------------------
    sinistra, destra = [], []

    fatture = d.get("ultime_fatture") or []
    if fatture:
        righe = "".join(
            f'<a class="row" href="/fatture/{fid}">'
            f'<span class="k">{data_breve(data)}</span>'
            f'<span class="t">{_esc(numero)} · {_esc(cliente)}</span>'
            f'<span class="v tnum">€ {eur(totale)}</span></a>'
            for fid, numero, cliente, data, totale in fatture
        )
        sinistra.append(f'''<div class="card">
          <div class="card-head">
            <div class="eyebrow">Ultime fatture</div>
            <a class="small" style="color:var(--accent-text)" href="/fatture/storico">Tutte ›</a>
          </div>
          <div class="rows">{righe}</div>
        </div>''')

    movimenti = d.get("ultimi_movimenti") or []
    if movimenti:
        righe = "".join(
            f'<div class="row"><span class="k">{data_breve(data)}</span>'
            f'<span class="t">{_esc(desc)}</span>'
            f'<span class="v tnum {"pos" if tipo == "entrata" else "neg" if tipo == "uscita" else ""}">'
            f'{eur_segno(imp if tipo == "entrata" else -imp)}</span></div>'
            for desc, data, imp, tipo in movimenti
        )
        sinistra.append(f'''<div class="card">
          <div class="card-head">
            <div class="eyebrow">Ultimi movimenti</div>
            <a class="small" style="color:var(--accent-text)" href="/spese">Tutti ›</a>
          </div>
          <div class="rows">{righe}</div>
        </div>''')

    scadenze = d.get("scadenze") or []
    if scadenze:
        righe = "".join(
            f'<div class="row"><span class="t">{descr}'
            f'<span class="sub">{data_it(data)}</span></span>'
            f'<span class="v tnum">€ {eur(imp, 0)}</span></div>'
            for data, descr, imp in scadenze
        )
        destra.append(f'''<div class="card">
          <div class="card-head"><div class="eyebrow">Prossime scadenze</div></div>
          <div class="rows detail">{righe}</div>
        </div>''')

    destra.append(f'''<div class="card">
      <div class="card-head"><div class="eyebrow">Azioni rapide</div></div>
      <div class="list">
        <a class="item" href="/fatture/nuova">
          <span class="ico">{icon("plus")}</span>
          <span class="body"><span class="n">Nuova fattura</span></span>
          <span class="chev">{icon("chevron")}</span>
        </a>
        <a class="item" href="/fatture/spese-piva/nuova">
          <span class="ico neutral">{icon("wallet")}</span>
          <span class="body"><span class="n">Nuovo movimento P.IVA</span></span>
          <span class="chev">{icon("chevron")}</span>
        </a>
        <a class="item" href="/fatture/situazione">
          <span class="ico neutral">{icon("fiscale")}</span>
          <span class="body"><span class="n">Situazione fiscale</span></span>
          <span class="chev">{icon("chevron")}</span>
        </a>
        <a class="item" href="/ore">
          <span class="ico neutral">{icon("ore")}</span>
          <span class="body"><span class="n">Registra le ore</span></span>
          <span class="chev">{icon("chevron")}</span>
        </a>
      </div>
    </div>''')

    blocchi.append(
        f'<div class="grid split">'
        f'<div class="stack">{"".join(sinistra)}</div>'
        f'<div class="stack">{"".join(destra)}</div>'
        f'</div>'
    )

    return app_shell(
        section="home",
        eyebrow=_oggi_esteso(),
        title_html=saluto,
        title="B2F — Home",
        content="\n".join(blocchi),
        prefetch=["/ore", "/fatture", "/spese"],
        extra_body=_BIO_SCRIPT,
    )


def _kpi_conto(saldo: dict, tipo: str) -> str:
    """
    Riga di KPI di dettaglio per un conto — entrate/uscite/movimenti e
    quel che e' specifico del tipo. La card in cima (_blocco_saldi) da'
    il saldo e una scomposizione compatta; qui, sulla pagina dedicata,
    c'e' spazio per vedere ogni pezzo come tessera a se', non solo come
    riga di un elenco.
    """
    from .fmt import eur, data_it

    if not saldo.get("disponibile"):
        return ""

    # Il saldo va sempre per primo ed e' sempre la prima tessera: e' la
    # risposta a "quanto ho", non un dato statistico come i flussi che
    # seguono. Un livello, non una variazione: niente "+" davanti, solo
    # il "-" se negativo.
    v_saldo = float(saldo.get("saldo") or 0)
    saldo_txt = ("−" if v_saldo < 0 else "") + eur(abs(v_saldo))
    tile_saldo = _kpi(f'€ {saldo_txt}', "Saldo",
                      classe="pos" if v_saldo >= 0 else "neg")

    tiles = []
    if tipo == "piva":
        tiles = [
            tile_saldo,
            _kpi(f'€ {eur(saldo["entrate"])}', "Entrate", classe="pos"),
            _kpi(f'€ {eur(saldo["uscite"])}', "Uscite", classe="neg"),
            _kpi(f'€ {eur(saldo["girati"])}', "Girate al personale"),
            _kpi(str(saldo.get("movimenti", 0)), "Movimenti"),
        ]
        if saldo.get("rivalsa_incassata"):
            tiles.append(_kpi(f'€ {eur(saldo["rivalsa_incassata"])}',
                              "Rivalsa INPS incassata",
                              hint="già dentro il saldo, non un extra"))
    elif tipo == "personale":
        tiles = [
            tile_saldo,
            _kpi(f'€ {eur(saldo["entrate"])}', "Entrate", classe="pos"),
            _kpi(f'€ {eur(saldo["uscite"])}', "Uscite", classe="neg"),
            _kpi(f'€ {eur(saldo.get("risparmiato", 0))}', "Risparmiato",
                hint="uscito verso i salvadanai"),
            _kpi(str(saldo.get("movimenti", 0)), "Movimenti"),
        ]
    elif tipo == "revolut":
        quando = data_it(saldo.get("data")) or "—"
        giorni = saldo.get("giorni")
        hint_data = (f'fermo da {giorni} giorni' if (giorni or 0) > 45
                    else f'aggiornato al {quando}')
        tiles = [
            tile_saldo,
            _kpi(f'€ {eur(saldo["conto"])}', "Liquidità"),
            _kpi(f'€ {eur(saldo["risparmi"])}', "Risparmi"),
            _kpi(f'€ {eur(saldo["investimenti"])}', "Investimenti"),
            _kpi(quando, "Ultimo estratto", hint=hint_data),
        ]
    if not tiles:
        return ""
    return f'<div class="grid kpi mb-4">{"".join(tiles)}</div>'


def render_saldi_page(saldi: dict | None, coerenza_html: str = "") -> str:
    """
    Pagina dedicata "Saldi": la stessa card che compare in cima alla
    home, ma raggiungibile dal menu senza passare da li' — utile mentre
    si e' gia' dentro Fatture o Spese e si vuole solo controllare quanto
    c'e' sui conti, senza perdere il punto in cui si era. In piu' — dove
    la card di home resta compatta — una riga di KPI di dettaglio per
    ciascun conto: qui c'e' spazio per vederli come tessere, non solo
    come righe di un elenco.

    `saldi` ha la stessa forma usata da render_launchpad: dict opzionale
    con chiavi piva/personale/revolut (ciascuna dal rispettivo saldo_*()).
    `coerenza_html` e' gia' pronto (spese.revolut._riquadro_coerenza):
    il confronto fra risparmio dichiarato e reale, se Revolut e' collegato.
    """
    if not saldi:
        corpo = '<div class="empty">Saldi non disponibili.</div>'
    else:
        blocchi = [_blocco_saldi(saldi)]
        piva = saldi.get("piva") or {}
        pers = saldi.get("personale") or {}
        rev = saldi.get("revolut") or {}

        if piva.get("disponibile"):
            blocchi.append('<div class="eyebrow mt-4 mb-2">WeBank P.IVA</div>')
            blocchi.append(_kpi_conto(piva, "piva"))
        if pers.get("disponibile"):
            blocchi.append('<div class="eyebrow mt-4 mb-2">WeBank Personale</div>')
            blocchi.append(_kpi_conto(pers, "personale"))
        if rev.get("disponibile"):
            blocchi.append('<div class="eyebrow mt-4 mb-2">Revolut</div>')
            blocchi.append(_kpi_conto(rev, "revolut"))
            if coerenza_html:
                blocchi.append(coerenza_html)

        corpo = "\n".join(blocchi)

    return render_page(
        section="saldi",
        eyebrow="I tuoi conti",
        title_html='<em>Saldi</em>',
        content=corpo,
        breadcrumb=[("Saldi", "")],
    )


_BIO_SCRIPT = r"""
<script>
// Banner "sblocco veloce": proposto solo a sessione gia' sbloccata, se il
// device ha un platform authenticator e non ci sono ancora credenziali.
(async () => {
  const banner  = document.getElementById('bioBanner');
  const btnGo   = document.getElementById('bioBannerBtn');
  const btnSkip = document.getElementById('bioBannerDecline');
  if (!banner) return;

  try {
    if (localStorage.getItem('b2f-biometric-declined')) return;
    if (!window.PublicKeyCredential
        || !window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) return;

    const status = await fetch('/api/status', {credentials:'same-origin'})
      .then(r => r.ok ? r.json() : null);
    if (!status || (status.needs_pin && !status.unlocked)) return;

    const [wa, avail] = await Promise.all([
      fetch('/api/webauthn/status', {credentials:'same-origin'}).then(r => r.ok ? r.json() : null),
      PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(),
    ]);
    if (!wa || wa.credentials_count > 0 || !avail) return;
    banner.style.display = 'flex';
  } catch (e) { return; }

  btnSkip.addEventListener('click', () => {
    localStorage.setItem('b2f-biometric-declined', '1');
    banner.style.display = 'none';
  });

  btnGo.addEventListener('click', async () => {
    btnGo.disabled = true;
    try {
      const beginRes = await fetch('/api/webauthn/register/begin', {
        method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({device_name: navigator.userAgentData?.platform
                              || navigator.platform || 'Telefono'})});
      if (!beginRes.ok) throw new Error('begin failed');
      const options = await beginRes.json();
      options.challenge = b2fBase64urlToBuffer(options.challenge);
      options.user.id = b2fBase64urlToBuffer(options.user.id);
      if (options.excludeCredentials) {
        options.excludeCredentials = options.excludeCredentials.map(c => ({
          ...c, id: b2fBase64urlToBuffer(c.id)}));
      }
      const cred = await navigator.credentials.create({publicKey: options});
      const payload = {
        id: cred.id, rawId: b2fBufferToBase64url(cred.rawId), type: cred.type,
        response: {
          clientDataJSON: b2fBufferToBase64url(cred.response.clientDataJSON),
          attestationObject: b2fBufferToBase64url(cred.response.attestationObject),
          transports: cred.response.getTransports ? cred.response.getTransports() : [],
        }};
      const completeRes = await fetch('/api/webauthn/register/complete', {
        method:'POST', headers:{'Content-Type':'application/json'},
        credentials:'same-origin', body: JSON.stringify({credential: payload})});
      if (!completeRes.ok) throw new Error('complete failed');
      banner.querySelector('span').textContent = 'Impronta salvata';
      setTimeout(() => { banner.style.display = 'none'; }, 1800);
    } catch (e) {
      banner.querySelector('span').textContent = 'Configurazione non riuscita, riprova più tardi';
    } finally {
      btnGo.disabled = false;
    }
  });
})();
</script>
"""
