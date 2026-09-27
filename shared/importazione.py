"""
shared/importazione.py — L'import da estratto, uguale per tutti i conti.

PERCHE' UNO SOLO
----------------
WeBank personale, WeBank P.IVA e Revolut arrivano da tre file diversi, ma
dopo la lettura il lavoro e' lo stesso: guardare le righe, capire quali
sono gia' state salvate, dare una categoria a quelle nuove, salvarle.
Prima c'erano due pannelli scritti due volte, con due logiche diverse sui
doppioni e due modi diversi di scegliere la categoria — e uno dei due
buttava via il secondo di due caffe' identici nello stesso giorno.

Qui ci sono i pezzi comuni:

  * `segna_doppioni()` — quali righe del file sono gia' a database, e
    quali lo sembrano soltanto (stesso importo, pochi giorni di scarto);
  * `proponi()` — la categoria suggerita dallo storico
    (`shared/suggerimenti.py`), preselezionata solo quando e' sicura;
  * `pannello()` — la revisione, identica sulle tre pagine: stesso
    layout, stessi filtri, stesso «applica alle selezionate», stesso
    salvataggio.

Ogni pagina ci mette solo quello che e' suo: come si legge il file e dove
si salva.
"""
import json
from collections import Counter
from datetime import date

from .suggerimenti import CITTA_BASE, togli_citta
from .suggerimenti import chiave as chiave_descrizione

_CITTA = frozenset(CITTA_BASE)

# Quanti giorni di scarto rendono due movimenti uguali "sospetti". Serve
# solo a SEGNALARE, mai a scartare: tre caffe' da 1,10 in due giorni sono
# tre caffe' veri (vedi spese/importa.py, dove il valore e' nato).
TOLLERANZA_GIORNI = 4


def _num(v) -> float | None:
    try:
        return round(abs(float(v)), 2)
    except (TypeError, ValueError):
        return None


def _impronta(r: dict) -> tuple:
    """Data, tipo, importo e descrizione ripulita: lo stesso movimento
    riscaricato la ripete identica anche se la pulizia della descrizione
    e' cambiata nel frattempo (spazi, maiuscole, prefissi della carta)."""
    # Senza la citta' e la provincia in coda: la stessa spesa e' a database
    # come «…iper portello  milano  mi  ita» (descrizione grezza, prima che
    # l'import la ripulisse) e nel file nuovo come «Iper Portello Mil Ano».
    return (str(r.get("data") or "")[:10], r.get("tipo"),
            _num(r.get("importo")), _esercente(r.get("descrizione")))


def _esercente(descrizione) -> str:
    k = chiave_descrizione(descrizione)
    return togli_citta(k, _CITTA) or k


def _togli(rimasti: dict, impronta: tuple) -> None:
    """Consuma dall'indice del secondo passaggio la riga appena abbinata."""
    lista = rimasti.get(impronta[:3])
    if lista and impronta[3] in lista:
        lista.remove(impronta[3])


# Descrizioni che non nominano la controparte: l'export dei movimenti
# Revolut scrive «Revolut Bank UAB» dove il consolidato dice «Pagamento da
# parte di MARIO ROSSI». Non somigliano a niente, ma non smentiscono
# niente: stessa data, stessa direzione, stesso importo bastano.
_SENZA_NOME = {"revolutbankuab", "revolutbank"}   # nella forma di `_esercente`


def _stesso_movimento(rimasti: dict, r: dict, imp: tuple):
    """L'impronta della riga a database che e' questo movimento, o None."""
    from .suggerimenti import somiglianza, trigrammi
    anonimo = imp[3] in _SENZA_NOME
    for giorno in filter(None, (imp[0], r.get("data_valuta"))):
        lista = rimasti.get((giorno, imp[1], imp[2]))
        if not lista:
            continue
        for esercente in list(lista):
            if (imp[2] >= 100 or esercente == imp[3] or anonimo or esercente in _SENZA_NOME
                    or somiglianza(trigrammi(esercente), trigrammi(imp[3])) >= 0.75):
                lista.remove(esercente)
                return (giorno, imp[1], imp[2], esercente)
    return None


def segna_doppioni(esistenti: list[dict], righe: list[dict]) -> dict:
    """
    Marca le righe del file gia' presenti (`presente`) e quelle che lo
    sembrano (`sospetto`, con il perche'), e ritorna quante sono.

    **Conta le copie, non solo la presenza.** Due caffe' identici lo
    stesso giorno sono due righe identiche anche a database: il primo del
    file e' «gia' presente» se a database ce n'e' almeno uno, il secondo
    solo se ce ne sono almeno due. Il controllo di prima guardava un
    insieme — e un insieme ha un solo caffe' —, quindi il secondo caffe'
    di un file nuovo veniva scartato come doppione del primo, in silenzio.

    Una riga presente nasce spenta e non si salva; una sospetta nasce
    spenta ma si riaccende con un click: e' il file a sapere se sono due.
    """
    disponibili = Counter(_impronta(e) for e in esistenti)
    per_importo: dict[tuple, list] = {}
    for e in esistenti:
        chiave = (e.get("tipo"), _num(e.get("importo")))
        per_importo.setdefault(chiave, []).append(
            (str(e.get("data") or "")[:10], (e.get("descrizione") or "").strip()))

    # Secondo passaggio, per chi non ha l'impronta identica: lo stesso
    # movimento con la descrizione scritta in un altro modo. Stessa
    # direzione, stesso importo, stessa data (contabile o valuta), e in
    # piu' una descrizione molto simile («Lidl 1482 Novate Milane» e
    # «…novate milami», troncata dalla banca) oppure un importo da almeno
    # 100 € — due bonifici identici da 2.000,00 nello stesso giorno non
    # succedono, mentre due caffe' da 1,10 si'. Anche qui le copie si
    # consumano una per una.
    rimasti: dict = {}
    for e in esistenti:
        chiave = (str(e.get("data") or "")[:10], e.get("tipo"), _num(e.get("importo")))
        rimasti.setdefault(chiave, []).append(_esercente(e.get("descrizione")))
    presenti = sospetti = 0
    for r in righe:
        imp = _impronta(r)
        if imp[2] is None:
            continue            # importo illeggibile: lo dira' il salvataggio
        # La stessa impronta con la data valuta: l'estratto WeBank ne porta
        # due (contabile e valuta), e lo storico le ha usate entrambe.
        alt = ((r["data_valuta"],) + imp[1:]) if r.get("data_valuta") else None
        trovata = imp if disponibili[imp] > 0 else (
            alt if alt and disponibili[alt] > 0 else None)
        if trovata:
            disponibili[trovata] -= 1
            _togli(rimasti, trovata)
            r["presente"] = True
            r["nota"] = ("già registrato" if trovata == imp
                         else "già registrato con la data valuta")
            presenti += 1
            continue
        simile = _stesso_movimento(rimasti, r, imp)
        if simile:
            disponibili[simile] -= 1
            r["presente"] = True
            r["nota"] = "già registrato con un'altra descrizione"
            presenti += 1
            continue
        try:
            giorno = date.fromisoformat(str(r.get("data") or "")[:10])
        except ValueError:
            continue
        vicini = []
        for d, desc in per_importo.get((r.get("tipo"), imp[2]), []):
            try:
                scarto = abs((date.fromisoformat(d) - giorno).days)
            except ValueError:
                continue
            if scarto <= TOLLERANZA_GIORNI:
                vicini.append((scarto, d, desc))
        if vicini:
            vicini.sort()
            scarto, d, desc = vicini[0]
            quando = "lo stesso giorno" if scarto == 0 else f"il {d[8:10]}/{d[5:7]}"
            r["sospetto"] = (f"somiglia a un movimento già registrato {quando}"
                             + (f" («{desc[:36]}»)" if desc else ""))
            sospetti += 1
    return {"presenti": presenti, "sospetti": sospetti}


def proponi(storico, righe: list[dict], ammesse: set | None = None,
            campo: str = "categoria") -> int:
    """
    Aggiunge a ogni riga la categoria proposta dallo storico, e ritorna a
    quante righe e' stata assegnata.

    Una riga che ha gia' una categoria (la gemella WeBank di un bonifico
    Revolut, un interesse riconosciuto dalla sezione) la tiene: quelle
    sono fatti, lo storico e' una statistica. Una proposta non sicura
    resta visibile ma non si applica: si accetta con un click.
    """
    applicate = 0
    for r in righe:
        if r.get(campo):
            continue
        p = storico.suggerisci(r.get("descrizione"), r.get("importo"),
                               r.get("tipo"), ammesse)
        if not p:
            continue
        r["suggerimento"] = {"valore": p["etichetta"], "nome": p["nome"],
                             "fiducia": p["fiducia"], "motivo": p["motivo"],
                             "sicura": p["sicura"]}
        if p["sicura"]:
            r[campo] = p["etichetta"]
            applicate += 1
    return applicate


# ---------------------------------------------------------------------------
# Il pannello di revisione
# ---------------------------------------------------------------------------

def pannello(voci: list[dict], salva_url: str, obbligatoria: bool,
             dopo_salvataggio: str = "") -> str:
    """
    La revisione delle righe lette, uguale per ogni conto.

    `voci`: [{valore, nome}] in ordine alfabetico — le categorie
    selezionabili (il link `cfg_*`, o la chiave della P.IVA).
    `salva_url`: dove spedire {righe: [...]}; la risposta attesa e'
    {salvate: [idx], duplicati: [{idx, nota}], errori: [{idx, errore}]}.
    `obbligatoria`: se una riga senza categoria si puo' salvare. Sul
    conto personale no — un movimento senza categoria sparisce dal
    budget dei periodi (README §7) —; su Revolut si', e resta nell'elenco
    «da categorizzare».

    La pagina carica le righe con `IMPORT.carica(righe, avvisi)`.
    """
    return f'''
    <div id="revisione" style="display:none">
      <div class="card mb-3">
        <div class="card-head">
          <div class="eyebrow">Revisione</div>
          <span class="chip" id="impConteggio"></span>
        </div>
        <div id="impAvvisi"></div>
        <div class="toolbar mt-2" role="group" aria-label="Quali righe mostrare">
          <button type="button" class="btn ghost sm" data-filtro="tutte" onclick="IMPORT.filtro('tutte')">Tutte</button>
          <button type="button" class="btn ghost sm" data-filtro="senza" onclick="IMPORT.filtro('senza')">Senza categoria</button>
          <button type="button" class="btn ghost sm" data-filtro="incerte" onclick="IMPORT.filtro('incerte')">Proposte da confermare</button>
          <button type="button" class="btn ghost sm" data-filtro="sospette" onclick="IMPORT.filtro('sospette')">Sospette</button>
          <button type="button" class="btn ghost sm" data-filtro="presenti" onclick="IMPORT.filtro('presenti')">Già registrate</button>
        </div>
        <div class="field-group mt-3">
          <div class="field"><label>Categoria per le righe selezionate</label>
            <select id="impBulk" class="input" data-etichetta="Categoria" data-icona="🏷️">
              <option value="">—</option>
              {"".join(f'<option value="{_attr(v["valore"])}">{_esc(v["nome"])}</option>' for v in voci)}
            </select></div>
        </div>
        <div class="actions">
          <button type="button" class="btn ghost" onclick="IMPORT.applica()">Applica alle selezionate</button>
          <button type="button" class="btn ghost" onclick="IMPORT.accettaProposte()">Accetta tutte le proposte</button>
          <button type="button" class="btn ghost" onclick="IMPORT.seleziona(true)">Seleziona le visibili</button>
          <button type="button" class="btn ghost" onclick="IMPORT.seleziona(false)">Deseleziona</button>
        </div>
      </div>

      <div class="card">
        <p class="small muted">Le categorie proposte vengono dai movimenti che hai già
          categorizzato: stessa descrizione, importo uguale o multiplo. Quelle
          sicure sono già scelte; le altre si accettano con «usa». Cambiando la
          categoria di una riga, le righe con la stessa descrizione ancora vuote
          la prendono anche loro.
          {"Una riga senza categoria non si salva: sul conto personale sparirebbe dal budget dei periodi." if obbligatoria else "Una riga senza categoria si salva lo stesso e resta fra quelle «da categorizzare»."}</p>
        <div class="scroll-x">
          <table class="table imp-tab">
            <thead><tr>
              <th></th><th>Data</th><th class="num">Importo</th><th>Descrizione</th>
              <th>Categoria</th><th>Nota</th>
            </tr></thead>
            <tbody id="impCorpo"></tbody>
          </table>
        </div>
        <div class="actions mt-4">
          <button type="button" class="btn" id="impSalva" onclick="IMPORT.salva()">Salva le selezionate</button>
        </div>
      </div>
    </div>
    <style>
      .imp-tab td{{vertical-align:top}}
      .imp-tab .spenta{{opacity:.5}}
      .imp-tab .prop{{display:block;margin-top:4px}}
      .imp-tab select{{min-width:180px}} .imp-tab input.input{{min-width:220px}}
      [data-filtro].attivo{{background:var(--accent-soft);color:var(--accent-text)}}
    </style>
    <script>
    const IMPORT = (function () {{
      const VOCI = {json.dumps(voci, ensure_ascii=False)};
      const OBBLIGATORIA = {json.dumps(bool(obbligatoria))};
      const SALVA_URL = {json.dumps(salva_url)};
      let R = [];
      let FILTRO = 'tutte';
      const NOMI = new Map(VOCI.map(v => [String(v.valore), v.nome]));
      const OPZIONI = '<option value="">— da categorizzare —</option>' + VOCI.map(v =>
        '<option value="' + esc(v.valore) + '">' + esc(v.nome) + '</option>').join('');

      function esc(s) {{
        const d = document.createElement('div'); d.textContent = s == null ? '' : String(s);
        return d.innerHTML.replace(/"/g, '&quot;');
      }}
      function euro(v) {{
        return new Intl.NumberFormat('it-IT', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}).format(Number(v) || 0);
      }}
      function toastImp(msg, cls) {{
        const t = document.getElementById('toast');
        if (!t) return;
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(() => {{ t.className = 'toast ' + (cls || ''); }}, 3000);
      }}
      // La stessa chiave di shared/suggerimenti.py::chiave, abbastanza
      // da riconoscere le righe con la stessa descrizione.
      function chiave(s) {{
        return String(s || '').toLowerCase()
          .replace(/pagamento con carta|spesa pagobancomat|carta\\s*\\*?\\s*\\d+/g, ' ')
          .normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').replace(/[^a-z]/g, '');
      }}

      function carica(righe, avvisi) {{
        R = righe.map((r, i) => Object.assign({{}}, r, {{
          idx: i,
          scelta: r.presente ? false : !r.sospetto,
          categoria: r.categoria == null ? '' : String(r.categoria),
          toccata: false, salvata: false, _k: chiave(r.descrizione),
        }}));
        document.getElementById('impAvvisi').innerHTML = (avvisi || []).map(a =>
          '<div class="notice ' + (a.classe || 'info') + ' small mt-2">' + esc(a.testo) + '</div>').join('');
        document.getElementById('revisione').style.display = '';
        filtro(R.some(r => !r.presente) ? 'tutte' : 'presenti');
      }}

      function visibile(r) {{
        if (FILTRO === 'presenti') return r.presente;
        if (r.presente) return false;
        if (FILTRO === 'senza') return !r.categoria;
        if (FILTRO === 'incerte') return r.suggerimento && !r.suggerimento.sicura && !r.toccata;
        if (FILTRO === 'sospette') return !!r.sospetto;
        return true;
      }}

      function filtro(f) {{
        FILTRO = f;
        document.querySelectorAll('[data-filtro]').forEach(b =>
          b.classList.toggle('attivo', b.dataset.filtro === f));
        disegna();
      }}

      function riga(r) {{
        const entra = r.tipo === 'entrata';
        const blocco = r.presente || r.salvata;
        const s = r.suggerimento;
        let prop = '';
        if (s && !blocco && String(s.valore) !== r.categoria) {{
          prop = '<span class="prop small muted">proposta: ' + esc(s.nome) + ' (' +
            Math.round(s.fiducia * 100) + '%) <a href="#" onclick="IMPORT.usa(' + r.idx +
            ');return false">usa</a></span>';
        }} else if (s && !blocco) {{
          prop = '<span class="prop small muted" title="' + esc(s.motivo) + '">' + esc(s.motivo) + '</span>';
        }}
        const nota = r.salvata ? '<span class="pos">✔ salvato</span>'
          : esc(r.nota || r.sospetto || '');
        return '<tr data-i="' + r.idx + '" class="' + (blocco || !r.scelta ? 'spenta' : '') + '">' +
          '<td><input type="checkbox" aria-label="Seleziona" ' + (r.scelta ? 'checked ' : '') +
            (blocco ? 'disabled ' : '') + 'onchange="IMPORT.spunta(' + r.idx + ', this.checked)"></td>' +
          '<td class="tnum">' + r.data.split('-').reverse().join('/') + '</td>' +
          '<td class="num tnum ' + (entra ? 'pos' : 'neg') + '">' + (entra ? '+' : '−') + ' € ' + euro(r.importo) + '</td>' +
          '<td><input class="input" value="' + esc(r.descrizione) + '" ' + (blocco ? 'disabled ' : '') +
            'onchange="IMPORT.descrizione(' + r.idx + ', this.value)">' +
            (r.sezione ? '<span class="prop small muted">' + (r.sezione === 'risparmi' ? 'deposito' : 'liquidità') + '</span>' : '') + '</td>' +
          '<td><select class="input" data-nativo aria-label="Categoria" ' + (blocco ? 'disabled ' : '') +
            'onchange="IMPORT.categoria(' + r.idx + ', this.value)">' +
            OPZIONI.replace('value="' + esc(r.categoria) + '"', 'value="' + esc(r.categoria) + '" selected') +
            '</select>' + prop + '</td>' +
          '<td class="small muted">' + nota + '</td></tr>';
      }}

      // Le righe si disegnano a blocchi: un estratto dall'apertura del
      // conto ne ha piu' di mille, e mille tendine in un colpo solo
      // bloccano il telefono per un paio di secondi.
      let giro = 0;
      function disegna() {{
        const corpo = document.getElementById('impCorpo');
        const mie = R.filter(visibile);
        const questo = ++giro;
        corpo.innerHTML = '';
        let i = 0;
        (function blocco() {{
          if (questo !== giro) return;
          corpo.insertAdjacentHTML('beforeend', mie.slice(i, i + 150).map(riga).join(''));
          i += 150;
          if (i < mie.length) requestAnimationFrame(blocco);
        }})();
        conteggio();
      }}
      function ridisegna(r) {{
        const tr = document.querySelector('#impCorpo tr[data-i="' + r.idx + '"]');
        if (tr) tr.outerHTML = riga(r);
      }}

      function conteggio() {{
        const nuove = R.filter(r => !r.presente && !r.salvata);
        const scelte = nuove.filter(r => r.scelta);
        const pronte = scelte.filter(r => r.categoria || !OBBLIGATORIA);
        document.getElementById('impConteggio').textContent =
          nuove.length + ' nuove · ' + scelte.length + ' selezionate · ' +
          scelte.filter(r => r.categoria).length + ' con categoria';
        const b = document.getElementById('impSalva');
        b.disabled = !pronte.length;
        b.textContent = pronte.length ? 'Salva ' + pronte.length + ' movimenti' : 'Niente da salvare';
      }}

      function categoria(i, v, daPropagare) {{
        const r = R[i];
        r.categoria = v; r.toccata = true;
        if (v && !r.presente) r.scelta = true;
        ridisegna(r);
        if (daPropagare === false || !v) {{ conteggio(); return; }}
        // Le righe con la stessa descrizione e la stessa direzione, ancora
        // senza una scelta tua, prendono la stessa categoria.
        for (const x of R) {{
          if (x === r || x.toccata || x.presente || x.salvata) continue;
          if (x.tipo !== r.tipo || !x._k || x._k !== r._k) continue;
          x.categoria = v; x.toccata = true;
          ridisegna(x);
        }}
        conteggio();
      }}

      async function salva() {{
        const righe = R.filter(r => !r.presente && !r.salvata && r.scelta
                                     && (r.categoria || !OBBLIGATORIA));
        if (!righe.length) return;
        const sosp = righe.filter(r => r.sospetto).length;
        if (!confirm('Salvare ' + righe.length + ' movimenti?' +
                     (sosp ? '\\n\\n' + sosp + ' somigliano a movimenti già registrati.' : ''))) return;
        const b = document.getElementById('impSalva');
        b.disabled = true;
        // A blocchi da 100: il primo import di un conto sono mille righe,
        // e una richiesta sola durerebbe piu' del tempo massimo che il
        // server concede. Ogni blocco e' un salvataggio completo: se il
        // quarto fallisce, i primi tre restano salvati e segnati.
        const tot = {{salvate: 0, duplicati: 0, errori: 0}};
        try {{
          for (let k = 0; k < righe.length; k += 100) {{
            b.textContent = 'Salvo ' + Math.min(k + 100, righe.length) + ' di ' + righe.length + '…';
            const resp = await fetch(SALVA_URL, {{
              method: 'POST', headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify({{righe: righe.slice(k, k + 100).map(r => ({{
                idx: r.idx, data: r.data, tipo: r.tipo, importo: r.importo,
                descrizione: r.descrizione, categoria: r.categoria || null,
                chiave: r.chiave || null, sezione: r.sezione || null,
              }}))}}),
            }});
            const j = await resp.json();
            if (!resp.ok) {{ toastImp(j.error || 'Errore', 'err'); break; }}
            (j.salvate || []).forEach(i => {{ R[i].salvata = true; R[i].scelta = false; }});
            (j.duplicati || []).forEach(d => {{ R[d.idx].presente = true; R[d.idx].nota = d.nota || 'già registrato'; }});
            (j.errori || []).forEach(e => {{ R[e.idx].nota = 'non salvato: ' + e.errore; }});
            tot.salvate += (j.salvate || []).length;
            tot.duplicati += (j.duplicati || []).length;
            tot.errori += (j.errori || []).length;
          }}
          disegna();
          toastImp(tot.salvate + ' movimenti salvati' +
                   (tot.duplicati ? ', ' + tot.duplicati + ' già presenti' : '') +
                   (tot.errori ? ', ' + tot.errori + ' con errore' : ''),
                   tot.errori ? 'err' : 'ok');
          {dopo_salvataggio}
        }} catch (e) {{ toastImp('Errore rete: ' + e.message, 'err'); disegna(); }}
      }}

      return {{
        carica, filtro, salva,
        categoria: (i, v) => categoria(i, v),
        usa: i => categoria(i, String(R[i].suggerimento.valore)),
        spunta: (i, v) => {{ R[i].scelta = v; ridisegna(R[i]); conteggio(); }},
        descrizione: (i, v) => {{ R[i].descrizione = v; }},
        seleziona: on => {{ R.filter(visibile).forEach(r => {{ if (!r.presente && !r.salvata) r.scelta = on; }}); disegna(); }},
        applica: () => {{
          const v = document.getElementById('impBulk').value;
          if (!v) {{ toastImp('Scegli una categoria', 'err'); return; }}
          R.filter(r => r.scelta && !r.presente && !r.salvata && visibile(r))
           .forEach(r => {{ r.categoria = v; r.toccata = true; }});
          disegna();
        }},
        accettaProposte: () => {{
          R.forEach(r => {{
            if (r.suggerimento && !r.presente && !r.salvata && !r.categoria) {{
              r.categoria = String(r.suggerimento.valore); r.toccata = true;
            }}
          }});
          disegna();
        }},
      }};
    }})();
    </script>'''


def _esc(v) -> str:
    return (str(v) if v is not None else "").replace("&", "&amp;") \
        .replace("<", "&lt;").replace(">", "&gt;")


def _attr(v) -> str:
    return _esc(v).replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Il suggerimento nei form di inserimento a mano
# ---------------------------------------------------------------------------

def suggerimento_form(conto: str) -> str:
    """
    Lo script che, nei form «nuovo movimento», propone la categoria mentre
    scrivi: stessa API e stesso motore dell'import, cosi' un movimento
    scritto a mano e uno letto dall'estratto ricevono la stessa proposta.

    Si aspetta nel form `f_descrizione`, `f_importo`, `f_tipo` e
    `f_categoria` (piu' `f_sottocategoria` e `aggiornaSub()` sui conti che
    usano l'albero categoria › sottocategoria). Se la categoria e' ancora
    vuota e la proposta e' sicura, la applica; altrimenti la mostra con
    «usa». Non tocca mai una categoria gia' scelta.
    """
    return f'''
    <div class="small muted mt-1" id="propostaForm"></div>
    <script>
    (function () {{
      const box = document.getElementById('propostaForm');
      const cat = document.getElementById('f_categoria');
      if (!box || !cat) return;
      cat.closest('.field').appendChild(box);
      let ultima = null, timer = null, tipoToccato = false;
      const tipoEl = document.getElementById('f_tipo');
      if (tipoEl) tipoEl.addEventListener('change', e => {{ if (e.isTrusted) tipoToccato = true; }});
      function applica(p) {{
        // Prima la direzione, se lo storico ne propone un'altra: la
        // categoria giusta di un'entrata non e' fra quelle delle uscite.
        if (p.tipo && tipoEl && tipoEl.value !== p.tipo) {{
          tipoEl.value = p.tipo;
          tipoEl.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        if (p.categoria !== undefined) {{
          // Con l'evento `change`, non solo il valore: e' quello che
          // ascoltano il menu Fiori della shell (per ridisegnarsi) e il
          // form (per ricaricare le sottocategorie della categoria nuova).
          cat.value = p.categoria;
          cat.dispatchEvent(new Event('change', {{bubbles: true}}));
          const sub = document.getElementById('f_sottocategoria');
          if (sub) {{
            sub.value = p.sottocategoria || '';
            sub.dispatchEvent(new Event('change', {{bubbles: true}}));
          }}
        }}
        box.innerHTML = '';
      }}
      async function chiedi() {{
        const d = (document.getElementById('f_descrizione') || {{}}).value || '';
        if (d.trim().length < 3) {{ box.innerHTML = ''; return; }}
        const q = new URLSearchParams({{conto: {json.dumps(conto)}, descrizione: d,
          importo: (document.getElementById('f_importo') || {{}}).value || '',
          tipo: (document.getElementById('f_tipo') || {{}}).value || ''}});
        try {{
          const r = await fetch('/spese/api/suggerisci?' + q);
          const p = await r.json();
          if (!r.ok || !p || !p.nome) {{ box.innerHTML = ''; return; }}
          ultima = p;
          const cambiaTipo = p.tipo && tipoEl && tipoEl.value !== p.tipo;
          if (!cat.value && p.sicura && !(cambiaTipo && tipoToccato)) {{
            applica(p);
            box.textContent = (cambiaTipo ? 'Tipo e categoria proposti: ' : 'Categoria proposta: ') + p.motivo;
            return;
          }}
          if (cat.value === p.categoria && !cambiaTipo) {{ box.textContent = ''; return; }}
          box.innerHTML = 'Proposta: <strong></strong> (' + Math.round(p.fiducia * 100) +
            '%) · <a href="#">usa</a>';
          box.querySelector('strong').textContent =
            (cambiaTipo ? (p.tipo === 'entrata' ? 'Entrata · ' : 'Uscita · ') : '') + p.nome;
          box.querySelector('a').onclick = e => {{ e.preventDefault(); applica(ultima); }};
          box.title = p.motivo;
        }} catch (e) {{ box.innerHTML = ''; }}
      }}
      function presto() {{ clearTimeout(timer); timer = setTimeout(chiedi, 350); }}
      ['f_descrizione', 'f_importo', 'f_tipo'].forEach(id => {{
        const el = document.getElementById(id);
        if (el) {{ el.addEventListener('input', presto); el.addEventListener('change', presto); }}
      }});
    }})();
    </script>'''
