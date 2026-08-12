"""
fatture/editor.py — Compilazione e modifica del facsimile di fattura.

Il documento prodotto qui non e' la fattura elettronica: e' il facsimile
che viene mandato allo studio, che poi predispone e trasmette l'XML allo
SDI. Per questo si nasce in bozza e si diventa "inviata allo studio" solo
con un'azione esplicita.

Rotte:
  GET /fatture/nuova            -> nuovo documento
  GET /fatture/<int:fid>/modifica -> modifica, solo se ancora in bozza

Il PDF e' delegato a window.b2fRenderInvoicePDF (shared/pdfgen.py).
"""
import json
from datetime import date

from flask import Response, redirect

from . import fatture_bp
from .costanti import RIVALSA_PERC, modificabile, motivo_blocco, normalizza_stato
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured
from shared.pdfgen import pdf_script


def _contesto_comune(sb):
    """Emittente + quota di accantonamento, serve a entrambe le rotte."""
    try:
        em = (sb.table("b2f_emittente")
                .select("*").eq("id", 1).single().execute()).data or {}
    except Exception:
        em = {}

    # Quota da accantonare coi parametri fiscali correnti: serve per il
    # suggerimento dal vivo mentre si compila.
    try:
        from .fiscale import get_parametri
        from . import accantonamento as acc
        prova = acc.scomponi(1000.0, get_parametri(sb))
        acc_rate = prova["aliquote"][prova["scenario_preferito"]]
    except Exception:
        acc_rate = 0.0

    return em, acc_rate


def _render_editor(em, acc_rate, init: dict, titolo: str, eyebrow: str,
                   breadcrumb) -> Response:
    # __INIT__ si sostituisce per ultimo: il suo valore porta dentro testo
    # libero (numero, righe di una fattura esistente). Se un'altra
    # sostituzione girasse dopo, un valore che contenesse per caso il
    # testo letterale di un altro segnaposto (es. "__PDF_SCRIPT__" dentro
    # una descrizione) verrebbe espanso una seconda volta.
    content = (_EDITOR_HTML
               .replace("__ACC_RATE__", f"{acc_rate:.6f}")
               .replace("__RIVALSA_PERC__", f"{RIVALSA_PERC:g}")
               .replace("__PDF_SCRIPT__", pdf_script(em))
               # niente "<" nel blob: un cliente o una riga con "</script>"
               # dentro chiuderebbe il tag prima e inietterebbe markup.
               .replace("__INIT__", json.dumps(init, ensure_ascii=False)
                        .replace("<", "\\u003c")))
    html = render_page(section="fatture", eyebrow=eyebrow, title_html=titolo,
                       content=content, breadcrumb=breadcrumb)
    return Response(html, mimetype="text/html")


@fatture_bp.get("/nuova")
def fattura_nuova():
    if not is_configured():
        return Response(render_page(
            section="fatture", eyebrow="Nuova fattura",
            title_html='<em>Nuova</em> fattura',
            content='<div class="notice warn">Supabase non configurato.</div>',
        ), mimetype="text/html")

    sb = get_client()
    em, acc_rate = _contesto_comune(sb)
    init = {
        "modo": "nuova",
        "id": None,
        "data": date.today().isoformat(),
        "tipo_doc": "TD01",
        "divisa": "EUR",
        "numero": "",
        "cliente_id": None,
        "righe": [{"desc": "", "qta": 1, "prezzo": "", "um": ""}],
        "rivalsa": True,
        "bollo_add": True,
        "pagamento_mod": "",
        "pagamento_cond": "",
        "scadenza": "",
    }
    return _render_editor(em, acc_rate, init,
                          '<em>Nuova</em> fattura', "Nuova fattura",
                          [("Fatture", "/fatture"), ("Nuova", "")])


@fatture_bp.get("/<int:fid>/modifica")
def fattura_modifica(fid):
    """
    Modifica di una fattura, permessa solo finche' e' in bozza.

    Se non lo e', non si mostra un editor disabilitato: si torna al
    dettaglio, che e' il posto dove la spiegazione ha senso accanto allo
    stato e alle azioni disponibili.
    """
    if not is_configured():
        return redirect(f"/fatture/{fid}")

    sb = get_client()
    try:
        f = (sb.table("b2f_fatture").select("*")
               .eq("id", fid).single().execute()).data or {}
    except Exception:
        return redirect("/fatture/storico")

    stato = normalizza_stato(f.get("stato"))
    if not modificabile(stato):
        return redirect(f"/fatture/{fid}?bloccata=1")

    em, acc_rate = _contesto_comune(sb)
    righe = [{"desc": r.get("descrizione") or "", "qta": r.get("qta") or 1,
              "prezzo": r.get("prezzo") or "", "um": r.get("um") or ""}
             for r in (f.get("righe") or [])] or [
        {"desc": "", "qta": 1, "prezzo": "", "um": ""}]

    init = {
        "modo": "modifica",
        "id": fid,
        "data": f.get("data") or date.today().isoformat(),
        "tipo_doc": f.get("tipo_doc") or "TD01",
        "divisa": f.get("divisa") or "EUR",
        "numero": f.get("numero") or "",
        "cliente_id": f.get("cliente_id"),
        "righe": righe,
        "rivalsa": float(f.get("cassa_importo") or 0) > 0,
        "bollo_add": bool(f.get("bollo_addebitato")),
        "pagamento_mod": f.get("pagamento_mod") or "",
        "pagamento_cond": f.get("pagamento_cond") or "",
        "scadenza": f.get("scadenza") or "",
    }
    numero = f.get("numero") or str(fid)
    return _render_editor(
        em, acc_rate, init,
        f'Modifica <em>{numero}</em>', "Modifica fattura",
        [("Fatture", "/fatture"), ("Storico", "/fatture/storico"),
         (numero, f"/fatture/{fid}"), ("Modifica", "")])


# ---------------------------------------------------------------------------
# HTML dell'editor
# ---------------------------------------------------------------------------

_EDITOR_HTML = r"""
<style>
/* Due righe: descrizione a tutta larghezza, poi quantità · unità · prezzo ·
   elimina. Le quattro colonne descrivono la seconda riga. */
.riga{display:grid;grid-template-columns:minmax(0,1fr) 58px minmax(0,1.4fr) 40px;
  gap:6px;padding:10px;border:1px solid var(--line);border-radius:var(--r-sm);
  margin-bottom:var(--sp-2);background:var(--surface-3)}
.riga input{width:100%;padding:8px 10px;border-radius:var(--r-xs);
  background:var(--surface);border:1px solid var(--line);color:var(--ink);
  font-family:inherit;font-size:14px;min-height:40px}
.riga .desc{grid-column:1/-1}
.riga input:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft)}
.riga .qta,.riga .prezzo{text-align:right;font-variant-numeric:tabular-nums}
.riga .um{text-align:center;text-transform:lowercase;font-size:12.5px}
.riga .btn-x{color:var(--ink-4);font-size:17px;display:grid;place-items:center;
  border-radius:var(--r-xs);transition:color .15s,background-color .15s;min-height:40px}
.riga .btn-x:hover{color:var(--neg);background:var(--neg-soft)}
.tot-row{display:flex;justify-content:space-between;gap:12px;
  padding:7px 0;font-size:13.5px}
.tot-row.sub{padding:3px 0 3px 14px;font-size:12.5px;color:var(--ink-3)}
.tot-row.big{font-size:17px;font-weight:600;padding-top:11px;margin-top:var(--sp-2);
  border-top:1px solid var(--line)}
.tot-row .lbl{color:var(--ink-3)}
.tot-row.sub .lbl{color:var(--ink-4)}
.tot-row .val{font-variant-numeric:tabular-nums}
.tot-row.big .val{color:var(--accent-text)}
.pill-count{background:var(--surface-3);padding:5px 12px;border-radius:var(--r-full);
  font-size:12.5px;color:var(--ink-2);display:inline-flex;align-items:center;gap:5px}
.pill-count .tnum{font-weight:600}
</style>

<div class="narrow">
<div class="card">
  <div class="card-head"><div class="eyebrow">Documento</div></div>
  <div class="field-group">
    <div class="field">
      <label>Numero</label>
      <input id="d_num" placeholder="Auto" onchange="onNumeroChange()">
      <div class="hint">Vuoto = usa il prossimo progressivo dell'anno</div>
    </div>
    <div class="field">
      <label>Data</label>
      <input id="d_data" type="date">
    </div>
  </div>
  <div class="field-group">
    <div class="field">
      <label>Tipo documento</label>
      <select id="d_tipo">
        <option value="TD01">TD01 — Fattura</option>
        <option value="TD04">TD04 — Nota di credito</option>
        <option value="TD06">TD06 — Parcella</option>
      </select>
    </div>
    <div class="field">
      <label>Divisa</label>
      <input id="d_div" maxlength="3" style="text-transform:uppercase">
    </div>
  </div>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div class="eyebrow">Cliente</div>
    <a href="/fatture/clienti/nuovo" style="font-size:12.5px;color:var(--accent-text);
       text-decoration:none">+ nuovo</a>
  </div>
  <div class="field">
    <label>Seleziona cliente</label>
    <select id="c_pick" onchange="loadCliente()">
      <option value="">— seleziona —</option>
    </select>
  </div>
  <div id="c_summary" class="small muted" style="line-height:1.5"></div>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <div class="eyebrow">Righe</div>
    <span class="pill-count"><span class="tnum" id="n_righe">0</span>
      <span id="n_righe_lbl">righe</span></span>
  </div>
  <div id="righe"></div>
  <button type="button" class="btn ghost" onclick="addRiga()" style="width:100%;margin-top:4px">
    + Aggiungi riga
  </button>
  <div class="hint mt-2">
    I prezzi che scrivi sono quelli concordati col cliente: la rivalsa INPS
    viene ricavata da dentro, non aggiunta sopra.
  </div>
</div>

<div class="card">
  <div class="card-head"><div class="eyebrow">Rivalsa e bollo</div></div>
  <div class="field inline">
    <input type="checkbox" id="o_inps" onchange="recalc()">
    <label for="o_inps">Rivalsa INPS gestione separata __RIVALSA_PERC__ %
      (scorporata dal corrispettivo)</label>
  </div>
  <div class="field inline">
    <input type="checkbox" id="o_bollo_add" onchange="recalc()">
    <label for="o_bollo_add">Addebita bollo € 2,00 se dovuto (oltre € 77,47)</label>
  </div>
</div>

<div class="card">
  <div class="card-head"><div class="eyebrow">Totali</div></div>
  <div id="totali"></div>
  <div class="notice info small mt-3" id="accHint" style="display:none"></div>
</div>

<div class="card">
  <div class="card-head"><div class="eyebrow">Pagamento</div></div>
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

<div class="actions">
  <button type="button" class="btn" onclick="onSalva()" id="btnSalva">Salva</button>
  <button type="button" class="btn ghost" onclick="onPDF()">Anteprima facsimile</button>
</div>
<div id="azioniAnnulla" class="actions" style="display:none">
  <a class="btn ghost block" id="linkIndietro" href="#">Annulla e torna alla fattura</a>
</div>
</div>

<div id="toast" class="toast"></div>

__PDF_SCRIPT__
<script>
// ==============================================================
// Stato iniziale, dal server. Stessa struttura per nuova e modifica.
// ==============================================================
const INIT = __INIT__;
const ACC_RATE = __ACC_RATE__;        // quota consigliata da accantonare
const RIVALSA_PERC = __RIVALSA_PERC__; // 4

const $ = id => document.getElementById(id);
const r2 = n => Math.round((Number(n)+Number.EPSILON)*100)/100;
const eur = n => '€ ' + (r2(n)).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const todayISO = () => new Date().toISOString().slice(0,10);

function toast(msg, cls) {
  const t = $('toast'); t.textContent = msg; t.className = 'toast show ' + (cls || '');
  setTimeout(()=>{t.className='toast '+(cls||'')}, cls==='err' ? 4500 : 2500);
}

// ==============================================================
// Numerazione
// ==============================================================
let CURRENT_ANNO = null, CURRENT_PROG = null;

async function loadProgressivo() {
  // In modifica il numero e' gia' assegnato e non si tocca.
  if (INIT.modo === 'modifica') return;
  const y = new Date($('d_data').value || todayISO()).getFullYear();
  try {
    const r = await fetch('/fatture/api/next_progressivo?anno=' + y);
    if (!r.ok) throw new Error('no');
    const j = await r.json();
    CURRENT_ANNO = j.anno; CURRENT_PROG = j.progressivo;
    $('d_num').placeholder = j.numero + ' (auto)';
  } catch (e) {
    $('d_num').placeholder = 'errore progressivo';
  }
}
function onNumeroChange() {
  const v = ($('d_num').value || '').trim();
  const m = v.match(/^(\d{4})[\/\-\.](\d+)$/);
  if (m) { CURRENT_ANNO = +m[1]; CURRENT_PROG = +m[2]; }
}

// ==============================================================
// Clienti
// ==============================================================
let CLIENTI = [];
async function loadClienti() {
  try {
    const r = await fetch('/fatture/api/clienti-picker');
    if (!r.ok) throw new Error('picker');
    CLIENTI = await r.json();
    const sel = $('c_pick');
    sel.innerHTML = '<option value="">— seleziona —</option>' +
      CLIENTI.map(c => `<option value="${c.id}">${esc(clienteLabel(c))}</option>`).join('');
    if (INIT.cliente_id) sel.value = String(INIT.cliente_id);
    loadCliente();
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
  const lines = [`<strong style="color:var(--ink)">${esc(clienteLabel(c))}</strong>`];
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
      <input class="qta" type="number" step="0.01" min="0" inputmode="decimal"
             placeholder="Q.tà" aria-label="Quantità"
             value="${r.qta}" oninput="upd(${i},'qta',this.value)">
      <input class="um" placeholder="um" maxlength="6" aria-label="Unità di misura"
             value="${esc(r.um || '')}" oninput="upd(${i},'um',this.value)">
      <input class="prezzo" type="number" step="0.01" min="0" inputmode="decimal"
             placeholder="Prezzo" aria-label="Prezzo unitario"
             value="${r.prezzo}" oninput="upd(${i},'prezzo',this.value)">
      <button type="button" class="btn-x" onclick="delRiga(${i})"
              aria-label="Elimina riga">✕</button>
    `;
    wrap.appendChild(el);
  });
  $('n_righe').textContent = righe.length;
  $('n_righe_lbl').textContent = righe.length === 1 ? 'riga' : 'righe';
}
function upd(i, k, v) { righe[i][k] = v; recalc(); }
function delRiga(i) {
  righe.splice(i, 1);
  if (righe.length === 0) righe.push({desc:"", qta:1, prezzo:"", um:""});
  renderRighe(); recalc();
}

// ==============================================================
// Calcolo — SCORPORO, non addebito
// ==============================================================
// Accordo con lo studio: la rivalsa del 4 % si estrae dal corrispettivo
// concordato. Il totale che il cliente paga non cambia; e' il compenso a
// ridursi. La variante ad addebito (corrispettivo + 4 %) non esiste piu':
// produrrebbe un facsimile che non combacia con la fattura vera.
function calc() {
  const corrispettivo = r2(righe.reduce(
    (s, r) => s + (Number(r.qta) || 0) * (Number(r.prezzo) || 0), 0));
  const conRivalsa = $('o_inps').checked;
  const rivalsa = conRivalsa
    ? r2(corrispettivo - corrispettivo / (1 + RIVALSA_PERC / 100))
    : 0;
  const compenso = r2(corrispettivo - rivalsa);
  // Imponibile = compenso + rivalsa = corrispettivo. Nel forfettario non
  // c'è IVA, quindi è anche la base che concorre al fatturato.
  const imponibile = corrispettivo;
  const bolloDovuto = imponibile > 77.47;
  const bolloAdd = (bolloDovuto && $('o_bollo_add').checked) ? 2.00 : 0;
  const totale = r2(imponibile + bolloAdd);
  return {corrispettivo, compenso, rivalsa,
          rivalsa_perc: conRivalsa ? RIVALSA_PERC : 0,
          imponibile, bolloDovuto, bolloAdd, totale};
}

function recalc() {
  const t = calc();
  const righeScorporo = t.rivalsa > 0 ? `
    <div class="tot-row sub"><span class="lbl">di cui compenso</span>
      <span class="val tnum">${eur(t.compenso)}</span></div>
    <div class="tot-row sub"><span class="lbl">di cui rivalsa INPS ${RIVALSA_PERC} %</span>
      <span class="val tnum">${eur(t.rivalsa)}</span></div>` : '';

  $('totali').innerHTML = `
    <div class="tot-row"><span class="lbl">Corrispettivo concordato</span>
      <span class="val tnum">${eur(t.corrispettivo)}</span></div>
    ${righeScorporo}
    ${t.bolloDovuto ? `<div class="tot-row"><span class="lbl">Bollo € 2,00 ${
        t.bolloAdd > 0 ? "(addebitato)" : "(a tuo carico)"}</span>
      <span class="val tnum">${t.bolloAdd > 0 ? eur(t.bolloAdd) : eur(0)}</span></div>` : ''}
    <div class="tot-row big"><span>Totale a pagare</span>
      <span class="val tnum">${eur(t.totale)}</span></div>
  `;

  // Quanto andrà messo da parte all'incasso: saperlo mentre si decide il
  // prezzo è più utile che scoprirlo dopo.
  const hint = $('accHint');
  if (hint) {
    if (t.totale > 0 && ACC_RATE > 0) {
      hint.style.display = 'block';
      hint.innerHTML = 'Quando incasserai, metti da parte circa '
        + '<strong>' + eur(t.totale * ACC_RATE) + '</strong> ('
        + (ACC_RATE * 100).toFixed(1).replace('.', ',') + '%). '
        + 'Restano tuoi ' + eur(t.totale * (1 - ACC_RATE)) + '.';
    } else {
      hint.style.display = 'none';
    }
  }
}

// ==============================================================
// Salvataggio
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
  if (!currentCliente()) return 'Seleziona un cliente.';
  const nonZero = righe.some(r => (Number(r.qta) || 0) > 0 && (Number(r.prezzo) || 0) > 0);
  if (!nonZero) return 'Aggiungi almeno una riga con quantità e prezzo.';
  return null;
}

function righePulite() {
  return righe
    .filter(r => (Number(r.qta) || 0) > 0 && (Number(r.prezzo) || 0) > 0)
    .map(r => ({descrizione: r.desc, qta: Number(r.qta), um: r.um || null,
                prezzo: Number(r.prezzo),
                tot: r2(Number(r.qta) * Number(r.prezzo))}));
}

function corpoComune(t, dataIso) {
  return {
    data: dataIso,
    tipo_doc: $('d_tipo').value || 'TD01',
    cliente_id: currentCliente().id,
    cliente_snapshot: clienteSnapshot(currentCliente()),
    righe: righePulite(),
    imponibile: t.imponibile,
    bollo: t.bolloAdd || (t.bolloDovuto ? 2.00 : 0),
    bollo_addebitato: t.bolloAdd > 0,
    cassa_perc: t.rivalsa_perc,
    cassa_importo: t.rivalsa,
    totale: t.totale,
    divisa: ($('d_div').value || 'EUR').toUpperCase(),
    pagamento_mod: $('p_mod').value || null,
    pagamento_cond: $('p_cond').value || null,
    scadenza: $('p_scad').value || null,
    iban: (window.B2F_EMITTENTE && window.B2F_EMITTENTE.iban) || null,
  };
}

async function onSalva() {
  const err = validate();
  if (err) { toast(err, 'err'); return; }
  const btn = $('btnSalva'); btn.disabled = true;
  const t = calc();
  const dataIso = $('d_data').value || todayISO();

  try {
    if (INIT.modo === 'modifica') {
      const r = await fetch('/fatture/api/fatture/' + INIT.id, {
        method: 'PATCH', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(corpoComune(t, dataIso)),
      });
      const j = await r.json();
      if (!r.ok) { toast(j.error || 'Errore salvataggio', 'err'); return; }
      toast('Modifiche salvate', 'ok');
      setTimeout(()=>{ location.href = '/fatture/' + INIT.id; }, 600);
      return;
    }

    const anno = new Date(dataIso).getFullYear();
    if (!CURRENT_PROG || CURRENT_ANNO !== anno) {
      try {
        const rp = await fetch('/fatture/api/next_progressivo?anno=' + anno);
        const jp = await rp.json();
        CURRENT_ANNO = jp.anno; CURRENT_PROG = jp.progressivo;
      } catch (e) {}
    }
    const payload = Object.assign(
      {anno, progressivo: CURRENT_PROG, stato: 'bozza'},
      corpoComune(t, dataIso));
    const r = await fetch('/fatture/api/fatture', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok) { toast(j.error || 'Errore salvataggio', 'err'); return; }
    toast('Bozza ' + (j.numero || '') + ' salvata', 'ok');
    setTimeout(()=>{ location.href = '/fatture/' + j.id; }, 700);
  } catch (e) {
    toast('Errore rete: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

// ==============================================================
// Facsimile PDF
// ==============================================================
function buildPdfPayload() {
  const c = currentCliente();
  const t = calc();
  const dataIso = $('d_data').value || todayISO();
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
    righe: righePulite().map(r => ({descrizione: r.descrizione, qta: r.qta,
                                    um: r.um, prezzo: r.prezzo})),
    corrispettivo: t.corrispettivo,
    compenso: t.compenso,
    cassa_perc: t.rivalsa_perc,
    cassa_importo: t.rivalsa,
    imponibile: t.imponibile,
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
  if (window.b2fRenderInvoicePDF(buildPdfPayload())) toast('Facsimile generato', 'ok');
}

// ==============================================================
// Avvio
// ==============================================================
(async () => {
  $('d_data').value  = INIT.data;
  $('d_tipo').value  = INIT.tipo_doc;
  $('d_div').value   = INIT.divisa;
  $('p_mod').value   = INIT.pagamento_mod;
  $('p_cond').value  = INIT.pagamento_cond;
  $('p_scad').value  = INIT.scadenza || '';
  $('o_inps').checked      = !!INIT.rivalsa;
  $('o_bollo_add').checked = !!INIT.bollo_add;

  righe = INIT.righe.map(r => ({...r}));
  renderRighe();

  if (INIT.modo === 'modifica') {
    $('d_num').value = INIT.numero;
    $('d_num').disabled = true;
    $('btnSalva').textContent = 'Salva modifiche';
    $('azioniAnnulla').style.display = 'flex';
    $('linkIndietro').href = '/fatture/' + INIT.id;
  }

  await loadClienti();
  await loadProgressivo();
  $('d_data').addEventListener('change', loadProgressivo);
  recalc();
})();
</script>
"""
