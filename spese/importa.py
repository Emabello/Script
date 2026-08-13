"""
spese/importa.py — Import massivo da estratto conto (xlsx).

Porta la logica di bank_import.py (client desktop separato, PyQt): stessa
euristica di riconoscimento colonne e di pulizia delle causali bancarie,
ma senza le dipendenze desktop — openpyxl al posto di pandas (già una
dipendenza dell'app, usata per l'export Excel in fatture/fiscale.py),
niente PyQt.

Flusso in due passi, tutto su questa pagina, niente scritto finché non
confermi:
  1. Carica il file -> POST /spese/api/importa/carica: legge e ripulisce
     le righe, le ritorna al client. Nessuna scrittura.
  2. Rivedi, assegna categoria/sottocategoria (riga per riga o in blocco
     sulle selezionate) -> POST /spese/api/importa/salva: scrive solo le
     righe selezionate e con categoria assegnata.

Rotte HTML:
  GET  /spese/importa

Rotte JSON:
  POST /spese/api/importa/carica   (multipart: file)
  POST /spese/api/importa/salva    (json: {righe: [...]})
"""
import json
import re
from datetime import date, datetime
from io import BytesIO

import openpyxl
from flask import Response, jsonify, request

from . import dati as D
from . import spese_bp
from shared.theme import render_page


# ---------------------------------------------------------------------------
# Pulizia descrizioni banca — stessa logica di bank_import.py: solo
# manipolazione di stringhe, nessuna dipendenza da portare.
# ---------------------------------------------------------------------------

def clean_bank_description(s: str) -> str:
    if not s:
        return ""
    raw = str(s).strip()
    txt = raw.lower()

    m = re.match(r"pagamento con carta.*?digit-\d{1,2}:\d{2}-(.+)$", txt)
    if m:
        merch = m.group(1).strip()
        merch = re.sub(r"\s+(it|ie|fr|de|es|uk|us|nl|at|ch)\s*$", "", merch).strip()
        return merch.title()

    m = re.match(r"bon\.da\s+(.+?)\s+nr\.?\s+bonifico", txt)
    if m:
        return f"Bonifico da {m.group(1).strip().title()}"

    m = re.search(r"favore\s+(.+?)(?:\s+notprovide|\s{2,}|\s*$)", txt)
    if m:
        return f"Bonifico a favore di {m.group(1).strip().title()}"

    m = re.match(r"addebito diretto sdd.*?\s([a-z][a-z\s\.\-]+)$", txt)
    if m:
        return f"SDD {m.group(1).strip().title()}"

    return raw[:80]


# ---------------------------------------------------------------------------
# Parsing xlsx — stessa euristica di bank_import.py sulle intestazioni
# (Data Contabile / Importo / Causale o Descrizione), con openpyxl.
# ---------------------------------------------------------------------------

def _numero_bancario(v) -> float | None:
    """
    Un importo puo' arrivare come numero (cella formattata) o come testo
    con virgola decimale ("1.234,56" — capita quando il file passa da un
    altro strumento prima di arrivare qui). float() da solo capisce solo
    il punto: prova prima cosi' com'e', poi convertendo alla notazione
    con il punto, prima di arrendersi.
    """
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        pulito = v.strip().replace(".", "").replace(",", ".")
        try:
            return float(pulito)
        except ValueError:
            return None
    return None


def parse_bank_xlsx(file_bytes: bytes) -> dict:
    """
    Ritorna {"movimenti": [...], "scartate": n, "motivi": [...],
    "colonna_data_incerta": bool}. Le righe scartate (data/importo non
    riconosciuti) prima sparivano senza traccia: chi importava vedeva solo
    "N movimenti caricati" e non aveva modo di sapere se il numero fosse
    completo o mancasse qualcosa rispetto al file originale.
    """
    wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.active
    righe = ws.iter_rows(values_only=True)
    try:
        intestazione = next(righe)
    except StopIteration:
        return {"movimenti": [], "scartate": 0, "motivi": [], "colonna_data_incerta": False}

    nomi = [str(c or "").strip().lower() for c in intestazione]

    def trova(*pattern):
        for i, h in enumerate(nomi):
            if any(p in h for p in pattern):
                return i
        return None

    idx_data = trova("data contabile")
    colonna_data_incerta = idx_data is None
    if idx_data is None:
        idx_data = 0
    idx_imp = trova("importo")
    idx_desc = trova("causale", "descrizione")
    if idx_imp is None or idx_desc is None:
        raise ValueError(
            "Formato file non riconosciuto. Servono colonne 'Data Contabile', "
            "'Importo' e 'Causale' o 'Descrizione'."
        )

    out = []
    scartate = 0
    motivi: list[str] = []

    def scarta(motivo: str):
        nonlocal scartate
        scartate += 1
        if len(motivi) < 10:  # basta un campione, non tutte le righe uguali
            motivi.append(motivo)

    for n_riga, row in enumerate(righe, start=2):  # 2: la 1 e' l'intestazione
        if not row or idx_data >= len(row):
            scarta(f"riga {n_riga}: vuota")
            continue
        d_raw = row[idx_data]
        if d_raw is None:
            scarta(f"riga {n_riga}: data mancante")
            continue
        d = None
        if isinstance(d_raw, datetime):
            d = d_raw.date()
        elif isinstance(d_raw, date):
            d = d_raw
        elif isinstance(d_raw, str):
            try:
                d = datetime.strptime(d_raw.strip(), "%d/%m/%Y").date()
            except ValueError:
                scarta(f"riga {n_riga}: data '{d_raw}' non in formato gg/mm/aaaa")
                continue
        if d is None:
            scarta(f"riga {n_riga}: data non riconosciuta")
            continue

        imp_raw = row[idx_imp] if idx_imp < len(row) else None
        imp = _numero_bancario(imp_raw)
        if imp is None:
            scarta(f"riga {n_riga}: importo '{imp_raw}' non numerico")
            continue

        raw_desc = row[idx_desc] if idx_desc < len(row) else ""
        raw_desc = "" if raw_desc is None else str(raw_desc)

        out.append({
            "data": d.isoformat(),
            "tipo": "entrata" if imp > 0 else "uscita",
            "importo": round(abs(imp), 2),
            "descrizione": clean_bank_description(raw_desc),
            "descrizione_raw": raw_desc[:200],
        })

    out.sort(key=lambda x: x["data"])
    return {"movimenti": out, "scartate": scartate, "motivi": motivi,
            "colonna_data_incerta": colonna_data_incerta}


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@spese_bp.get("/importa")
def importa_pagina():
    breadcrumb = [("Spese", "/spese"), ("Movimenti", "/spese/movimenti"),
                  ("Importa da banca", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb)

    albero = D.albero_categorie(client)
    cat_opts = "".join(
        f'<option value="{_esc(g["categoria"])}">{_esc(g["categoria"])}</option>'
        for g in albero
    )

    body = f'''
    <div class="card" id="cardUpload">
      <div class="card-head"><div class="eyebrow">Importa da estratto conto</div></div>
      <p class="small muted">
        Carica il file .xlsx esportato dalla banca (colonne Data Contabile,
        Importo, Causale o Descrizione — export Webank). Non scrive nulla
        finché non confermi: prima rivedi e assegni una categoria a ogni riga.
      </p>
      <div class="field mt-4">
        <label>File movimenti (.xlsx)</label>
        <input type="file" id="f_file" class="input" accept=".xlsx,.xls">
      </div>
      <div class="actions">
        <button type="button" class="btn" onclick="onCarica()">Carica file</button>
      </div>
      <div class="notice err" id="uploadErr" style="display:none"></div>
    </div>

    <div id="cardRevisione" style="display:none">
      <div class="notice warn mb-3" id="scartateNotice" style="display:none"></div>
      <div class="card mb-3">
        <div class="card-head"><div class="eyebrow">Applica a selezionate</div></div>
        <div class="field-group">
          <div class="field"><label>Categoria</label>
            <select id="bulk_cat" class="input" onchange="aggiornaBulkSub()">
              <option value="">—</option>{cat_opts}
            </select></div>
          <div class="field"><label>Sottocategoria</label>
            <select id="bulk_sub" class="input"><option value="">—</option></select></div>
        </div>
        <div class="actions">
          <button type="button" class="btn ghost" onclick="applicaBulk()">Applica alle selezionate</button>
          <button type="button" class="btn ghost" onclick="selezionaTutto(true)">Seleziona tutto</button>
          <button type="button" class="btn ghost" onclick="selezionaTutto(false)">Deseleziona tutto</button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="eyebrow">Movimenti trovati</div>
          <span class="chip" id="conteggio"></span>
        </div>
        <p class="small muted">Scorri la tabella a destra per assegnare categoria
          e sottocategoria a ogni riga — o usa "Applica a selezionate" qui sopra
          per farlo in blocco.</p>
        <div class="scroll-x">
          <table class="table">
            <thead><tr>
              <th></th><th>Data</th><th>Tipo</th><th class="num">Importo</th>
              <th>Descrizione</th><th>Categoria</th><th>Sottocategoria</th>
            </tr></thead>
            <tbody id="corpoTabella"></tbody>
          </table>
        </div>
        <div class="actions mt-4">
          <button type="button" class="btn" id="btnSalva" onclick="onSalva()">Salva selezionate</button>
        </div>
      </div>
    </div>

    <div id="toast" class="toast"></div>
    <script>
      const ALBERO = {json.dumps(albero, ensure_ascii=False)};
      let MOVS = [];
      let RIGHE = [];  // stato per riga: {{selezionata, categoria, sottocategoria, salvata}}

      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 2600);
      }}

      function euro(v) {{
        return new Intl.NumberFormat('it-IT', {{minimumFractionDigits:2, maximumFractionDigits:2}}).format(v);
      }}

      function esc(s) {{
        const d = document.createElement('div'); d.textContent = s == null ? '' : s;
        return d.innerHTML;
      }}

      function subOptions(cat, selezionata) {{
        const g = ALBERO.find(x => x.categoria === cat);
        let out = '<option value="">—</option>';
        if (!g) return out;
        for (const v of g.voci) {{
          if (!v.sottocategoria) continue;
          const sel = v.sottocategoria === selezionata ? ' selected' : '';
          out += `<option value="${{esc(v.sottocategoria)}}"${{sel}}>${{esc(v.sottocategoria)}}</option>`;
        }}
        return out;
      }}

      function aggiornaBulkSub() {{
        document.getElementById('bulk_sub').innerHTML = subOptions(document.getElementById('bulk_cat').value, null);
      }}

      async function onCarica() {{
        const inp = document.getElementById('f_file');
        const errBox = document.getElementById('uploadErr');
        errBox.style.display = 'none';
        if (!inp.files.length) {{ toast('Scegli un file', 'err'); return; }}
        const fd = new FormData();
        fd.append('file', inp.files[0]);
        try {{
          const r = await fetch('/spese/api/importa/carica', {{method: 'POST', body: fd}});
          const j = await r.json();
          if (!r.ok) {{ errBox.textContent = j.error || 'Errore'; errBox.style.display = 'block'; return; }}
          MOVS = j.movimenti || [];
          if (!MOVS.length) {{ toast('Nessun movimento trovato nel file', 'err'); return; }}
          RIGHE = MOVS.map(() => ({{selezionata: true, categoria: '', sottocategoria: '', salvata: false}}));
          document.getElementById('cardUpload').style.display = 'none';
          document.getElementById('cardRevisione').style.display = 'block';
          renderTabella();
          // Righe scartate (data/importo non riconosciuti): prima
          // sparivano senza traccia, ora restano visibili finché non le
          // guardi — un conto che "quasi torna" è peggio di uno che non
          // torna per niente, perché non lo sospetti.
          const notice = document.getElementById('scartateNotice');
          if (j.scartate > 0 || j.colonna_data_incerta) {{
            const pezzi = [];
            if (j.scartate > 0) {{
              pezzi.push(`${{j.scartate}} riga/righe del file non ${{j.scartate === 1 ? 'è stata' : 'sono state'}} importata/e `
                + `(formato data o importo non riconosciuto)`
                + (j.motivi && j.motivi.length ? `: ${{j.motivi.join('; ')}}` : '') + '.');
            }}
            if (j.colonna_data_incerta) {{
              pezzi.push('Colonna "Data Contabile" non trovata nell\\'intestazione: '
                + 'sto usando la prima colonna del file, controlla che le date siano giuste.');
            }}
            notice.textContent = pezzi.join(' ');
            notice.style.display = 'block';
          }} else {{
            notice.style.display = 'none';
          }}
          toast(`${{MOVS.length}} movimenti caricati`, 'ok');
        }} catch (e) {{ errBox.textContent = 'Errore rete: ' + e.message; errBox.style.display = 'block'; }}
      }}

      function renderTabella() {{
        const tbody = document.getElementById('corpoTabella');
        tbody.innerHTML = MOVS.map((m, i) => {{
          const r = RIGHE[i];
          const cls = m.tipo === 'entrata' ? 'pos' : 'neg';
          const segno = m.tipo === 'entrata' ? '+' : '−';
          const dis = r.salvata ? 'disabled' : '';
          return `<tr>
            <td><input type="checkbox" data-i="${{i}}" ${{r.selezionata ? 'checked' : ''}} ${{dis}}
                  onchange="onChk(${{i}}, this.checked)"></td>
            <td class="tnum">${{m.data.split('-').reverse().join('/')}}</td>
            <td class="${{cls}}">${{m.tipo}}</td>
            <td class="num tnum ${{cls}}">${{segno}} € ${{euro(m.importo)}}</td>
            <td><input type="text" class="input" style="min-width:200px" value="${{esc(m.descrizione)}}"
                  ${{dis}} onchange="onDesc(${{i}}, this.value)"></td>
            <td><select class="input" style="min-width:150px" ${{dis}} onchange="onCat(${{i}}, this.value)">
                  <option value="">— scegli —</option>
                  ${{ALBERO.map(g => `<option value="${{esc(g.categoria)}}" ${{g.categoria === r.categoria ? 'selected' : ''}}>${{esc(g.categoria)}}</option>`).join('')}}
                </select></td>
            <td><select class="input sel-sub" style="min-width:150px" data-i="${{i}}" ${{dis}}
                  onchange="onSub(${{i}}, this.value)">${{subOptions(r.categoria, r.sottocategoria)}}</select></td>
            ${{r.salvata ? '<td class="pos small">✔ salvato</td>' : ''}}
          </tr>`;
        }}).join('');
        aggiornaConteggio();
      }}

      function onChk(i, val) {{ RIGHE[i].selezionata = val; aggiornaConteggio(); }}
      function onDesc(i, val) {{ MOVS[i].descrizione = val; }}
      function onCat(i, val) {{
        RIGHE[i].categoria = val; RIGHE[i].sottocategoria = '';
        const sub = document.querySelector(`.sel-sub[data-i="${{i}}"]`);
        if (sub) sub.innerHTML = subOptions(val, null);
        aggiornaConteggio();
      }}
      function onSub(i, val) {{ RIGHE[i].sottocategoria = val; }}

      function selezionaTutto(on) {{
        RIGHE.forEach((r) => {{ if (!r.salvata) r.selezionata = on; }});
        renderTabella();
      }}

      function applicaBulk() {{
        const cat = document.getElementById('bulk_cat').value;
        if (!cat) {{ toast('Scegli una categoria da applicare', 'err'); return; }}
        const sub = document.getElementById('bulk_sub').value;
        RIGHE.forEach((r) => {{ if (r.selezionata && !r.salvata) {{ r.categoria = cat; r.sottocategoria = sub; }} }});
        renderTabella();
      }}

      function aggiornaConteggio() {{
        const sel = RIGHE.filter(r => r.selezionata && !r.salvata).length;
        const conCat = RIGHE.filter(r => r.selezionata && !r.salvata && r.categoria).length;
        document.getElementById('conteggio').textContent = `${{sel}} selezionate · ${{conCat}} con categoria`;
      }}

      async function onSalva() {{
        const daSalvare = [];
        RIGHE.forEach((r, i) => {{
          if (r.selezionata && !r.salvata && r.categoria) {{
            daSalvare.push({{
              idx: i, data: MOVS[i].data, tipo: MOVS[i].tipo, importo: MOVS[i].importo,
              descrizione: MOVS[i].descrizione, categoria: r.categoria,
              sottocategoria: r.sottocategoria || null,
            }});
          }}
        }});
        if (!daSalvare.length) {{ toast('Nessuna riga pronta: seleziona e assegna una categoria', 'err'); return; }}
        if (!confirm(`Salvare ${{daSalvare.length}} movimenti su Spese?`)) return;

        const btn = document.getElementById('btnSalva');
        btn.disabled = true;
        try {{
          const r = await fetch('/spese/api/importa/salva', {{
            method: 'POST', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{righe: daSalvare}}),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); btn.disabled = false; return; }}
          (j.salvate || []).forEach(idx => {{ RIGHE[idx].salvata = true; }});
          renderTabella();
          toast(`${{(j.salvate || []).length}} movimenti salvati`, 'ok');
          if (j.duplicati && j.duplicati.length) {{
            toast(`${{j.duplicati.length}} righe già presenti, non duplicate`, 'ok');
          }}
          if (j.errori && j.errori.length) {{
            toast(`${{j.errori.length}} righe non salvate — vedi console`, 'err');
            console.warn('Righe non salvate:', j.errori);
          }}
        }} catch (e) {{ toast('Errore rete: ' + e.message, 'err'); }}
        btn.disabled = false;
      }}
    </script>'''

    return _render(body, breadcrumb)


@spese_bp.post("/api/importa/carica")
def api_importa_carica():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "nessun file caricato"}), 400
    try:
        esito = parse_bank_xlsx(f.read())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"file non leggibile: {str(e)[:200]}"}), 400
    return jsonify(esito)


def _righe_gia_presenti(client, righe: list[dict]) -> set[tuple]:
    """
    (data, importo, descrizione) dei movimenti gia' in `spese` negli anni
    coperti dalle righe da salvare — per accorgersi se lo stesso estratto
    conto (o una sua parte, le banche includono qualche giorno di margine
    fra un export e il successivo) e' gia' stato importato prima.
    """
    date_valide = [r.get("data") for r in righe if r.get("data")]
    if not date_valide:
        return set()
    anni = {int(d[:4]) for d in date_valide if len(d) >= 4 and d[:4].isdigit()}
    esistenti: set[tuple] = set()
    for anno in anni:
        for riga in D.righe_periodo(client, anno=anno):
            esistenti.add((
                riga.get("data"),
                round(float(riga.get("importo") or 0), 2),
                (riga.get("descrizione") or "").strip(),
            ))
    return esistenti


@spese_bp.post("/api/importa/salva")
def api_importa_salva():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    body = request.get_json(silent=True) or {}
    righe = body.get("righe") or []
    if not righe:
        return jsonify({"error": "nessuna riga da salvare"}), 400

    gia_presenti = _righe_gia_presenti(client, righe)

    salvate, errori, duplicati = [], [], []
    for r in righe:
        idx = r.get("idx")
        cat = (r.get("categoria") or "").strip()
        sub = (r.get("sottocategoria") or "").strip() or None
        if not cat:
            errori.append({"idx": idx, "errore": "categoria mancante"})
            continue
        chiave = (r.get("data"), round(float(r.get("importo") or 0), 2),
                 (r.get("descrizione") or "").strip())
        if chiave in gia_presenti:
            duplicati.append(idx)
            continue
        link_id = D.link_categoria(client, cat, sub)
        if link_id is None:
            errori.append({"idx": idx, "errore": f"combinazione '{cat}'/'{sub}' non valida"})
            continue
        esito = D.crea(client, {
            "data":              r.get("data"),
            "tipo":              r.get("tipo"),
            "importo":           r.get("importo"),
            "descrizione":       r.get("descrizione"),
            "metodo_pagamento":  "Import banca",
            "categoria_link_id": link_id,
        })
        if esito.get("error") or not esito.get("id"):
            errori.append({"idx": idx, "errore": esito.get("error") or "errore sconosciuto"})
        else:
            salvate.append(idx)
            # Anche nello stesso file possono esserci due righe identiche
            # (capita, alcune banche duplicano una transazione nell'export):
            # segnala la seconda come duplicato invece di scriverla due volte.
            gia_presenti.add(chiave)

    return jsonify({"salvate": salvate, "errori": errori, "duplicati": duplicati})


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="spese", eyebrow="Importa",
                                title_html='Importa da <em>banca</em>',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
