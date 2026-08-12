"""
spese/movimenti.py — Movimenti del conto personale: lista, form, API.

Rotte HTML:
  GET /spese/movimenti              -> lista con filtri
  GET /spese/movimenti/nuovo        -> form nuovo movimento
  GET /spese/movimenti/<int:mid>    -> form modifica

Rotte JSON:
  GET    /spese/api/movimenti
  POST   /spese/api/movimenti
  PATCH  /spese/api/movimenti/<int:mid>
  DELETE /spese/api/movimenti/<int:mid>
  GET    /spese/api/categorie
"""
import json
from datetime import date

from flask import Response, request, jsonify

from . import spese_bp
from . import dati as D
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_it

MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;") \
        .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _no_db(breadcrumb):
    return _render('<div class="notice warn">Supabase non configurato.</div>',
                   eyebrow="Movimenti", titolo='I miei <em>movimenti</em>',
                   breadcrumb=breadcrumb)


def _riga_movimento(m: dict) -> str:
    tipo = m.get("tipo") or ""
    segno = D.TIPI_SEGNO.get(tipo, 0)
    cls = "pos" if segno > 0 else "neg" if segno < 0 else ""
    imp = abs(float(m.get("importo") or 0))
    cat = m.get("categoria") or "Senza categoria"
    if m.get("sottocategoria"):
        cat += f' · {m["sottocategoria"]}'
    marchio = ('<span class="chip">giroconto</span>'
               if tipo == "giroconto" else "")
    return f'''
    <a class="item" href="/spese/movimenti/{m["id"]}">
      <span class="body">
        <span class="n">{_esc((m.get("descrizione") or "—")[:60])}</span>
        <span class="m">{data_it(m.get("data"))} · {_esc(cat)}</span>
      </span>
      <span class="end">
        <span class="amt tnum {cls}">{eur_segno(imp * (segno or 1))}</span>
        {marchio}
      </span>
    </a>'''


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------

@spese_bp.get("/movimenti")
def movimenti_lista():
    breadcrumb = [("Spese", "/spese"), ("Movimenti", "")]
    client = D.sb()
    if client is None:
        return _no_db(breadcrumb)

    oggi = date.today()
    anno = request.args.get("anno", type=int) or oggi.year
    mese = request.args.get("mese", type=int) or 0
    tipo = request.args.get("tipo") or ""
    categoria = request.args.get("categoria") or ""
    sottocategoria = request.args.get("sottocategoria") or ""
    metodo = (request.args.get("metodo") or "").strip()
    importo_min = request.args.get("importo_min", type=float)
    importo_max = request.args.get("importo_max", type=float)
    cerca = (request.args.get("q") or "").strip()

    filtri = dict(anno=anno, mese=mese or None, tipo=tipo or None,
                 categoria=categoria or None, sottocategoria=sottocategoria or None,
                 metodo=metodo or None, importo_min=importo_min,
                 importo_max=importo_max, cerca=cerca or None)
    righe = D.movimenti(client, limite=300, **filtri)
    # I KPI in cima devono contare TUTTO il periodo filtrato, non solo le
    # righe mostrate in lista: un anno pieno puo' avere piu' di 300
    # movimenti (qui ne bastano 461 su un anno solo), e sommare le sole
    # righe visibili farebbe un saldo troncato per difetto.
    t = D.totali_periodo(client, **filtri)

    anni = D.anni_disponibili(client)
    if anno not in anni:
        anni = sorted(set(anni + [anno]), reverse=True)
    voci_cat = D.voci_categoria(client)
    categorie = sorted({v["categoria"] for v in voci_cat})
    sottocategorie = sorted({v["sottocategoria"] for v in voci_cat if v["sottocategoria"]})

    def opzioni(valori, corrente, etichetta_vuota):
        out = [f'<option value="">{etichetta_vuota}</option>']
        for val, lbl in valori:
            sel = " selected" if str(val) == str(corrente) else ""
            out.append(f'<option value="{val}"{sel}>{lbl}</option>')
        return "".join(out)

    toolbar = f'''
    <div class="toolbar">
      <select class="select-pill" aria-label="Anno" onchange="filtra('anno', this.value)">
        {"".join(f'<option value="{a}"{" selected" if a == anno else ""}>{a}</option>' for a in anni)}
      </select>
      <select class="select-pill" aria-label="Mese" onchange="filtra('mese', this.value)">
        {opzioni([(i + 1, MESI[i]) for i in range(12)], mese or "", "Tutto l'anno")}
      </select>
      <select class="select-pill" aria-label="Tipo" onchange="filtra('tipo', this.value)">
        {opzioni(D.TIPI, tipo, "Tutti i tipi")}
      </select>
      <select class="select-pill" aria-label="Categoria" onchange="filtra('categoria', this.value)">
        {opzioni([(c, c) for c in categorie], categoria, "Tutte le categorie")}
      </select>
      <input class="select-pill" style="min-width:150px" placeholder="Cerca…"
             value="{_esc(cerca)}" onchange="filtra('q', this.value)">
      <a class="btn ghost" href="/spese/importa">{icon("download")}Importa da banca</a>
    </div>
    <details class="explain mb-3">
      <summary>Filtri avanzati</summary>
      <div class="field-group mt-2">
        <div class="field"><label>Sottocategoria</label>
          <select class="input" onchange="filtra('sottocategoria', this.value)">
            {opzioni([(s, s) for s in sottocategorie], sottocategoria, "Tutte")}
          </select></div>
        <div class="field"><label>Metodo di pagamento</label>
          <input class="input" placeholder="es. Webank, Contanti…" value="{_esc(metodo)}"
                 onchange="filtra('metodo', this.value)"></div>
      </div>
      <div class="field-group">
        <div class="field"><label>Importo minimo (€)</label>
          <input class="input" type="number" step="0.01" min="0"
                 value="{importo_min if importo_min is not None else ''}"
                 onchange="filtra('importo_min', this.value)"></div>
        <div class="field"><label>Importo massimo (€)</label>
          <input class="input" type="number" step="0.01" min="0"
                 value="{importo_max if importo_max is not None else ''}"
                 onchange="filtra('importo_max', this.value)"></div>
      </div>
    </details>'''

    riepilogo = f'''
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat">
        <div class="val tnum {"pos" if t["saldo"] >= 0 else "neg"}">€ {eur_segno(t["saldo"], 0)}</div>
        <div class="lbl">Saldo del periodo</div>
        <div class="hint">{t["n"]} moviment{"o" if t["n"] == 1 else "i"}</div>
      </div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum pos">€ {eur(t["entrate"], 0)}</div>
        <div class="lbl">Entrate</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum neg">€ {eur(t["uscite"], 0)}</div>
        <div class="lbl">Uscite</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum">€ {eur(t["giroconti"], 0)}</div>
        <div class="lbl">Dalla P.IVA</div></div></div>
    </div>'''

    if not righe:
        corpo = f'''<div class="empty">{icon("spese")}
          <div class="t">Nessun movimento</div>
          <div class="s">Nessun risultato per i filtri scelti.</div></div>'''
    else:
        corpo = f'<div class="list">{"".join(_riga_movimento(m) for m in righe)}</div>'

    ripartizione = ""
    quote = D.per_categoria(righe, "uscita")[:8]
    if quote:
        barre = "".join(f'''
        <div class="row">
          <span class="t">{_esc(q["categoria"])}
            <span class="sub">{q["quota"] * 100:.1f}% delle uscite</span></span>
          <span class="v tnum">€ {eur(q["importo"])}</span>
        </div>''' for q in quote)
        ripartizione = f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">Dove vanno le uscite</div></div>
          <div class="rows detail">{barre}</div>
        </div>'''

    body = f'''
    {riepilogo}{toolbar}
    <div class="grid split">
      <div class="stack">{corpo}</div>
      <div class="stack">{ripartizione}</div>
    </div>
    <script>
      function filtra(chiave, valore) {{
        const u = new URL(location.href);
        if (valore) u.searchParams.set(chiave, valore);
        else u.searchParams.delete(chiave);
        location.href = u;
      }}
    </script>'''

    return _render(body, eyebrow=f"Movimenti {anno}",
                   titolo='I miei <em>movimenti</em>', breadcrumb=breadcrumb,
                   fab=("Nuovo movimento", "/spese/movimenti/nuovo"))


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------

def _form(client, m: dict | None = None) -> str:
    m = m or {}
    mid = m.get("id")
    modifica = bool(mid)
    tipo_corrente = m.get("tipo") or "uscita"

    albero = D.albero_categorie(client)
    cat_corrente = m.get("categoria") or ""
    cat_opts = "".join(
        f'<option value="{_esc(g["categoria"])}"'
        f'{" selected" if g["categoria"] == cat_corrente else ""}>'
        f'{_esc(g["categoria"])}</option>' for g in albero)

    # Il movimento che nasce da un giroconto ha una contropartita sul
    # conto P.IVA: si dice, e si impedisce di cancellarlo da qui.
    collegato = D.collegato(client, mid) if modifica else None
    avviso = ""
    if collegato:
        if collegato["origine"] == "fattura":
            origine = f'del giroconto della fattura <strong>{_esc(collegato.get("numero") or "")}</strong>'
            istruzione = '"Annulla la ripartizione" sulla fattura'
        else:
            origine = 'di un giroconto registrato in Spese P.IVA'
            istruzione = "l'eliminazione dalla sezione Spese P.IVA"
        avviso = f'''<div class="notice info mb-4">
          Questo movimento è la contropartita {origine}. Per annullarlo usa
          {istruzione}: così spariscono entrambe le righe, qui e sul conto P.IVA.
        </div>'''

    # Un movimento collegato non si salva da qui in nessun caso: il form
    # spedisce sempre tipo e importo insieme al resto, e l'endpoint li
    # rifiuta. Meglio non mostrare un bottone che fallirebbe sempre.
    ro = " disabled" if collegato else ""
    salva_btn = ("" if collegato else
                 f'<button type="button" class="btn" onclick="onSalva()">'
                 f'{"Aggiorna" if modifica else "Registra movimento"}</button>')
    elimina_btn = ""
    if modifica and not collegato:
        elimina_btn = ('<button type="button" class="btn danger" '
                       'onclick="onElimina()">Elimina</button>')

    return f'''
    <div class="narrow">
    {avviso}
    <div class="card">
      <div class="field-group">
        <div class="field"><label>Data</label>
          <input type="date" id="f_data"{ro}
                 value="{_esc(m.get("data") or date.today().isoformat())}"></div>
        <div class="field"><label>Importo (€)</label>
          <input type="number" step="0.01" min="0" inputmode="decimal" id="f_importo"{ro}
                 value="{abs(float(m.get("importo") or 0)) or ""}"></div>
      </div>
      <div class="field"><label>Tipo</label>
        <select id="f_tipo"{ro}>
          {"".join(f'<option value="{k}"{" selected" if k == tipo_corrente else ""}>{lbl}</option>' for k, lbl in D.TIPI)}
        </select>
        <div class="hint">L'importo è sempre positivo: la direzione la dà il tipo.</div>
      </div>
      <div class="field"><label>Descrizione</label>
        <input id="f_descrizione"{ro} value="{_esc(m.get("descrizione"))}"></div>
      <div class="field-group">
        <div class="field"><label>Categoria</label>
          <select id="f_categoria"{ro} onchange="aggiornaSub()">
            <option value="">—</option>{cat_opts}
          </select></div>
        <div class="field"><label>Sottocategoria</label>
          <select id="f_sottocategoria"{ro}><option value="">—</option></select></div>
      </div>
      <div class="field"><label>Metodo di pagamento</label>
        <input id="f_metodo"{ro} list="metodi" value="{_esc(m.get("metodo_pagamento"))}">
        <datalist id="metodi">
          <option value="Bancomat"><option value="Carta di credito">
          <option value="Contanti"><option value="Bonifico">
          <option value="Giroconto"><option value="Addebito diretto">
        </datalist>
      </div>
      <div class="actions">
        {salva_btn}
        {elimina_btn}
        <a class="btn ghost" href="/spese/movimenti">Annulla</a>
      </div>
    </div>
    </div>
    <div id="toast" class="toast"></div>
    <script>
      const ALBERO = {json.dumps(albero, ensure_ascii=False)};
      const MID = {mid if modifica else "null"};
      const SUB_INIZIALE = {json.dumps(m.get("sottocategoria"), ensure_ascii=False)};

      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 2600);
      }}

      // Le sottocategorie dipendono dalla categoria: l'accoppiamento
      // valido e' deciso da cfg_categoria_sottocategoria, non libero.
      function aggiornaSub() {{
        const cat = document.getElementById('f_categoria').value;
        const sel = document.getElementById('f_sottocategoria');
        const gruppo = ALBERO.find(g => g.categoria === cat);
        sel.innerHTML = '<option value="">—</option>';
        if (!gruppo) return;
        for (const v of gruppo.voci) {{
          if (!v.sottocategoria) continue;
          const o = document.createElement('option');
          o.value = v.sottocategoria; o.textContent = v.sottocategoria;
          sel.appendChild(o);
        }}
      }}

      function linkId() {{
        const cat = document.getElementById('f_categoria').value;
        const sub = document.getElementById('f_sottocategoria').value || null;
        const gruppo = ALBERO.find(g => g.categoria === cat);
        if (!gruppo) return null;
        const v = gruppo.voci.find(x => (x.sottocategoria || null) === sub);
        return v ? v.link_id : null;
      }}

      async function onSalva() {{
        const importo = Number(document.getElementById('f_importo').value || 0);
        if (!(importo > 0)) {{ toast('Inserisci un importo', 'err'); return; }}
        const cat = document.getElementById('f_categoria').value;
        const link = linkId();
        if (cat && !link) {{
          toast('Questa coppia categoria/sottocategoria non è prevista', 'err'); return;
        }}
        const body = {{
          data: document.getElementById('f_data').value,
          tipo: document.getElementById('f_tipo').value,
          importo: importo,
          descrizione: document.getElementById('f_descrizione').value.trim() || null,
          metodo_pagamento: document.getElementById('f_metodo').value.trim() || null,
          categoria_link_id: link,
        }};
        const nuovo = !MID;
        try {{
          const r = await fetch(nuovo ? '/spese/api/movimenti' : '/spese/api/movimenti/' + MID, {{
            method: nuovo ? 'POST' : 'PATCH',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast(nuovo ? 'Movimento registrato' : 'Aggiornato', 'ok');
          setTimeout(()=>{{ location.href = '/spese/movimenti'; }}, 600);
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}

      async function onElimina() {{
        if (!confirm('Eliminare questo movimento?')) return;
        try {{
          const r = await fetch('/spese/api/movimenti/' + MID, {{method: 'DELETE'}});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); return; }}
          toast('Eliminato', 'ok');
          setTimeout(()=>{{ location.href = '/spese/movimenti'; }}, 600);
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
      }}

      aggiornaSub();
      if (SUB_INIZIALE) document.getElementById('f_sottocategoria').value = SUB_INIZIALE;
    </script>'''


@spese_bp.get("/movimenti/nuovo")
def movimento_nuovo():
    breadcrumb = [("Spese", "/spese"), ("Movimenti", "/spese/movimenti"), ("Nuovo", "")]
    client = D.sb()
    if client is None:
        return _no_db(breadcrumb)
    return _render(_form(client), eyebrow="Nuovo movimento",
                   titolo='<em>Nuovo</em> movimento', breadcrumb=breadcrumb)


@spese_bp.get("/movimenti/<int:mid>")
def movimento_modifica(mid):
    breadcrumb = [("Spese", "/spese"), ("Movimenti", "/spese/movimenti"), (str(mid), "")]
    client = D.sb()
    if client is None:
        return _no_db(breadcrumb)
    m = D.movimento(client, mid)
    if not m:
        return _render('<div class="notice err">Movimento non trovato.</div>',
                       eyebrow="Movimento", titolo='<em>Movimento</em>',
                       breadcrumb=breadcrumb)
    return _render(_form(client, m), eyebrow="Movimento",
                   titolo=f'<em>{_esc((m.get("descrizione") or "Movimento")[:24])}</em>',
                   breadcrumb=breadcrumb)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _client_o_503():
    client = D.sb()
    if client is None:
        return None, (jsonify({"error": "supabase not configured"}), 503)
    return client, None


@spese_bp.get("/api/movimenti")
def api_movimenti():
    client, err = _client_o_503()
    if err:
        return err
    return jsonify(D.movimenti(
        client,
        anno=request.args.get("anno", type=int),
        mese=request.args.get("mese", type=int),
        tipo=request.args.get("tipo"),
        categoria=request.args.get("categoria"),
        cerca=request.args.get("q"),
    ))


@spese_bp.post("/api/movimenti")
def api_movimento_crea():
    client, err = _client_o_503()
    if err:
        return err
    esito = D.crea(client, request.get_json(silent=True) or {})
    return (jsonify(esito), 400) if esito.get("error") else jsonify(esito)


def _messaggio_collegato(collegato: dict, verbo: str) -> str:
    if collegato["origine"] == "fattura":
        return (f'Questo movimento è la contropartita del giroconto della fattura '
                f'{collegato.get("numero") or ""}. {verbo} dalla fattura, così '
                f'spariscono entrambe le righe.')
    return (f'Questo movimento è la contropartita di un giroconto registrato in '
            f'Spese P.IVA. {verbo} da lì, così spariscono entrambe le righe.')


@spese_bp.patch("/api/movimenti/<int:mid>")
def api_movimento_aggiorna(mid):
    client, err = _client_o_503()
    if err:
        return err
    # Le guardie stanno qui e non solo nel form: un giroconto alterato a
    # meta' disallineerebbe i due conti senza che nulla lo segnali.
    collegato = D.collegato(client, mid)
    if collegato:
        return jsonify({"error": _messaggio_collegato(
            collegato, "Annulla la ripartizione" if collegato["origine"] == "fattura"
                       else "Eliminalo")}), 409
    esito = D.aggiorna(client, mid, request.get_json(silent=True) or {})
    return (jsonify(esito), 400) if esito.get("error") else jsonify(esito)


@spese_bp.delete("/api/movimenti/<int:mid>")
def api_movimento_elimina(mid):
    client, err = _client_o_503()
    if err:
        return err
    # Meta' giroconto non si cancella da qui: l'altra riga resterebbe sul
    # conto P.IVA senza contropartita, e i due conti non tornerebbero piu'.
    collegato = D.collegato(client, mid)
    if collegato:
        return jsonify({"error": _messaggio_collegato(
            collegato, "Annulla la ripartizione" if collegato["origine"] == "fattura"
                       else "Eliminalo")}), 409
    esito = D.elimina(client, mid)
    return (jsonify(esito), 400) if esito.get("error") else jsonify(esito)


@spese_bp.get("/api/categorie")
def api_categorie():
    client, err = _client_o_503()
    if err:
        return err
    return jsonify(D.albero_categorie(client))


def _render(content: str, eyebrow: str, titolo: str,
            breadcrumb=None, fab=None) -> Response:
    return Response(render_page(section="spese", eyebrow=eyebrow,
                                title_html=titolo, content=content,
                                breadcrumb=breadcrumb, fab=fab),
                    mimetype="text/html")
