"""
fatture/emittente.py — Editor dei dati dell'emittente (intestazione documenti).

I dati salvati qui (P.IVA, C.F., indirizzo, email, PEC, IBAN, ...) sono
quelli che compaiono nell'intestazione del PDF fattura/proforma generato da
shared/pdfgen.py. Senza questi dati l'intestazione mostra solo il nome.

Rotte HTML:
  GET   /fatture/emittente            -> form editor emittente

Rotte JSON:
  GET   /fatture/api/emittente        -> dati emittente
  PATCH /fatture/api/emittente        -> aggiorna dati emittente
"""
from flask import Response, request, jsonify

from . import fatture_bp
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured


# Valori di partenza per precompilare il form la prima volta (finché la riga
# b2f_emittente non contiene ancora i dati fiscali). Vengono usati solo come
# fallback: qualsiasi valore già presente a DB ha la precedenza.
EMITTENTE_DEFAULT = {
    "id": 1,
    "nome": "Emanuele",
    "cognome": "Bellotti",
    "denominazione": "",
    "piva": "14747480961",
    "cf": "BLLMNL01S27F205K",
    "regime_fisc": "RF19",
    "indirizzo": "VIA GABBRO, 5",
    "cap": "20161",
    "comune": "Milano",
    "provincia": "MI",
    "nazione": "IT",
    "email": "ebellotti001@gmail.com",
    "pec": "ebellotti@pec.it",
    "telefono": "",
    "iban": "",
    "cassa_prev": "",
    "aliquota_cassa": 0,
}

# Campi ammessi in scrittura (PATCH).
EMITTENTE_CAMPI = (
    "nome", "cognome", "denominazione", "piva", "cf", "regime_fisc",
    "indirizzo", "cap", "comune", "provincia", "nazione", "email", "pec",
    "telefono", "iban", "cassa_prev", "aliquota_cassa",
)


def _supabase_or_error():
    if not is_configured():
        return None, ('<div class="notice warn">Supabase non configurato.</div>')
    return get_client(), None


def _get_emittente(sb) -> dict:
    """Ritorna i dati emittente: valori a DB, con fallback ai default per i
    campi ancora vuoti (così il form parte già compilato)."""
    row = {}
    try:
        r = sb.table("b2f_emittente").select("*").eq("id", 1).single().execute()
        row = r.data or {}
    except Exception:
        row = {}
    out = dict(EMITTENTE_DEFAULT)
    for k, v in row.items():
        if v not in (None, ""):
            out[k] = v
    return out


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@fatture_bp.get("/emittente")
def emittente_editor():
    sb, err = _supabase_or_error()
    breadcrumb = [("Fatture", "/fatture"), ("Emittente", "")]
    if err:
        return _render(err, breadcrumb=breadcrumb)
    e = _get_emittente(sb)

    body = f'''
    <div class="card">
      <div class="notice" style="margin-bottom:14px">
        Questi dati compaiono nell'intestazione dei PDF (fattura e proforma).
      </div>
      <div class="field-group">
        <div class="field"><label>Nome</label>
          <input id="f_nome" value="{_esc(e['nome'])}"></div>
        <div class="field"><label>Cognome</label>
          <input id="f_cognome" value="{_esc(e['cognome'])}"></div>
      </div>
      <div class="field"><label>Denominazione (opzionale, sostituisce nome+cognome)</label>
        <input id="f_denominazione" value="{_esc(e['denominazione'])}"></div>
      <div class="field-group">
        <div class="field"><label>P.IVA</label>
          <input id="f_piva" value="{_esc(e['piva'])}"></div>
        <div class="field"><label>Codice Fiscale</label>
          <input id="f_cf" value="{_esc(e['cf'])}"></div>
      </div>
      <div class="field"><label>Indirizzo</label>
        <input id="f_indirizzo" value="{_esc(e['indirizzo'])}"></div>
      <div class="field-group">
        <div class="field"><label>CAP</label>
          <input id="f_cap" value="{_esc(e['cap'])}"></div>
        <div class="field"><label>Comune</label>
          <input id="f_comune" value="{_esc(e['comune'])}"></div>
        <div class="field"><label>Prov.</label>
          <input id="f_provincia" maxlength="2" style="text-transform:uppercase"
                 value="{_esc(e['provincia'])}"></div>
      </div>
      <div class="field-group">
        <div class="field"><label>Email</label>
          <input id="f_email" type="email" value="{_esc(e['email'])}"></div>
        <div class="field"><label>PEC</label>
          <input id="f_pec" type="email" value="{_esc(e['pec'])}"></div>
      </div>
      <div class="field-group">
        <div class="field"><label>Telefono</label>
          <input id="f_telefono" value="{_esc(e['telefono'])}"></div>
        <div class="field"><label>Regime fiscale</label>
          <input id="f_regime_fisc" value="{_esc(e['regime_fisc'])}"></div>
      </div>
      <div class="field"><label>IBAN</label>
        <input id="f_iban" style="text-transform:uppercase" value="{_esc(e['iban'])}"></div>
      <div class="field-group">
        <div class="field"><label>Cassa previdenziale</label>
          <input id="f_cassa_prev" value="{_esc(e['cassa_prev'])}"></div>
        <div class="field"><label>Aliquota cassa (%)</label>
          <input type="number" step="0.01" id="f_aliquota_cassa"
                 value="{_esc(e['aliquota_cassa'])}"></div>
      </div>
      <div class="actions">
        <button type="button" class="btn" onclick="onSalva()">Salva</button>
      </div>
    </div>
    <div id="toast" class="toast"></div>
    <script>
    function toast(msg, cls) {{
      const t = document.getElementById('toast');
      t.textContent = msg; t.className = 'toast show ' + (cls || '');
      setTimeout(()=>{{t.className='toast '+(cls||'')}}, 2200);
    }}
    async function onSalva() {{
      const g = id => document.getElementById(id).value.trim();
      const body = {{
        nome: g('f_nome'), cognome: g('f_cognome'),
        denominazione: g('f_denominazione'),
        piva: g('f_piva'), cf: g('f_cf'), regime_fisc: g('f_regime_fisc'),
        indirizzo: g('f_indirizzo'), cap: g('f_cap'), comune: g('f_comune'),
        provincia: g('f_provincia').toUpperCase(),
        email: g('f_email'), pec: g('f_pec'), telefono: g('f_telefono'),
        iban: g('f_iban').toUpperCase(), cassa_prev: g('f_cassa_prev'),
        aliquota_cassa: Number(document.getElementById('f_aliquota_cassa').value || 0),
      }};
      try {{
        const r = await fetch('/fatture/api/emittente', {{
          method: 'PATCH', headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(body),
        }});
        const j = await r.json();
        if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
        toast('Dati emittente salvati', 'ok');
      }} catch (e) {{ toast('Errore rete: '+e.message, 'err'); }}
    }}
    </script>
    '''
    return _render(body, eyebrow="Emittente",
                   title_html='Dati <em>emittente</em>', breadcrumb=breadcrumb)


@fatture_bp.get("/api/emittente")
def api_emittente_get():
    sb, err = _supabase_or_error()
    if err:
        return jsonify({"error": "supabase not configured"}), 503
    return jsonify(_get_emittente(sb))


@fatture_bp.patch("/api/emittente")
def api_emittente_update():
    sb, err = _supabase_or_error()
    if err:
        return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    payload = {}
    for k in EMITTENTE_CAMPI:
        if k in data:
            v = data[k]
            if isinstance(v, str):
                v = v.strip() or None
            payload[k] = v
    if not payload:
        return jsonify({"error": "nessun campo da aggiornare"}), 400
    try:
        # Aggiorna la riga id=1; se non esiste ancora la crea (upsert).
        r = (sb.table("b2f_emittente")
               .upsert({"id": 1, **payload}).execute())
        return jsonify(r.data[0] if r.data else {"id": 1, **payload})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


def _render(content: str, eyebrow: str = "Emittente",
            title_html: str = 'Dati <em>emittente</em>',
            breadcrumb=None) -> Response:
    html = render_page(
        section="fatture", eyebrow=eyebrow, title_html=title_html,
        content=content, breadcrumb=breadcrumb,
    )
    return Response(html, mimetype="text/html")
