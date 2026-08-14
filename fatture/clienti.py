"""
fatture/clienti.py — CRUD anagrafica clienti (tabella b2f_clienti).

Rotte HTML:
  GET  /fatture/clienti              -> lista con search + tipo
  GET  /fatture/clienti/nuovo        -> form nuovo cliente
  GET  /fatture/clienti/<int:cid>    -> form edit
Rotte JSON:
  POST   /fatture/api/clienti           -> crea
  PATCH  /fatture/api/clienti/<int:cid> -> aggiorna
  DELETE /fatture/api/clienti/<int:cid> -> soft delete (attivo=false)
"""
from flask import Response, request, jsonify, redirect, url_for

from . import fatture_bp
from shared.theme import render_page
from shared.design import icon as _icon
from shared.ordina import chiave_alfabetica, ordina_coppie
from shared.supabase_client import get_client, is_configured


TIPI = ordina_coppie([
    ("azienda", "Azienda IT"),
    ("privato", "Privato"),
    ("pa",      "Pubblica Amministrazione"),
    ("estero",  "Cliente estero"),
])

# Campi anagrafica raccolti dal form
CAMPI = [
    "tipo", "denominazione", "nome", "cognome",
    "piva", "cf",
    "indirizzo", "cap", "comune", "provincia", "nazione",
    "sdi", "pec", "email",
    "note",
]


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _label(c: dict) -> str:
    """Nome leggibile del cliente. Testo grezzo: chi lo stampa in HTML
    deve passarlo da _esc(), perche' nome/cognome/denominazione sono
    testo libero digitato dall'utente."""
    tipo = (c.get("tipo") or "azienda")
    if tipo == "privato":
        return f'{c.get("nome") or ""} {c.get("cognome") or ""}'.strip() or "—"
    return c.get("denominazione") or "—"


def _sub(c: dict) -> str:
    parts = []
    if c.get("piva"): parts.append(f"P.IVA {_esc(c['piva'])}")
    if c.get("cf") and not c.get("piva"): parts.append(f"CF {_esc(c['cf'])}")
    if c.get("comune"): parts.append(_esc(c["comune"]))
    return " · ".join(parts) or "—"


def _tipo_chip(tipo: str) -> str:
    cls = {"azienda": "accent", "privato": "", "pa": "warn", "estero": "pos"}.get(tipo, "")
    lbl = dict(TIPI).get(tipo, tipo)
    return f'<span class="chip {cls}">{lbl}</span>'


def _supabase_or_error():
    if not is_configured():
        return None, ('<div class="notice warn">Supabase non configurato.</div>')
    return get_client(), None


# ---------------------------------------------------------------------------
# Lista clienti
# ---------------------------------------------------------------------------

@fatture_bp.get("/clienti")
def clienti_list():
    sb, err = _supabase_or_error()
    if err:
        content = err
    else:
        q = (request.args.get("q") or "").strip()
        tipo = request.args.get("tipo") or ""
        show_inactive = request.args.get("all") == "1"

        query = sb.table("b2f_clienti").select("*").order("id", desc=True)
        if not show_inactive:
            query = query.eq("attivo", True)
        if tipo:
            query = query.eq("tipo", tipo)
        try:
            r = query.execute()
            rows = r.data or []
        except Exception as e:
            content = f'<div class="notice err">Errore: {str(e)[:200]}</div>'
            return _render(content, breadcrumb=[("Fatture", "/fatture"), ("Clienti", "")])

        if q:
            ql = q.lower()
            def match(c):
                fields = [_label(c), c.get("piva") or "", c.get("cf") or "",
                          c.get("comune") or "", c.get("email") or ""]
                return any(ql in (f or "").lower() for f in fields)
            rows = [c for c in rows if match(c)]

        # Filtri
        opts = "".join(
            f'<option value="{k}"{" selected" if tipo==k else ""}>{lbl}</option>'
            for k, lbl in TIPI
        )
        inactive_toggle = ("Attivi & inattivi" if show_inactive else "Solo attivi")
        toggle_href = "/fatture/clienti" if show_inactive else "/fatture/clienti?all=1"

        toolbar = f'''
        <div class="toolbar">
          <input class="select-pill" id="q_search" type="search" aria-label="Cerca cliente"
                 placeholder="Cerca…" value="{_esc(q)}" style="flex:1;min-width:150px"
                 oninput="clearTimeout(window.__st);window.__st=setTimeout(()=>{{
                   const u=new URL(location.href);
                   if(this.value){{u.searchParams.set('q',this.value);}}else{{u.searchParams.delete('q');}}
                   location.href=u.toString();
                 }},420)">
          <select class="select-pill" aria-label="Tipo cliente"
                  onchange="location.href='/fatture/clienti'+(this.value?'?tipo='+this.value:'')">
            <option value="">Tutti i tipi</option>
            {opts}
          </select>
          <a href="{toggle_href}" class="btn ghost" style="min-height:40px;padding:8px 16px;
             font-size:13.5px;font-weight:500">{inactive_toggle}</a>
        </div>
        '''

        if not rows:
            body = f'''
            {toolbar}
            <div class="empty">
              {_icon("clienti")}
              <div class="t">Nessun cliente</div>
              <div class="s">Nessun risultato con i filtri correnti.</div>
            </div>
            '''
        else:
            items = []
            for c in rows:
                inactive = ("" if c.get("attivo")
                            else '<span class="chip">Inattivo</span>')
                items.append(f'''
                <a class="item" href="/fatture/clienti/{c["id"]}">
                  <span class="ico neutral">{_icon("clienti")}</span>
                  <span class="body">
                    <span class="n">{_esc(_label(c))}</span>
                    <span class="m">{_sub(c)}</span>
                  </span>
                  <span class="end">
                    {_tipo_chip(c.get("tipo") or "azienda")}{inactive}
                  </span>
                </a>''')
            body = f'{toolbar}<div class="list">{"".join(items)}</div>'

        content = body

    return _render(
        content,
        breadcrumb=[("Fatture", "/fatture"), ("Clienti", "")],
        fab=("Nuovo cliente", "/fatture/clienti/nuovo"),
    )


# ---------------------------------------------------------------------------
# Nuovo / Edit
# ---------------------------------------------------------------------------

def _form_html(c: dict | None = None) -> str:
    c = c or {}
    v = lambda k: _esc(c.get(k) or "")
    tipo_current = c.get("tipo") or "azienda"
    tipo_options = "".join(
        f'<option value="{k}"{" selected" if k==tipo_current else ""}>{lbl}</option>'
        for k, lbl in TIPI
    )

    cid = c.get("id") or ""
    is_edit = bool(cid)
    inactive_note = ""
    if is_edit and not c.get("attivo"):
        inactive_note = '<div class="notice warn" style="margin-bottom:14px">Cliente disattivato.</div>'

    delete_btn = ""
    if is_edit:
        active_now = bool(c.get("attivo"))
        lbl = "Disattiva" if active_now else "Riattiva"
        cls = "btn danger" if active_now else "btn ghost"
        delete_btn = f'''<button type="button" class="{cls}"
          onclick="toggleActive({cid}, {str(not active_now).lower()})">{lbl}</button>'''

    submit_lbl = "Aggiorna" if is_edit else "Crea cliente"

    return f'''
    <div class="narrow">
    {inactive_note}
    <div class="card">
      <div class="field">
        <label>Tipo</label>
        <select id="f_tipo" onchange="onTipoChange()">{tipo_options}</select>
      </div>

      <div id="grp_azienda" class="field">
        <label>Denominazione / Ragione sociale</label>
        <input id="f_denominazione" value="{v('denominazione')}">
      </div>

      <div id="grp_privato" class="field-group" style="display:none">
        <div class="field"><label>Nome</label>
          <input id="f_nome" value="{v('nome')}"></div>
        <div class="field"><label>Cognome</label>
          <input id="f_cognome" value="{v('cognome')}"></div>
      </div>

      <div class="field-group">
        <div class="field"><label>Partita IVA</label>
          <input id="f_piva" value="{v('piva')}" placeholder="IT01234567890"></div>
        <div class="field"><label>Codice Fiscale</label>
          <input id="f_cf" value="{v('cf')}"></div>
      </div>

      <div class="field"><label>Indirizzo</label>
        <input id="f_indirizzo" value="{v('indirizzo')}"></div>

      <div class="field-group c3">
        <div class="field"><label>Comune</label>
          <input id="f_comune" value="{v('comune')}"></div>
        <div class="field"><label>CAP</label>
          <input id="f_cap" value="{v('cap')}"></div>
        <div class="field"><label>Prov</label>
          <input id="f_provincia" value="{v('provincia')}" maxlength="2"
                 style="text-transform:uppercase"></div>
      </div>

      <div class="field-group">
        <div class="field"><label>Nazione</label>
          <input id="f_nazione" value="{v('nazione') or 'IT'}" maxlength="2"
                 style="text-transform:uppercase"></div>
        <div class="field"><label>Codice SDI</label>
          <input id="f_sdi" value="{v('sdi')}" placeholder="0000000" maxlength="7"></div>
      </div>

      <div class="field-group">
        <div class="field"><label>PEC</label>
          <input id="f_pec" type="email" value="{v('pec')}"></div>
        <div class="field"><label>Email</label>
          <input id="f_email" type="email" value="{v('email')}"></div>
      </div>

      <div class="field"><label>Note</label>
        <textarea id="f_note">{_esc(c.get('note') or '')}</textarea></div>

      <div class="actions">
        <button type="button" class="btn" onclick="onSubmit({cid or 'null'})">{submit_lbl}</button>
        {delete_btn}
      </div>
    </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
    function onTipoChange() {{
      const t = document.getElementById('f_tipo').value;
      document.getElementById('grp_azienda').style.display = (t==='privato' ? 'none' : '');
      document.getElementById('grp_privato').style.display = (t==='privato' ? 'grid' : 'none');
    }}
    onTipoChange();

    function readForm() {{
      const g = id => document.getElementById(id).value.trim();
      return {{
        tipo: g('f_tipo'),
        denominazione: g('f_denominazione') || null,
        nome: g('f_nome') || null,
        cognome: g('f_cognome') || null,
        piva: g('f_piva') || null,
        cf: g('f_cf') || null,
        indirizzo: g('f_indirizzo') || null,
        cap: g('f_cap') || null,
        comune: g('f_comune') || null,
        provincia: (g('f_provincia') || '').toUpperCase() || null,
        nazione: (g('f_nazione') || 'IT').toUpperCase(),
        sdi: g('f_sdi') || null,
        pec: g('f_pec') || null,
        email: g('f_email') || null,
        note: document.getElementById('f_note').value.trim() || null,
      }};
    }}

    function toast(msg, cls) {{
      const t = document.getElementById('toast');
      t.textContent = msg; t.className = 'toast show ' + (cls || '');
      setTimeout(()=>{{t.className='toast '+(cls||'')}}, 2200);
    }}

    async function onSubmit(cid) {{
      const body = readForm();
      const isNew = !cid;
      const url = isNew ? '/fatture/api/clienti' : '/fatture/api/clienti/'+cid;
      const method = isNew ? 'POST' : 'PATCH';
      try {{
        const r = await fetch(url, {{
          method, headers:{{'Content-Type':'application/json'}},
          body: JSON.stringify(body),
        }});
        const j = await r.json();
        if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
        toast(isNew ? 'Cliente creato' : 'Aggiornato', 'ok');
        setTimeout(()=>{{ location.href = '/fatture/clienti/' + (j.id || cid); }}, 500);
      }} catch (e) {{ toast('Errore: '+e.message, 'err'); }}
    }}

    async function toggleActive(cid, nextActive) {{
      try {{
        const r = await fetch('/fatture/api/clienti/'+cid, {{
          method:'PATCH', headers:{{'Content-Type':'application/json'}},
          body: JSON.stringify({{attivo: nextActive}}),
        }});
        if (!r.ok) {{ toast('Errore', 'err'); return; }}
        toast(nextActive ? 'Riattivato' : 'Disattivato', 'ok');
        setTimeout(()=>location.reload(), 500);
      }} catch (e) {{ toast('Errore: '+e.message, 'err'); }}
    }}
    </script>
    '''


@fatture_bp.get("/clienti/nuovo")
def cliente_new():
    content = _form_html(None)
    return _render(
        content,
        eyebrow="Nuovo cliente",
        title_html='<em>Nuovo</em> cliente',
        breadcrumb=[("Fatture", "/fatture"), ("Clienti", "/fatture/clienti"), ("Nuovo", "")],
    )


@fatture_bp.get("/clienti/<int:cid>")
def cliente_edit(cid):
    sb, err = _supabase_or_error()
    if err:
        return _render(err, breadcrumb=[("Fatture", "/fatture"),
                                        ("Clienti", "/fatture/clienti"), (str(cid), "")])
    try:
        r = sb.table("b2f_clienti").select("*").eq("id", cid).single().execute()
        c = r.data
    except Exception as e:
        return _render(f'<div class="notice err">{str(e)[:200]}</div>',
                       breadcrumb=[("Fatture", "/fatture"),
                                   ("Clienti", "/fatture/clienti"), (str(cid), "")])

    return _render(
        _form_html(c),
        eyebrow="Cliente",
        title_html=f'<em>{_esc(_label(c)[:24])}</em>',
        breadcrumb=[("Fatture", "/fatture"), ("Clienti", "/fatture/clienti"),
                    (_esc(_label(c)[:20]), "")],
    )


# ---------------------------------------------------------------------------
# API JSON
# ---------------------------------------------------------------------------

def _payload_clean(data: dict) -> dict:
    """Restringe il payload ai soli campi consentiti."""
    out = {}
    for k in CAMPI:
        if k in data:
            v = data[k]
            if isinstance(v, str):
                v = v.strip() or None
            out[k] = v
    if "attivo" in data:
        out["attivo"] = bool(data["attivo"])
    return out


@fatture_bp.get("/api/clienti-picker")
def api_clienti_picker():
    """Lista clienti attivi, ordinata per label, per il picker dell'editor."""
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    try:
        r = (sb.table("b2f_clienti").select("*")
             .eq("attivo", True).order("id", desc=True).execute())
        # Ordino per label alfabeticamente lato Python (piu' semplice).
        # `chiave_alfabetica` e non `.lower()`: un cliente che inizia per
        # accento (o una ragione sociale con "È") finiva in fondo.
        rows = r.data or []
        rows.sort(key=lambda c: chiave_alfabetica(_label(c)))
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.post("/api/clienti")
def api_cliente_create():
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    if not data.get("tipo"):
        return jsonify({"error": "tipo obbligatorio"}), 400
    payload = _payload_clean(data)
    try:
        r = sb.table("b2f_clienti").insert(payload).execute()
        return jsonify(r.data[0] if r.data else {})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.patch("/api/clienti/<int:cid>")
def api_cliente_update(cid):
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    data = request.get_json(silent=True) or {}
    payload = _payload_clean(data)
    try:
        r = sb.table("b2f_clienti").update(payload).eq("id", cid).execute()
        return jsonify(r.data[0] if r.data else {"id": cid})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@fatture_bp.delete("/api/clienti/<int:cid>")
def api_cliente_delete(cid):
    """Soft delete: pone attivo=false. Non elimina fisicamente."""
    sb, err = _supabase_or_error()
    if err: return jsonify({"error": "supabase not configured"}), 503
    try:
        sb.table("b2f_clienti").update({"attivo": False}).eq("id", cid).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------

def _render(content: str, eyebrow: str = "Clienti",
            title_html: str = 'I miei <em>clienti</em>',
            breadcrumb=None, fab=None) -> Response:
    html = render_page(
        section="fatture", eyebrow=eyebrow, title_html=title_html,
        content=content, breadcrumb=breadcrumb, fab=fab,
    )
    return Response(html, mimetype="text/html")
