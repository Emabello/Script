"""
fatture/editor.py — Editor nuova fattura.

Adatta la logica del fatturatore.html originale:
  - Emittente prelevato da b2f_emittente
  - Clienti prelevati da b2f_clienti (picker)
  - Numerazione da b2f_next_progressivo
  - Salvataggio POST /fatture/api/fatture
  - PDF client-side con jsPDF (immutato dall'originale)

Rotta HTML:
  GET /fatture/nuova
"""
from datetime import date

from flask import Response

from . import fatture_bp
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured


@fatture_bp.get("/nuova")
def fattura_nuova():
    if not is_configured():
        content = '<div class="notice warn">Supabase non configurato.</div>'
        return _render(content)

    # Preleva emittente per precompilare
    sb = get_client()
    try:
        em = (sb.table("b2f_emittente")
                .select("*").eq("id", 1).single().execute()).data or {}
    except Exception:
        em = {}

    emj = _emittente_to_json(em)
    today = date.today().isoformat()

    content = _EDITOR_HTML.replace("__EMITTENTE_JSON__", emj) \
                          .replace("__TODAY__", today)

    return _render(content)


def _emittente_to_json(em: dict) -> str:
    """Genera JS object literal per l'emittente."""
    import json
    d = {
        "nome":         em.get("nome") or "",
        "cognome":      em.get("cognome") or "",
        "denominazione": em.get("denominazione") or "",
        "piva":         em.get("piva") or "",
        "cf":           em.get("cf") or "",
        "regime_fisc":  em.get("regime_fisc") or "RF19",
        "indirizzo":    em.get("indirizzo") or "",
        "cap":          em.get("cap") or "",
        "comune":       em.get("comune") or "",
        "provincia":    em.get("provincia") or "",
        "nazione":      em.get("nazione") or "IT",
        "email":        em.get("email") or "",
        "pec":          em.get("pec") or "",
        "iban":         em.get("iban") or "",
        "cassa_prev":   em.get("cassa_prev") or "",
        "aliquota_cassa": float(em.get("aliquota_cassa") or 0),
    }
    return json.dumps(d, ensure_ascii=False)


def _render(content: str) -> Response:
    html = render_page(
        section="fatture", eyebrow="Nuova fattura",
        title_html='<em>Nuova</em> fattura', content=content,
        breadcrumb=[("Fatture", "/fatture"), ("Nuova", "")],
    )
    return Response(html, mimetype="text/html")


# ---------------------------------------------------------------------------
# HTML dell'editor.
# CSS ereditato dal theme (form/card/btn/notice) — solo micro-tweak locale.
# JS: righe dinamiche, calcolo totale con INPS 4% opz e bollo €2, POST server.
# jsPDF caricato via CDN, come nel fatturatore originale.
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

<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script>
// ==============================================================
// Emittente iniettato dal server (b2f_emittente)
// ==============================================================
const EMITTENTE = __EMITTENTE_JSON__;

// ==============================================================
// Utility
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
    iban: EMITTENTE.iban || null,
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
// PDF — Layout stile proforma Meme (monocromatico, professionale)
// ==============================================================

// Format numero con virgola decimale e separatore migliaia italiano
function fmtNum(n) {
  return Number(n || 0).toLocaleString('it-IT',
    {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function onPDF() {
  const err = validate();
  if (err) { toast(err, 'err'); return; }
  const c = currentCliente();
  const t = calc();
  const dataIso = $('d_data').value || todayISO();
  const annoDoc = new Date(dataIso).getFullYear();

  // Numero display: solo progressivo (anno implicito dalla data)
  let numDisplay;
  const userNum = ($('d_num').value || '').trim();
  if (userNum) {
    // se contiene YYYY/NNN o NNN/YYYY, estrai la parte non-anno
    const m = userNum.match(/^(\d+)\s*[\/\-\.]\s*(\d+)$/);
    numDisplay = m ? String(parseInt(m[0].length === 4 ? m[2] : m[1], 10) || m[0]) : userNum;
  } else {
    numDisplay = CURRENT_PROG ? String(CURRENT_PROG) : '---';
  }

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({unit: 'mm', format: 'a4'});
  const W = 210, H = 297, M = 18;

  // Iniziali per il box EB
  const nomeCompleto = EMITTENTE.denominazione ||
    `${EMITTENTE.nome || ''} ${EMITTENTE.cognome || ''}`.trim() || 'B2F';
  const initials = nomeCompleto.split(/\s+/).filter(Boolean).slice(0, 2)
    .map(p => p[0]).join('').toUpperCase() || 'EB';

  // Palette
  const INK = [20, 23, 28];       // #14171C
  const MUTED = [115, 120, 130];
  const LINE = [220, 218, 210];
  const FAINT = [175, 178, 187];

  // ============ HEADER ============
  const headerY = M;

  // Box iniziali a sinistra
  doc.setFillColor(INK[0], INK[1], INK[2]);
  doc.rect(M, headerY, 22, 22, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.text(initials, M + 11, headerY + 14, {align: 'center'});

  // Info emittente a destra
  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(12);
  doc.text(nomeCompleto, W - M, headerY + 5, {align: 'right'});

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8.5);
  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  let hy = headerY + 10;

  const ids = [];
  if (EMITTENTE.piva) ids.push('P.IVA ' + EMITTENTE.piva);
  if (EMITTENTE.cf) ids.push('C.F. ' + EMITTENTE.cf);
  if (ids.length) { doc.text(ids.join(' · '), W - M, hy, {align: 'right'}); hy += 4; }

  const addrBits = [];
  if (EMITTENTE.indirizzo) addrBits.push(EMITTENTE.indirizzo);
  const cityStr = [EMITTENTE.cap, EMITTENTE.comune].filter(Boolean).join(' ');
  const cityFull = cityStr + (EMITTENTE.provincia ? ' (' + EMITTENTE.provincia + ')' : '');
  if (cityFull.trim()) addrBits.push(cityFull.trim());
  if (addrBits.length) { doc.text(addrBits.join(' — '), W - M, hy, {align: 'right'}); hy += 4; }

  const contact = [];
  if (EMITTENTE.email) contact.push(EMITTENTE.email);
  if (EMITTENTE.pec) contact.push('PEC ' + EMITTENTE.pec);
  if (contact.length) { doc.text(contact.join(' · '), W - M, hy, {align: 'right'}); hy += 4; }

  // ============ TITOLO DOCUMENTO ============
  let y = Math.max(hy, headerY + 22) + 12;
  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  doc.text('FATTURA', W - M, y, {align: 'right'});
  y += 5;
  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.text(`n. ${numDisplay} · ${itDate(dataIso)}`, W - M, y, {align: 'right'});

  // ============ DESTINATARIO ============
  y += 14;
  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8.5);
  doc.text('DESTINATARIO', M, y);
  y += 5;

  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.text(clienteLabel(c), M, y);
  y += 5;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  const cIds = [];
  if (c.piva) cIds.push('P.IVA ' + c.piva);
  if (c.cf) cIds.push('C.F. ' + c.cf);
  if (cIds.length) { doc.text(cIds.join(' · '), M, y); y += 4; }

  const cAddrBits = [];
  if (c.indirizzo) cAddrBits.push(c.indirizzo);
  const cCity = ([c.cap, c.comune].filter(Boolean).join(' ') +
    (c.provincia ? ' (' + c.provincia + ')' : '')).trim();
  if (cCity) cAddrBits.push(cCity);
  if (cAddrBits.length) { doc.text(cAddrBits.join(' — '), M, y); y += 4; }

  // ============ TABELLA RIGHE ============
  y += 8;
  const colDesc   = M;
  const colQta    = 128;
  const colPrezzo = 158;
  const colImp    = W - M;
  const descMax   = colQta - colDesc - 6;

  doc.setDrawColor(LINE[0], LINE[1], LINE[2]);
  doc.setLineWidth(0.4);
  doc.line(M, y, W - M, y);
  y += 5;

  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7.5);
  doc.text('DESCRIZIONE',  colDesc, y);
  doc.text('Q.TÀ',          colQta, y, {align: 'right'});
  doc.text('PREZZO €',      colPrezzo, y, {align: 'right'});
  doc.text('IMPORTO €',     colImp, y, {align: 'right'});
  y += 3;
  doc.line(M, y, W - M, y);
  y += 6;

  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);

  righe.forEach(r => {
    const q = Number(r.qta) || 0;
    const p = Number(r.prezzo) || 0;
    if (q === 0 || p === 0) return;
    const tot = r2(q * p);
    const descLines = doc.splitTextToSize(r.desc || '', descMax);
    doc.text(descLines, colDesc, y);
    const qtaText = String(r.qta) + (r.um ? ' ' + r.um : '');
    doc.text(qtaText, colQta, y, {align: 'right'});
    doc.text(fmtNum(p), colPrezzo, y, {align: 'right'});
    doc.text(fmtNum(tot), colImp, y, {align: 'right'});
    y += Math.max(6, descLines.length * 4.6);
    if (y > 245) { doc.addPage(); y = M; }
  });

  y += 3;
  doc.setDrawColor(LINE[0], LINE[1], LINE[2]);
  doc.line(M, y, W - M, y);
  y += 10;

  // ============ TOTALI ============
  const totLabelX = W - M - 55;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  doc.text('Imponibile', totLabelX, y, {align: 'right'});
  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.text(fmtNum(t.imponibile) + ' €', W - M, y, {align: 'right'});
  y += 6;

  if (t.cassa > 0) {
    doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
    doc.text('Cassa 4%', totLabelX, y, {align: 'right'});
    doc.setTextColor(INK[0], INK[1], INK[2]);
    doc.text(fmtNum(t.cassa) + ' €', W - M, y, {align: 'right'});
    y += 6;
  }
  if (t.bolloAdd > 0) {
    doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
    doc.text('Bollo', totLabelX, y, {align: 'right'});
    doc.setTextColor(INK[0], INK[1], INK[2]);
    doc.text(fmtNum(t.bolloAdd) + ' €', W - M, y, {align: 'right'});
    y += 6;
  }

  // Riga separazione totale
  y += 2;
  doc.setDrawColor(INK[0], INK[1], INK[2]);
  doc.setLineWidth(0.5);
  doc.line(W - M - 70, y, W - M, y);
  y += 7;

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(12);
  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.text('TOTALE A PAGARE', totLabelX, y, {align: 'right'});
  doc.text(fmtNum(t.totale) + ' €', W - M, y, {align: 'right'});

  // ============ PAGAMENTO ============
  y += 14;
  doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8.5);
  doc.text('PAGAMENTO', M, y);
  y += 5;

  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  const modo = ($('p_mod').value || '').trim() || 'Bonifico bancario';
  doc.text(modo, M, y);
  y += 5;

  if (EMITTENTE.iban) {
    doc.setFontSize(9);
    doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
    doc.text('IBAN ' + EMITTENTE.iban, M, y);
    y += 5;
  }
  const scad = $('p_scad').value;
  if (scad) {
    doc.setFontSize(9);
    doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
    doc.text('Scadenza: ' + itDate(scad), M, y);
    y += 5;
  }
  const cond = ($('p_cond').value || '').trim();
  if (cond) {
    doc.setFontSize(9);
    doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
    doc.text(cond, M, y);
    y += 5;
  }

  // ============ NOTE FISCALI ============
  y += 8;
  doc.setDrawColor(LINE[0], LINE[1], LINE[2]);
  doc.setLineWidth(0.3);
  doc.line(M, y - 3, W - M, y - 3);

  doc.setTextColor(INK[0], INK[1], INK[2]);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);

  const notes = [
    "Operazione senza applicazione dell'IVA ex art. 1, c. 54-89, L. 190/2014 - regime forfettario.",
    "Compenso non soggetto a ritenuta d'acconto ex art. 1, c. 67, L. 190/2014.",
  ];
  if (t.bolloDovuto) {
    const bolloLine = t.bolloAdd > 0
      ? "Imposta di bollo di € 2,00 assolta virtualmente ai sensi del D.M. 17/06/2014 (addebitata al cliente)."
      : "Imposta di bollo di € 2,00 assolta virtualmente ai sensi del D.M. 17/06/2014.";
    notes.push(bolloLine);
  }
  notes.forEach(n => {
    const wrapped = doc.splitTextToSize(n, W - 2 * M);
    doc.text(wrapped, M, y);
    y += wrapped.length * 4;
  });

  // ============ FOOTER ============
  const footerY = H - 12;
  doc.setFontSize(7.5);
  doc.setTextColor(FAINT[0], FAINT[1], FAINT[2]);
  const footerBits = [nomeCompleto];
  if (EMITTENTE.piva) footerBits.push('P.IVA ' + EMITTENTE.piva);
  if (EMITTENTE.email) footerBits.push(EMITTENTE.email);
  doc.text(footerBits.join(' · '), W / 2, footerY, {align: 'center'});

  // ============ SALVA ============
  const fname = `Fattura_${numDisplay}_${annoDoc}.pdf`.replace(/[\/\s]+/g, '-');
  doc.save(fname);
  toast('PDF generato', 'ok');
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
