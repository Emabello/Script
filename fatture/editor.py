"""
fatture/editor.py — Editor nuova fattura.

Il PDF viene generato dalla funzione condivisa window.b2fRenderInvoicePDF
definita in shared/pdfgen.py — stessa logica usata per la ristampa
dallo storico. Layout fedele al fatturatore.html originale ma senza
codici SDI e senza disclaimer proforma.
"""
from datetime import date

from flask import Response

from . import fatture_bp
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured
from shared.pdfgen import pdf_script


@fatture_bp.get("/nuova")
def fattura_nuova():
    if not is_configured():
        content = '<div class="notice warn">Supabase non configurato.</div>'
        return _render(content)

    # Preleva emittente per il picker + iniezione JS
    sb = get_client()
    try:
        em = (sb.table("b2f_emittente")
                .select("*").eq("id", 1).single().execute()).data or {}
    except Exception:
        em = {}

    today = date.today().isoformat()
    pdf_js = pdf_script(em)

    content = _EDITOR_HTML.replace("__TODAY__", today) \
                          .replace("__PDF_SCRIPT__", pdf_js)

    return _render(content)


def _render(content: str) -> Response:
    html = render_page(
        section="fatture", eyebrow="Nuova fattura",
        title_html='<em>Nuova</em> fattura', content=content,
        breadcrumb=[("Fatture", "/fatture"), ("Nuova", "")],
    )
    return Response(html, mimetype="text/html")


# ---------------------------------------------------------------------------
# HTML dell'editor. Il PDF e' delegato a b2fRenderInvoicePDF (pdfgen.py).
# ---------------------------------------------------------------------------

_EDITOR_HTML = r"""
<style>
.riga{display:grid;grid-template-columns:1fr 54px 46px 82px 34px;gap:6px;
  padding:10px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;
  background:var(--input-bg)}
.riga input{width:100%;padding:8px 10px;border-radius:8px;
  background:transparent;border:1px solid var(--line);color:var(--ink);
  font-family:inherit;font-size:14px;min-height:38px}
.riga .desc{grid-column:1/-1}
.riga input:focus{outline:none;border-color:var(--gold)}
.riga .qta,.riga .prezzo{text-align:right;font-variant-numeric:tabular-nums}
.riga .um{text-align:center;text-transform:lowercase;font-size:12.5px;color:var(--muted)}
.riga .btn-x{padding:0;background:transparent;border:none;color:var(--faint);
  font-size:18px;cursor:pointer;display:grid;place-items:center;border-radius:8px;
  transition:.15s;min-height:38px}
.riga .btn-x:hover{color:var(--danger);background:rgba(255,107,129,.1)}
.tot-row{display:flex;justify-content:space-between;padding:6px 4px;font-size:13.5px}
.tot-row.big{font-size:17px;font-weight:600;padding-top:10px;margin-top:8px;
  border-top:1px solid var(--line)}
.tot-row .lbl{color:var(--muted)}
.tot-row .val{font-variant-numeric:tabular-nums}
.tot-row.big .val{color:var(--gold)}
.check-row{display:flex;align-items:center;gap:10px;padding:8px 0;font-size:13.5px}
.check-row input[type=checkbox]{width:18px;height:18px;accent-color:var(--gold)}
.pill-count{background:var(--card-grad);border:1px solid var(--line-strong);
  padding:6px 12px;border-radius:999px;font-size:12.5px;color:var(--ink-dim);
  display:inline-flex;align-items:center;gap:6px}
.pill-count .tnum{color:var(--gold);font-weight:600}
</style>

<div class="card">
  <div class="eyebrow" style="margin-bottom:8px">Documento</div>
  <div class="field-group">
    <div class="field">
      <label>Numero</label>
      <input id="d_num" placeholder="Auto"
             onchange="onNumeroChange()">
      <div class="hint">Vuoto = usa prossimo progressivo dall'anno</div>
    </div>
    <div class="field">
      <label>Data</label>
      <input id="d_data" type="date" value="__TODAY__">
    </div>
  </div>
  <div class="field-group">
    <div class="field">
      <label>Tipo documento</label>
      <select id="d_tipo">
        <option value="TD01" selected>TD01 — Fattura</option>
        <option value="TD04">TD04 — Nota di credito</option>
        <option value="TD06">TD06 — Parcella</option>
      </select>
    </div>
    <div class="field">
      <label>Divisa</label>
      <input id="d_div" value="EUR" maxlength="3" style="text-transform:uppercase">
    </div>
  </div>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div class="eyebrow">Cliente</div>
    <a href="/fatture/clienti/nuovo" style="font-size:12.5px;color:var(--gold);
       text-decoration:none">+ nuovo</a>
  </div>
  <div class="field">
    <label>Seleziona cliente</label>
    <select id="c_pick" onchange="loadCliente()">
      <option value="">— seleziona —</option>
    </select>
  </div>
  <div id="c_summary" style="color:var(--muted);font-size:13px;line-height:1.5"></div>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <div class="eyebrow">Righe</div>
    <span class="pill-count"><span class="tnum" id="n_righe">0</span> righe</span>
  </div>
  <div id="righe"></div>
  <button type="button" class="btn ghost" onclick="addRiga()" style="width:100%;margin-top:4px">
    + Aggiungi riga
  </button>
</div>

<div class="card">
  <div class="eyebrow" style="margin-bottom:8px">Contributi & bollo</div>
  <div class="check-row">
    <input type="checkbox" id="o_inps">
    <label for="o_inps">Addebita cassa prev. 4% (INPS Gest. Sep.)</label>
  </div>
  <div class="check-row">
    <input type="checkbox" id="o_bollo_add" checked>
    <label for="o_bollo_add">Addebita bollo € 2,00 se dovuto (imponibile &gt; € 77,47)</label>
  </div>
</div>

<div class="card">
  <div class="eyebrow" style="margin-bottom:8px">Totali</div>
  <div id="totali"></div>
</div>

<div class="card">
  <div class="eyebrow" style="margin-bottom:8px">Pagamento</div>
  <div class="field">
    <label>Modalità</label>
    <input id="p_mod" placeholder="Bonifico bancario">
  </div>
  <div class="field-group">
    <div class="field">
      <label>Condizioni</label>
      <input id="p_cond" placeholder="30 gg data fattura">
    </div>
    <div class="field">
      <label>Scadenza</label>
      <input id="p_scad" type="date">
    </div>
  </div>
</div>

<div class="actions" style="margin-top:14px">
  <button type="button" class="btn" onclick="onSalva()">Salva fattura</button>
  <button type="button" class="btn ghost" onclick="onPDF()">Anteprima PDF</button>
</div>

<div id="toast" class="toast"></div>

__PDF_SCRIPT__
<script>
// ==============================================================
// Utility (l'oggetto EMITTENTE è disponibile globalmente via pdfgen)
// ==============================================================
const $ = id => document.getElementById(id);
const r2 = n => Math.round((Number(n)+Number.EPSILON)*100)/100;
const eur = n => (r2(n)).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
const xnum = n => (r2(n)).toFixed(2);
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const todayISO = () => new Date().toISOString().slice(0,10);
function itDate(iso){ if(!iso) return ''; const [y,m,d]=iso.split('-'); return `${d}/${m}/${y}`; }

function toast(msg, cls) {
  const t = $('toast'); t.textContent = msg; t.className = 'toast show ' + (cls || '');
  setTimeout(()=>{t.className='toast '+(cls||'')}, cls==='err' ? 4500 : 2500);
}

// ==============================================================
// Numerazione (chiamata al server)
// ==============================================================
let CURRENT_ANNO = null, CURRENT_PROG = null;

async function loadProgressivo() {
  const y = new Date($('d_data').value || todayISO()).getFullYear();
  try {
    const r = await fetch('/fatture/api/next_progressivo?anno=' + y);
    if (!r.ok) throw new Error('no');
    const j = await r.json();
    CURRENT_ANNO = j.anno; CURRENT_PROG = j.progressivo;
    $('d_num').placeholder = j.numero + ' (auto)';
    if (!$('d_num').value) $('d_num').value = '';
  } catch (e) {
    $('d_num').placeholder = 'errore progressivo';
  }
}
function onNumeroChange() {
  // Se l'utente scrive un numero manuale nel formato YYYY/NNN, lo prendiamo
  const v = ($('d_num').value || '').trim();
  const m = v.match(/^(\d{4})[\/\-\.](\d+)$/);
  if (m) { CURRENT_ANNO = +m[1]; CURRENT_PROG = +m[2]; }
}

// ==============================================================
// Clienti (fetch da /fatture/api/clienti)
// ==============================================================
let CLIENTI = [];
async function loadClienti() {
  try {
    // /api/clienti non esiste come GET list -> usiamo direttamente Supabase-side via /fatture/api/clienti-list
    // ma per non aggiungere una rotta in piu' facciamo il fetch di una lista via storico API? No.
    // Semplifichiamo: aggiungiamo qui una richiesta al PICKER endpoint
    const r = await fetch('/fatture/api/clienti-picker');
    if (!r.ok) throw new Error('picker');
    CLIENTI = await r.json();
    const sel = $('c_pick');
    sel.innerHTML = '<option value="">— seleziona —</option>' +
      CLIENTI.map(c => `<option value="${c.id}">${esc(clienteLabel(c))}</option>`).join('');
  } catch (e) {
    console.warn('clienti load failed', e);
  }
}
function clienteLabel(c) {
  return (c.tipo === 'privato')
    ? `${c.nome || ''} ${c.cognome || ''}`.trim() || '(privato)'
    : (c.denominazione || '(azienda)');
}
function currentCliente() {
  const id = $('c_pick').value;
  return CLIENTI.find(c => String(c.id) === String(id)) || null;
}
function loadCliente() {
  const c = currentCliente();
  const box = $('c_summary');
  if (!c) { box.innerHTML = ''; return; }
  const lines = [];
  lines.push(`<strong style="color:var(--ink)">${esc(clienteLabel(c))}</strong>`);
  const idl = [];
  if (c.piva) idl.push('P.IVA ' + esc(c.piva));
  if (c.cf) idl.push('CF ' + esc(c.cf));
  if (idl.length) lines.push(idl.join(' · '));
  const addr = [c.indirizzo, [c.cap, c.comune].filter(Boolean).join(' ') +
                (c.provincia ? ' (' + c.provincia + ')' : '')].filter(x => x && x.trim());
  if (addr.length) lines.push(esc(addr.join(', ')));
  if (c.sdi) lines.push('SDI: ' + esc(c.sdi));
  if (c.pec) lines.push('PEC: ' + esc(c.pec));
  box.innerHTML = lines.join('<br>');
}

// ==============================================================
// Righe
// ==============================================================
let righe = [];
function addRiga(desc="", qta=1, prezzo="", um="") {
  righe.push({desc, qta, prezzo, um});
  renderRighe(); recalc();
}
function renderRighe() {
  const wrap = $('righe');
  wrap.innerHTML = '';
  righe.forEach((r, i) => {
    const el = document.createElement('div'); el.className = 'riga';
    el.innerHTML = `
      <input class="desc" placeholder="Descrizione" value="${esc(r.desc)}"
             oninput="upd(${i},'desc',this.value)">
      <input class="qta" type="number" step="0.01" min="0" placeholder="Q.tà"
             value="${r.qta}" oninput="upd(${i},'qta',this.value)">
      <input class="um" placeholder="um" maxlength="6"
             value="${esc(r.um || '')}" oninput="upd(${i},'um',this.value)">
      <input class="prezzo" type="number" step="0.01" min="0" placeholder="Prezzo"
             value="${r.prezzo}" oninput="upd(${i},'prezzo',this.value)">
      <button type="button" class="btn-x" onclick="delRiga(${i})">✕</button>
    `;
    wrap.appendChild(el);
  });
  $('n_righe').textContent = righe.length;
}
function upd(i, k, v) { righe[i][k] = v; recalc(); }
function delRiga(i) {
  righe.splice(i, 1);
  if (righe.length === 0) righe.push({desc:"", qta:1, prezzo:""});
  renderRighe(); recalc();
}

function calc() {
  const base = righe.reduce((s, r) => s + (Number(r.qta) || 0) * (Number(r.prezzo) || 0), 0);
  const inpsOn = $('o_inps').checked;
  const cassa = inpsOn ? r2(base * 0.04) : 0;
  const imponibile = r2(base + cassa);
  const bolloDovuto = imponibile > 77.47;
  const bolloAdd = (bolloDovuto && $('o_bollo_add').checked) ? 2.00 : 0;
  const totale = r2(imponibile + bolloAdd);
  return {base, cassa, cassa_perc: inpsOn ? 4 : 0, imponibile, bolloDovuto, bolloAdd, totale};
}
function recalc() {
  const t = calc();
  $('totali').innerHTML = `
    <div class="tot-row"><span class="lbl">Base imponibile</span>
      <span class="val tnum">${eur(t.base)}</span></div>
    ${t.cassa > 0 ? `<div class="tot-row"><span class="lbl">Cassa prev. 4%</span>
      <span class="val tnum">+${eur(t.cassa)}</span></div>` : ''}
    <div class="tot-row"><span class="lbl">Imponibile</span>
      <span class="val tnum">${eur(t.imponibile)}</span></div>
    ${t.bolloDovuto ? `<div class="tot-row"><span class="lbl">Bollo € 2,00 ${t.bolloAdd > 0 ? "(addebitato)" : "(a carico emittente)"}</span>
      <span class="val tnum">${t.bolloAdd > 0 ? '+'+eur(t.bolloAdd) : eur(0)}</span></div>` : ''}
    <div class="tot-row big"><span>Totale</span>
      <span class="val tnum">${eur(t.totale)}</span></div>
  `;
}

// ==============================================================
// Snapshot cliente + salvataggio
// ==============================================================
function clienteSnapshot(c) {
  if (!c) return null;
  return {
    tipo: c.tipo, denominazione: c.denominazione, nome: c.nome, cognome: c.cognome,
    piva: c.piva, cf: c.cf, indirizzo: c.indirizzo, cap: c.cap, comune: c.comune,
    provincia: c.provincia, nazione: c.nazione, sdi: c.sdi, pec: c.pec, email: c.email,
  };
}

function validate() {
  const c = currentCliente();
  if (!c) return 'Seleziona un cliente.';
  const nonZero = righe.some(r => (Number(r.qta) || 0) > 0 && (Number(r.prezzo) || 0) > 0);
  if (!nonZero) return 'Aggiungi almeno una riga con qta e prezzo.';
  return null;
}

async function onSalva() {
  const err = validate();
  if (err) { toast(err, 'err'); return; }
  const c = currentCliente();
  const t = calc();
  const dataIso = $('d_data').value || todayISO();
  const anno = new Date(dataIso).getFullYear();

  // Se l'utente non ha manualmente cambiato numero, prendiamo il progressivo
  // corrente. Altrimenti onNumeroChange l'ha gia' impostato.
  if (!CURRENT_PROG || CURRENT_ANNO !== anno) {
    // ricarica progressivo se anno cambiato
    try {
      const r = await fetch('/fatture/api/next_progressivo?anno=' + anno);
      const j = await r.json();
      CURRENT_ANNO = j.anno; CURRENT_PROG = j.progressivo;
    } catch (e) {}
  }

  const payload = {
    anno, progressivo: CURRENT_PROG,
    data: dataIso,
    tipo_doc: $('d_tipo').value || 'TD01',
    cliente_id: c.id,
    cliente_snapshot: clienteSnapshot(c),
    righe: righe.filter(r => (Number(r.qta) || 0) > 0 && (Number(r.prezzo) || 0) > 0)
                .map(r => ({descrizione: r.desc, qta: Number(r.qta), um: r.um || null,
                            prezzo: Number(r.prezzo),
                            tot: r2(Number(r.qta) * Number(r.prezzo))})),
    imponibile: t.imponibile,
    bollo: t.bolloAdd || (t.bolloDovuto ? 2.00 : 0),
    bollo_addebitato: t.bolloAdd > 0,
    cassa_perc: t.cassa_perc,
    cassa_importo: t.cassa,
    totale: t.totale,
    divisa: ($('d_div').value || 'EUR').toUpperCase(),
    pagamento_mod: $('p_mod').value || null,
    pagamento_cond: $('p_cond').value || null,
    scadenza: $('p_scad').value || null,
    iban: (window.B2F_EMITTENTE && window.B2F_EMITTENTE.iban) || null,
    stato: 'emessa',
  };

  try {
    const r = await fetch('/fatture/api/fatture', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const j = await r.json();
    if (!r.ok) { toast(j.error || 'Errore salvataggio', 'err'); return; }
    toast('Fattura ' + (j.numero || '') + ' salvata', 'ok');
    setTimeout(()=>{ location.href = '/fatture/' + j.id; }, 700);
  } catch (e) {
    toast('Errore rete: ' + e.message, 'err');
  }
}

// ==============================================================
// PDF — Delegato a window.b2fRenderInvoicePDF (shared/pdfgen.py)
// ==============================================================
function buildPdfPayload() {
  const c = currentCliente();
  const t = calc();
  const dataIso = $('d_data').value || todayISO();
  // Numero display: solo progressivo (anno implicito dalla data)
  let numDisplay;
  const userNum = ($('d_num').value || '').trim();
  if (userNum) {
    const m = userNum.match(/^(\d+)\s*[\/\-\.]\s*(\d+)$/);
    numDisplay = m ? String(parseInt(m[1].length === 4 ? m[2] : m[1], 10)) : userNum;
  } else {
    numDisplay = CURRENT_PROG ? String(CURRENT_PROG) : '---';
  }
  return {
    numero_display: numDisplay,
    data_iso: dataIso,
    tipo_doc: $('d_tipo').value || 'TD01',
    cliente: c ? {
      tipo: c.tipo, denominazione: c.denominazione,
      nome: c.nome, cognome: c.cognome,
      piva: c.piva, cf: c.cf,
      indirizzo: c.indirizzo, cap: c.cap, comune: c.comune, provincia: c.provincia,
    } : {},
    righe: righe.filter(r => (Number(r.qta) || 0) > 0 && (Number(r.prezzo) || 0) > 0)
                .map(r => ({descrizione: r.desc, qta: Number(r.qta),
                            um: r.um || null, prezzo: Number(r.prezzo)})),
    imponibile: t.imponibile,
    cassa_perc: t.cassa_perc,
    cassa_importo: t.cassa,
    bollo_add: t.bolloAdd > 0,
    bollo_dovuto: !!t.bolloDovuto,
    totale: t.totale,
    pagamento_mod: $('p_mod').value || 'Bonifico bancario',
    scadenza: $('p_scad').value || null,
  };
}

function onPDF() {
  const err = validate();
  if (err) { toast(err, 'err'); return; }
  const ok = window.b2fRenderInvoicePDF(buildPdfPayload());
  if (ok) toast('PDF generato', 'ok');
}

// ==============================================================
// Bootstrap
// ==============================================================
(async () => {
  addRiga();
  await loadClienti();
  await loadProgressivo();
  $('d_data').addEventListener('change', loadProgressivo);
  recalc();
})();
</script>
"""
