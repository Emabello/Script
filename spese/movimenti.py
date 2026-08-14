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
from shared.ordina import ordina

# I mesi restano in ordine di calendario: qui l'ordine e' informazione,
# non un elenco di dati da cercare per nome (vedi shared/ordina.py).
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
    # Per categoria e non per tipo: il giroconto dalla P.IVA e' sempre
    # tipo=entrata (vedi D.totali), "tipo=giroconto" non lo distingue.
    marchio = ('<span class="chip">giroconto</span>'
               if m.get("categoria") == D.CATEGORIA_GIROCONTO else "")
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
    # KPI e ripartizione devono contare TUTTO il periodo filtrato, non
    # solo le righe mostrate in lista: un anno pieno puo' avere piu' di
    # 300 movimenti (qui ne bastano 461 su un anno solo), e sommare le
    # sole righe visibili darebbe un saldo troncato per difetto. Una sola
    # query non troncata alimenta sia i totali sia la ripartizione, cosi'
    # non possono disallinearsi fra loro.
    righe_complete = D.righe_periodo(client, **filtri)
    t = D.totali(righe_complete)

    anni = D.anni_disponibili(client)
    if anno not in anni:
        anni = sorted(set(anni + [anno]), reverse=True)
    voci_cat = D.voci_categoria(client)
    categorie = ordina({v["categoria"] for v in voci_cat})
    sottocategorie = ordina({v["sottocategoria"] for v in voci_cat if v["sottocategoria"]})

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
          <select class="input" aria-label="Sottocategoria"
                  onchange="filtra('sottocategoria', this.value)">
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

    def _dd(extra: dict) -> str:
        """onclick di una card/riga: apre il dettaglio con i filtri della
        pagina piu' quelli specifici di quel numero (es. tipo=uscita).
        L'attributo HTML e' delimitato da apici singoli: una categoria
        con un "&" o un apostrofo nel nome (es. "L'Altro") altrimenti
        romperebbe l'attributo o verrebbe letta come entita' HTML.
        """
        js = json.dumps(extra, ensure_ascii=False)
        js = (js.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace(chr(39), "&#39;"))
        return f"apriDettaglio({js})"

    riepilogo = f'''
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat clickable" onclick='{_dd({})}'>
        <div class="val tnum {"pos" if t["saldo"] >= 0 else "neg"}">€ {eur_segno(t["saldo"], 0)}</div>
        <div class="lbl">Saldo del periodo</div>
        <div class="hint">{t["n"]} moviment{"o" if t["n"] == 1 else "i"} · come si calcola ›</div>
      </div></div>
      <div class="card"><div class="stat sm clickable" onclick='{_dd({"tipo": "entrata"})}'>
        <div class="val tnum pos">€ {eur(t["entrate"], 0)}</div>
        <div class="lbl">Entrate</div></div></div>
      <div class="card"><div class="stat sm clickable" onclick='{_dd({"tipo": "uscita"})}'>
        <div class="val tnum neg">€ {eur(t["uscite"], 0)}</div>
        <div class="lbl">Uscite</div></div></div>
      <div class="card"><div class="stat sm clickable" onclick='{_dd({"tipo": "entrata", "categoria": D.CATEGORIA_GIROCONTO})}'>
        <div class="val tnum">€ {eur(t["giroconti"], 0)}</div>
        <div class="lbl">Dalla P.IVA</div></div></div>
    </div>'''

    if not righe:
        corpo = f'''<div class="empty">{icon("spese")}
          <div class="t">Nessun movimento</div>
          <div class="s">Nessun risultato per i filtri scelti.</div></div>'''
    else:
        corpo = f'<div class="list">{"".join(_riga_movimento(m) for m in righe)}</div>'

    # Con una categoria gia' filtrata, ripartire di nuovo per categoria
    # darebbe sempre "100%, una riga sola": non dice niente. Si scende
    # di un livello, per sottocategoria — quello si' e' informativo.
    per_sotto = bool(categoria)
    campo_gruppo = "sottocategoria" if per_sotto else "categoria"
    titolo_ripartizione = (f"Sottocategorie di «{categoria}»" if per_sotto
                           else "Dove vanno le uscite")

    ripartizione = ""
    quote = D.per_categoria(righe_complete, "uscita", campo=campo_gruppo)[:8]
    if quote:
        def _riga_extra(nome: str) -> dict:
            extra = {"tipo": "uscita"}
            if per_sotto:
                extra["sottocategoria"] = None if nome == "Senza sottocategoria" else nome
            else:
                extra["categoria"] = None if nome == "Senza categoria" else nome
            return extra

        barre = "".join(f'''
        <div class="row clickable" onclick='{_dd(_riga_extra(q["categoria"]))}'>
          <span class="t">{_esc(q["categoria"])}
            <span class="sub">{q["quota"] * 100:.1f}% delle uscite</span></span>
          <span class="v tnum">€ {eur(q["importo"])}</span>
        </div>''' for q in quote)
        ripartizione = f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">{_esc(titolo_ripartizione)}</div></div>
          <div class="rows detail">{barre}</div>
        </div>'''

    dettaglio = f'''
    <div class="card" id="dettaglioBox" style="display:none">
      <div class="card-head">
        <div class="eyebrow" id="dettaglioTitolo">Come viene calcolato</div>
        <button class="btn ghost sm" type="button" onclick="chiudiDettaglio()">Chiudi ✕</button>
      </div>
      <div id="dettaglioCorpo"><p class="small muted">Carico…</p></div>
    </div>'''

    body = f'''
    {riepilogo}{toolbar}
    <div class="grid split">
      <div class="stack">{corpo}</div>
      <div class="stack">{ripartizione}{dettaglio}</div>
    </div>
    <script>
      function filtra(chiave, valore) {{
        const u = new URL(location.href);
        if (valore) u.searchParams.set(chiave, valore);
        else u.searchParams.delete(chiave);
        location.href = u;
      }}

      const FILTRI_PAGINA = {json.dumps(filtri, ensure_ascii=False)};

      function escHtml(v) {{
        return (v === null || v === undefined ? '' : String(v))
          .replace(/&/g, '&amp;').replace(/</g, '&lt;')
          .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }}
      function euroFmt(v) {{
        return (Math.abs(v)).toLocaleString('it-IT', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
      }}
      function dataItFmt(iso) {{
        if (!iso) return '';
        const [y, m, d] = iso.slice(0, 10).split('-');
        return `${{d}}/${{m}}/${{y}}`;
      }}

      async function apriDettaglio(extra) {{
        const box = document.getElementById('dettaglioBox');
        const corpo = document.getElementById('dettaglioCorpo');
        const titolo = document.getElementById('dettaglioTitolo');
        box.style.display = 'block';
        box.scrollIntoView({{behavior: 'smooth', block: 'nearest'}});
        corpo.innerHTML = '<p class="small muted">Carico…</p>';

        const params = new URLSearchParams();
        const uniti = Object.assign({{}}, FILTRI_PAGINA, extra);
        for (const [k, v] of Object.entries(uniti)) {{
          if (v !== null && v !== undefined && v !== '') params.set(k, v);
        }}
        const pezzi = [];
        if (uniti.tipo) pezzi.push(uniti.tipo === 'entrata' ? 'entrate' : 'uscite');
        if (uniti.categoria) pezzi.push(uniti.categoria);
        if (uniti.sottocategoria) pezzi.push(uniti.sottocategoria);
        titolo.textContent = pezzi.length ? 'Come viene calcolato — ' + pezzi.join(' › ')
                                          : 'Come viene calcolato — tutti i movimenti';

        try {{
          const r = await fetch('/spese/api/movimenti/dettaglio?' + params.toString());
          const righe = await r.json();
          if (!Array.isArray(righe)) {{
            corpo.innerHTML = '<div class="notice err">' + escHtml(righe.error || 'Errore') + '</div>';
            return;
          }}
          if (!righe.length) {{
            corpo.innerHTML = '<p class="small muted">Nessun movimento per questi filtri.</p>';
            return;
          }}
          let tot = 0;
          const trs = righe.map(rg => {{
            const imp = Number(rg.importo) || 0;
            tot += rg.tipo === 'uscita' ? -imp : imp;
            const cat = escHtml(rg.categoria || '—') +
              (rg.sottocategoria ? ' › ' + escHtml(rg.sottocategoria) : '');
            return `<tr>
              <td>${{dataItFmt(rg.data)}}</td>
              <td>${{escHtml((rg.descrizione || '—').slice(0, 50))}}</td>
              <td>${{rg.tipo === 'entrata' ? 'Entrata' : 'Uscita'}}</td>
              <td>${{cat}}</td>
              <td class="num">€ ${{euroFmt(imp)}}</td>
            </tr>`;
          }}).join('');
          corpo.innerHTML = `
            <div style="overflow-x:auto">
            <table class="table">
              <thead><tr><th>Data</th><th>Descrizione</th><th>Tipo</th><th>Categoria</th><th class="num">Importo</th></tr></thead>
              <tbody>${{trs}}</tbody>
              <tfoot><tr><td colspan="4">Totale (${{righe.length}} movimenti) — deve combaciare col numero sopra</td>
                <td class="num">€ ${{(tot < 0 ? '−' : '')}}${{euroFmt(tot)}}</td></tr></tfoot>
            </table>
            </div>`;
        }} catch (e) {{
          corpo.innerHTML = '<div class="notice err">Errore rete: ' + escHtml(e.message) + '</div>';
        }}
      }}

      function chiudiDettaglio() {{
        document.getElementById('dettaglioBox').style.display = 'none';
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
    # "Giroconto P.IVA" non e' una scelta libera: la crea solo il giroconto
    # automatico (fatture/giroconto.py), apposta perche' v_periodi_stipendio
    # apre un nuovo periodo su ogni entrata con questa categoria — assegnarla
    # a un rimborso o un regalo qualunque sposterebbe un confine di periodo
    # senza che nulla lo segnali. Resta nel menu solo se e' gia' quella del
    # movimento aperto (mostrata disabilitata, non e' comunque modificabile
    # da qui: vedi il blocco su `collegato` piu' sotto).
    albero_scelta = [g for g in albero
                     if g["categoria"] != D.CATEGORIA_GIROCONTO
                     or g["categoria"] == cat_corrente]
    cat_opts = "".join(
        f'<option value="{_esc(g["categoria"])}"'
        f'{" selected" if g["categoria"] == cat_corrente else ""}>'
        f'{_esc(g["categoria"])}</option>' for g in albero_scelta)

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
          {"".join(f'<option value="{_esc(mp)}">' for mp in D.METODI_PAGAMENTO)}
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
      const ALBERO = {json.dumps(albero_scelta, ensure_ascii=False)};
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


def _filtri_da_query() -> dict:
    return dict(
        anno=request.args.get("anno", type=int),
        mese=request.args.get("mese", type=int),
        tipo=request.args.get("tipo") or None,
        categoria=request.args.get("categoria") or None,
        sottocategoria=request.args.get("sottocategoria") or None,
        metodo=request.args.get("metodo") or None,
        importo_min=request.args.get("importo_min", type=float),
        importo_max=request.args.get("importo_max", type=float),
        cerca=request.args.get("q") or None,
    )


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


@spese_bp.get("/api/movimenti/dettaglio")
def api_movimenti_dettaglio():
    """
    Come `/api/movimenti`, ma senza il tetto di 300: serve al drill-down
    "come viene calcolato" di /spese/movimenti, dove la somma mostrata in
    tabella deve combaciare esattamente col numero cliccato — un elenco
    troncato darebbe un totale diverso da quello che lo ha generato.
    """
    client, err = _client_o_503()
    if err:
        return err
    return jsonify(D.righe_periodo(client, **_filtri_da_query()))


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
