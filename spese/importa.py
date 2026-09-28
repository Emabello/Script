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
  2. Rivedi nel pannello comune (shared/importazione.py): doppioni gia'
     segnati, categoria proposta dallo storico (shared/suggerimenti.py),
     modifiche riga per riga o in blocco -> POST /spese/api/importa/salva:
     scrive solo le righe selezionate e con categoria.

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
from shared import importazione as IM
from shared import suggerimenti as SG
from shared.ordina import ordina
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

    # I pagamenti con carta. L'estratto li ha scritti in due modi negli
    # anni: "pagamento con carta ... digit-16:23-esercente" e, da giugno
    # 2026, "pagamento con carta - carta *2058-esercente  milano  mi  ita".
    # Il secondo non era riconosciuto e finiva a database cosi' com'era,
    # quindi lo stesso McDonald's aveva due descrizioni diverse — e il
    # controllo sui doppioni, che confronta le descrizioni, non vedeva piu'
    # lo stesso movimento riscaricato. Si tiene solo l'esercente e la citta'.
    m = re.match(r"(?:pagamento con carta|pagamento internet|spesa pagobancomat)\s*-?\s*"
                 r"carta\s*(?:visa)?\s*\*?\s*\d+(?:\s*visa)?(?:\s*digit)?\s*-"
                 r"(?:\d{1,2}:\d{2}-)?(.+)$", txt)
    if m:
        merch = re.sub(r"\s+", " ", m.group(1)).strip(" -")
        merch = re.sub(r"\s+-da contab\w*$", "", merch)
        merch = re.sub(r"(\s+(it|ita|ie|fr|de|es|uk|us|nl|at|ch|it a|i))+\s*$", "", merch)
        merch = re.sub(r"\s+mi$", "", merch).strip()
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
    # La data valuta, quando c'e'. Non e' quella che si salva (si salva la
    # contabile, come sempre), ma serve a riconoscere i movimenti gia'
    # registrati: in passato alcuni sono entrati con una data e alcuni con
    # l'altra, e lo stesso Iper del 08/07 (valuta) e del 09/07 (contabile)
    # sembrava due spese diverse.
    idx_valuta = trova("data valuta")
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

        valuta = None
        if idx_valuta is not None and idx_valuta < len(row):
            v_raw = row[idx_valuta]
            if isinstance(v_raw, datetime):
                valuta = v_raw.date().isoformat()
            elif isinstance(v_raw, date):
                valuta = v_raw.isoformat()
            elif isinstance(v_raw, str):
                try:
                    valuta = datetime.strptime(v_raw.strip(), "%d/%m/%Y").date().isoformat()
                except ValueError:
                    valuta = None
        out.append({
            "data": d.isoformat(),
            "data_valuta": valuta if valuta != d.isoformat() else None,
            "tipo": "entrata" if imp > 0 else "uscita",
            "importo": round(abs(imp), 2),
            "descrizione": clean_bank_description(raw_desc),
            "descrizione_raw": raw_desc[:200],
        })

    out.sort(key=lambda x: x["data"])
    return {"movimenti": out, "scartate": scartate, "motivi": motivi,
            "colonna_data_incerta": colonna_data_incerta}


# ---------------------------------------------------------------------------
# Pagina e API — il pannello di revisione e' quello comune
# (shared/importazione.py), identico per WeBank personale, P.IVA e Revolut
# ---------------------------------------------------------------------------

def _voci(client) -> list[dict]:
    """
    Le categorie del conto personale per il pannello, come coppie
    (link, «Categoria › Sottocategoria»), in ordine alfabetico. Senza
    «Giroconto Revolut», che e' un movimento interno di Revolut.
    """
    voci = [{"valore": v["link_id"],
             "nome": v["categoria"] + (f' › {v["sottocategoria"]}' if v["sottocategoria"] else "")}
            for v in D.voci_categoria(client)
            if v["categoria"] != D.CATEGORIA_GIROCONTO_REVOLUT]
    return ordina(voci, per=lambda v: v["nome"])


def pagina_upload(titolo: str, spiega: str, accetta: str, url_leggi: str,
                  extra_html: str = "", dopo_lettura_js: str = "") -> str:
    """
    La card di caricamento, uguale sulle tre pagine di import: il file,
    «Leggi il file», e l'errore se non si legge. Dopo la lettura chiama
    `IMPORT.carica(j.movimenti, j.avvisi)` e poi `dopo_lettura_js`, dove
    la pagina aggiunge quello che e' solo suo (i saldi di Revolut).
    """
    return f'''
    <div class="card mb-3" id="cardUpload">
      <div class="card-head"><div class="eyebrow">{titolo}</div>
        <span class="chip">1 · leggi</span></div>
      <p class="small muted">{spiega} Non scrive niente finché non salvi:
        prima rivedi le righe qui sotto.</p>
      <div class="field mt-4">
        <label>Estratto (.xlsx)</label>
        <input type="file" id="f_file" class="input" accept="{accetta}">
      </div>
      <div class="actions">
        <button type="button" class="btn" id="btnLeggi" onclick="leggiFile()">Leggi il file</button>
      </div>
      <div class="notice err mt-3" id="errUpload" style="display:none"></div>
    </div>
    {extra_html}
    <script>
      async function leggiFile() {{
        const inp = document.getElementById('f_file');
        const err = document.getElementById('errUpload');
        const btn = document.getElementById('btnLeggi');
        err.style.display = 'none';
        if (!inp.files.length) {{ err.textContent = 'Scegli il file'; err.style.display = 'block'; return; }}
        const fd = new FormData();
        fd.append('file', inp.files[0]);
        btn.disabled = true; btn.textContent = 'Leggo…';
        try {{
          const r = await fetch('{url_leggi}', {{method: 'POST', body: fd}});
          const j = await r.json();
          if (!r.ok) {{ err.textContent = j.error || 'Errore'; err.style.display = 'block'; return; }}
          IMPORT.carica(j.movimenti || [], j.avvisi || []);
          {dopo_lettura_js}
        }} catch (e) {{
          err.textContent = 'Errore rete: ' + e.message; err.style.display = 'block';
        }} finally {{
          btn.disabled = false; btn.textContent = 'Leggi il file';
        }}
      }}
    </script>'''


@spese_bp.get("/conti/webank/personale/importa")
def importa_pagina():
    breadcrumb = [("Conti", "/conti"), ("WeBank Personale", "/conti/webank/personale"),
                  ("Importa da banca", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb)
    body = pagina_upload(
        "Importa l'estratto WeBank",
        "Il file .xlsx esportato da WeBank (colonne Data Contabile, Importo, "
        "Causale o Descrizione).", ".xlsx,.xls", "/spese/api/importa/carica")
    body += IM.pannello(_voci(client), "/spese/api/importa/salva", obbligatoria=True)
    body += '<div id="toast" class="toast"></div>'
    return _render(body, breadcrumb)


def _esistenti(client, righe: list[dict]) -> list[dict]:
    """I movimenti gia' a database negli anni del file, piu' quello prima e dopo."""
    anni = {int(str(r.get("data"))[:4]) for r in righe
            if str(r.get("data") or "")[:4].isdigit()}
    anni |= {a - 1 for a in anni} | {a + 1 for a in anni}
    out = []
    for anno in sorted(anni):
        out.extend(D.righe_periodo(client, anno=anno))
    return out


@spese_bp.post("/spese/api/importa/carica")
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

    righe = esito["movimenti"]
    avvisi = []
    if esito["scartate"]:
        avvisi.append({"classe": "warn", "testo":
            f'{esito["scartate"]} righe del file non sono state lette (data o importo '
            f'non riconosciuti)' + (f': {"; ".join(esito["motivi"])}' if esito["motivi"] else "") + "."})
    if esito["colonna_data_incerta"]:
        avvisi.append({"classe": "warn", "testo":
            "Colonna «Data Contabile» non trovata: sto usando la prima colonna del file, "
            "controlla che le date siano giuste."})

    # Doppioni e proposte chiedono il database. Se non risponde si tira
    # dritto: un avviso in meno, non un import bloccato.
    client = D.sb()
    if client is not None:
        try:
            esistenti = _esistenti(client, righe)
            conti = IM.segna_doppioni(esistenti, righe)
            ammesse = {v["valore"] for v in _voci(client)}
            proposte = IM.proponi(SG.storico_personale(client), righe, ammesse)
            storni = IM.accoppia_storni(righe, esistenti)
            if conti["presenti"]:
                avvisi.append({"testo": f'{conti["presenti"]} righe sono già registrate: '
                                        f'restano spente e non si salvano.'})
            if conti["sospetti"]:
                avvisi.append({"classe": "warn", "testo":
                    f'{conti["sospetti"]} righe somigliano a movimenti già registrati con '
                    f'un\'altra data: sono spente, riaccendile se sono movimenti nuovi.'})
            if proposte:
                avvisi.append({"testo": f"{proposte} righe hanno già la categoria, "
                                        f"proposta dallo storico."})
            if storni:
                avvisi.append({"testo": f"{storni} storni hanno la categoria della spesa "
                                        f"che annullano."})
        except Exception:
            pass
    return jsonify({"movimenti": righe, "avvisi": avvisi})


@spese_bp.post("/spese/api/importa/salva")
def api_importa_salva():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    body = request.get_json(silent=True)
    righe = body.get("righe") if isinstance(body, dict) else None
    if not isinstance(righe, list) or not righe:
        return jsonify({"error": "nessuna riga da salvare"}), 400
    righe = [r for r in righe if isinstance(r, dict)]

    # Il controllo sui doppioni si ripete qui, sullo stato del database di
    # ADESSO: fra la lettura e il salvataggio puo' essere passato un altro
    # import. Stessa regola del pannello: conta le copie.
    esistenti = _esistenti(client, righe)
    for r in righe:
        r.pop("presente", None)
    IM.segna_doppioni(esistenti, righe)

    validi = {v["valore"] for v in _voci(client)}
    salvate, errori, duplicati = [], [], []
    for r in righe:
        idx = r.get("idx")
        if r.get("presente"):
            duplicati.append({"idx": idx, "nota": "già registrato"})
            continue
        link = r.get("categoria")
        if not link:
            errori.append({"idx": idx, "errore": "categoria mancante"})
            continue
        if link not in validi:
            errori.append({"idx": idx, "errore": "categoria non valida"})
            continue
        esito = D.crea(client, {
            "data":              r.get("data"),
            "tipo":              r.get("tipo"),
            "importo":           r.get("importo"),
            "descrizione":       r.get("descrizione"),
            "metodo_pagamento":  "Import banca",
            "categoria_link_id": link,
        })
        if esito.get("error") or not esito.get("id"):
            errori.append({"idx": idx, "errore": esito.get("error") or "errore sconosciuto"})
        else:
            salvate.append(idx)

    # I movimenti di giroconto appena importati sono il lato vero di una
    # ripartizione: vanno agganciati alla loro fattura, altrimenti la
    # fattura continua a dire "in attesa" mentre i soldi sono gia' sul
    # conto (vedi `fatture/giroconto.py`). Import qui dentro e non in
    # testa: `spese` e `fatture` sono due blueprint indipendenti.
    agganciati = 0
    if salvate:
        try:
            from fatture import giroconto as giro
            agganciati = giro.riconcilia_tutte(client)
        except Exception:
            agganciati = 0

    return jsonify({"salvate": salvate, "errori": errori,
                    "duplicati": duplicati, "agganciati": agganciati})


@spese_bp.get("/spese/api/suggerisci")
def api_suggerisci():
    """
    La categoria proposta per un movimento scritto a mano, dallo stesso
    motore dell'import (shared/suggerimenti.py). `conto` = personale,
    revolut o piva. Risponde {} se non c'e' niente di abbastanza simile.
    """
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    conto = request.args.get("conto") or "personale"
    if conto not in ("personale", "revolut", "piva"):
        return jsonify({"error": "conto non valido"}), 400
    try:
        importo = abs(float(request.args.get("importo") or 0))
    except ValueError:
        importo = 0.0
    tipo = request.args.get("tipo") or None
    if conto == "piva":
        from fatture.costanti import CATEGORIE_SPESE_PIVA
        ammesse = {k for k, _l in CATEGORIE_SPESE_PIVA}
        # Sul conto P.IVA il form ha anche il tipo «giroconto»: nello
        # storico e' un'uscita.
        tipo = "uscita" if tipo == "giroconto" else tipo
    else:
        # Le stesse esclusioni dei menu dei due form: sul personale il
        # «Giroconto P.IVA» non si sceglie a mano (lo crea la ripartizione,
        # e apre un periodo di risparmio), il «Giroconto Revolut» non esiste.
        escluse = ((D.CATEGORIA_GIROCONTO_REVOLUT, D.CATEGORIA_GIROCONTO)
                   if conto == "personale" else (D.CATEGORIA_GIROCONTO,))
        voci = [v for v in D.voci_categoria(client) if v["categoria"] not in escluse]
        ammesse = {v["link_id"] for v in voci}
        per_link = {v["link_id"]: v for v in voci}
    storico = SG.storico_pronto(client, conto)
    descrizione = request.args.get("descrizione")
    p = storico.suggerisci(descrizione, importo, tipo, ammesse)
    # Anche la direzione: se con il tipo scelto nel form non c'e' niente
    # di simile, ma senza vincolo di tipo si' — «Bonifico da Sileron» e'
    # sempre stato un'entrata —, si propone il tipo insieme alla categoria.
    tipo_suggerito = None
    if tipo:
        libero = storico.suggerisci(descrizione, importo, None, ammesse)
        if libero and libero.get("tipo") and libero["tipo"] != tipo and (
                not p or libero["fiducia"] > p["fiducia"]):
            p, tipo_suggerito = libero, libero["tipo"]
    if not p:
        return jsonify({})
    out = {"nome": p["nome"], "fiducia": p["fiducia"], "sicura": p["sicura"],
           "motivo": p["motivo"], "valore": p["etichetta"]}
    if tipo_suggerito:
        out["tipo"] = tipo_suggerito
    if conto == "piva":
        out["categoria"] = p["etichetta"]
    else:
        v = per_link.get(p["etichetta"]) or {}
        out["categoria"] = v.get("categoria")
        out["sottocategoria"] = v.get("sottocategoria")
    return jsonify(out)


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="conti-personale", eyebrow="Importa",
                                title_html='Importa da <em>banca</em>',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
