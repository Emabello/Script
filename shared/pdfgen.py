"""
shared/pdfgen.py — Generazione del facsimile di fattura (PDF).

ATTENZIONE: questo documento NON e' la fattura elettronica.

Il giro concordato con lo studio (mail del 5 agosto 2026) e': tu emetti il
facsimile e lo mandi allo studio, loro predispongono e trasmettono l'XML
allo SDI. Il documento fiscale e' quello, non questo, e a dirlo resta il
badge FACSIMILE in testa al foglio.

In calce NON c'e' piu' l'avviso esteso ("documento non valido ai fini
fiscali... trasmessa al Sistema di Interscambio da..."): tolto su
richiesta, 01/09/2026, perche' questo foglio si stampa e si consegna, e
chi lo riceve sa gia' che la fattura elettronica arriva per altra via.
Se un giorno lo si volesse rimettere, il posto e' dopo le note fiscali,
prima del footer.

La rivalsa INPS del 4 % e' SCORPORATA dal corrispettivo, non aggiunta:
il totale che il cliente paga non cambia, e' il compenso a ridursi.

Espone globalmente:
  window.b2fRenderInvoicePDF(payload)

payload shape:
  {
    numero_display: "1"                   // solo progressivo (anno implicito dalla data)
    data_iso:       "2026-07-08",
    tipo_doc:       "TD01" | "TD04" | "TD06",
    cliente:        {tipo, denominazione, nome, cognome, piva, cf,
                     indirizzo, cap, comune, provincia},
    righe:          [{descrizione, qta, um, prezzo}],
    corrispettivo:  Number,               // concordato col cliente
    compenso:       Number,               // corrispettivo - rivalsa
    imponibile:     Number,               // = corrispettivo (compenso+rivalsa)
    cassa_perc:     Number,               // 0 o 4
    cassa_importo:  Number,               // rivalsa scorporata
    bollo_add:      Boolean,              // bollo addebitato al cliente?
    bollo_dovuto:   Boolean,              // dovuto in generale (imponibile > 77.47)
    totale:         Number,
    pagamento_mod:  "Bonifico" | ...,     // stringa libera senza codici
    scadenza:       "2026-07-31" | null,
  }
"""

import json


TIPO_DOC_LABEL = {
    "TD01": "FATTURA",
    "TD04": "NOTA CREDITO",
    "TD06": "PARCELLA",
}


def emittente_to_json(em: dict) -> str:
    """Serializza l'emittente per l'iniezione JS."""
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
        "aliquota_cassa": float(em.get("aliquota_cassa") or 0),
        # Chi predispone e trasmette la fattura elettronica. Non compare
        # piu' nel PDF (l'avviso in calce non c'e' piu'), ma resta qui:
        # e' il posto da cui rileggerlo se servisse rimetterlo.
        "studio_nome":  em.get("studio_nome") or "",
        "studio_email": em.get("studio_email") or "",
    }
    # niente "<" nel blob: iniettato in un <script> letterale (vedi
    # pdf_script sotto), un campo con "</script>" dentro chiuderebbe il
    # tag prima e inietterebbe markup.
    return json.dumps(d, ensure_ascii=False).replace("<", "\\u003c")


def pdf_script(emittente: dict) -> str:
    """
    Ritorna il tag <script> con jsPDF + la funzione window.b2fRenderInvoicePDF.
    Da iniettare nella pagina che ha bisogno di generare/ristampare PDF.
    """
    emj = emittente_to_json(emittente)
    return _JS_TEMPLATE.replace("__EMITTENTE_JSON__", emj)


# Layout PDF identico a genPDF() del fatturatore.html originale, con:
#   - titolo "FATTURA" (o "NOTA CREDITO" / "PARCELLA") invece di "PROFORMA"
#   - modo pagamento senza prefisso codice MP0x
#   - nessun blocco disclaimer in calce
#   - nome file "Fattura_N_Cliente.pdf"
_JS_TEMPLATE = r"""
<!-- jsPDF 2.5.1 (MIT), ospitata dall'app: il facsimile e' il documento
     che finisce dal commercialista, non puo' dipendere da un CDN
     raggiungibile. Cosi' funziona anche offline, come i caratteri. -->
<script src="/static/vendor/jspdf.umd.min.js"></script>
<script>
(function(){
  const EMITTENTE = __EMITTENTE_JSON__;
  window.B2F_EMITTENTE = EMITTENTE;   // esposto anche fuori dall'IIFE

  const DIC_REGIME   = "Operazione senza applicazione dell'IVA ex art. 1, c. 54-89, L. 190/2014 - regime forfettario.";
  const DIC_RITENUTA = "Compenso non soggetto a ritenuta d'acconto ex art. 1, c. 67, L. 190/2014.";

  const TIPI = { TD01: 'FATTURA', TD04: 'NOTA DI CREDITO', TD06: 'PARCELLA' };

  const r2 = n => Math.round((Number(n)+Number.EPSILON)*100)/100;
  const nf = n => r2(n).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
  const itDate = iso => { if(!iso) return ''; const [y,m,d]=iso.split('-'); return `${d}/${m}/${y}`; };
  const stripCode = s => (s || '').replace(/^\s*[A-Z]{2,}\d+\s*[—-]\s*/i, '').trim();

  function cLabel(c) {
    if (!c) return 'Cliente';
    return (c.tipo === 'privato' || c.tipo === 'priv')
      ? `${c.nome || ''} ${c.cognome || ''}`.trim() || 'Cliente'
      : (c.denominazione || 'Cliente');
  }

  window.b2fRenderInvoicePDF = function(payload) {
    if (!window.jspdf || !window.jspdf.jsPDF) {
      alert('Libreria PDF non caricata'); return;
    }
    const { jsPDF } = window.jspdf;
    const d = new jsPDF({unit:'mm', format:'a4'});

    const e = EMITTENTE;
    const c = payload.cliente || {};
    const PW = 210, M = 18, RX = PW - M, CW = RX - M;

    // Palette identica al fatturatore originale
    const ink=[24,27,33], mut=[110,116,124], soft=[150,156,163],
          acc=[22,98,79], accD=[14,70,56],
          tint=[236,244,241], tint2=[246,249,247],
          line=[228,227,222], lineS=[237,236,231], white=[255,255,255];

    const cNome = cLabel(c);
    const initials = ((e.nome[0]||'')+(e.cognome[0]||'')).toUpperCase() || 'EB';
    const tipoLabel = TIPI[payload.tipo_doc] || 'FATTURA';

    // ===== TOP BAND =====
    d.setFillColor(...acc); d.rect(0,0,PW,6,'F');

    let y = 22;

    // ===== MONOGRAM =====
    d.setFillColor(...acc); d.roundedRect(M, y-5, 13, 13, 2.2, 2.2, 'F');
    d.setTextColor(...white); d.setFont('helvetica','bold'); d.setFontSize(11);
    d.text(initials, M+6.5, y+2.6, {align:'center'});

    // ===== EMITTENTE =====
    const nx = M + 18;
    d.setTextColor(...ink); d.setFont('helvetica','bold'); d.setFontSize(15);
    const emName = e.denominazione || `${e.nome} ${e.cognome}`.trim();
    d.text(emName, nx, y);
    d.setFont('helvetica','normal'); d.setFontSize(8); d.setTextColor(...mut);
    const emIds = [];
    if (e.piva) emIds.push('P.IVA ' + e.piva);
    if (e.cf)   emIds.push('C.F. ' + e.cf);
    if (emIds.length) d.text(emIds.join('   ·   '), nx, y+5.5);
    const addrBits = [];
    if (e.indirizzo) addrBits.push(e.indirizzo);
    const cityStr = ([e.cap, e.comune].filter(Boolean).join(' ') +
                     (e.provincia ? ' (' + e.provincia + ')' : '')).trim();
    if (cityStr) addrBits.push(cityStr);
    if (addrBits.length) d.text(addrBits.join(' — '), nx, y+9.5);
    const cont = [];
    if (e.email) cont.push(e.email);
    if (e.pec)   cont.push('PEC ' + e.pec);
    if (cont.length) d.text(cont.join('   ·   '), nx, y+13.5);

    // ===== BADGE TITOLO DOC =====
    // "FACSIMILE" in grande e il tipo sotto: chi lo riceve deve capire al
    // primo sguardo che il documento fiscale non e' questo.
    const bw = 52, bx = RX - bw, by = y - 5;
    d.setFillColor(...tint); d.roundedRect(bx, by, bw, 22, 2.2, 2.2, 'F');
    d.setTextColor(...accD); d.setFont('helvetica','bold'); d.setFontSize(12.5);
    d.text('FACSIMILE', bx + bw/2, by + 7.5, {align:'center'});
    d.setFont('helvetica','normal'); d.setFontSize(7.5); d.setTextColor(...acc);
    d.text('per ' + tipoLabel.toLowerCase(), bx + bw/2, by + 12, {align:'center'});
    d.setFontSize(8);
    d.text(`n. ${payload.numero_display}   ·   ${itDate(payload.data_iso)}`,
           bx + bw/2, by + 17, {align:'center'});

    y += 24;
    d.setDrawColor(...line); d.setLineWidth(0.3); d.line(M, y, RX, y);
    y += 8;

    // ===== DESTINATARIO =====
    d.setFont('helvetica','bold'); d.setFontSize(7.5); d.setTextColor(...soft);
    d.text('DESTINATARIO', M + 4, y);
    const blkTop = y + 2;

    d.setTextColor(...ink); d.setFont('helvetica','bold'); d.setFontSize(11);
    d.text(cNome, M + 4, y + 7);

    d.setFont('helvetica','normal'); d.setFontSize(8.5); d.setTextColor(...mut);
    let cyy = y + 12;
    const cIds = [];
    if (c.piva) cIds.push('P.IVA ' + c.piva);
    if (c.cf)   cIds.push('C.F. ' + c.cf);
    if (cIds.length) { d.text(cIds.join('    '), M + 4, cyy); cyy += 4.4; }
    const cCityStr = ([c.cap, c.comune].filter(Boolean).join(' ') +
                      (c.provincia ? ' (' + c.provincia + ')' : '')).trim();
    const cAddr = [c.indirizzo, cCityStr].filter(Boolean).join(' — ');
    if (cAddr) { d.text(cAddr, M + 4, cyy); cyy += 4.4; }

    d.setFillColor(...acc); d.rect(M, blkTop, 1.5, cyy - blkTop - 2, 'F');
    y = cyy + 6;

    // ===== HEADER RIGHE =====
    const col = {desc: M + 2, qta: 116, prezzo: 150, imp: 190, descW: 82};
    d.setFillColor(...acc); d.roundedRect(M, y, CW, 8, 1.5, 1.5, 'F');
    d.setTextColor(...white); d.setFont('helvetica','bold'); d.setFontSize(7.5);
    d.text('DESCRIZIONE', col.desc, y + 5.2);
    d.text('Q.TÀ',       col.qta,    y + 5.2, {align:'right'});
    d.text('PREZZO €',    col.prezzo, y + 5.2, {align:'right'});
    d.text('IMPORTO €',   col.imp,    y + 5.2, {align:'right'});
    y += 8;

    // ===== RIGHE =====
    const drawRow = (desc, q, p, imp, zebra) => {
      const dl = d.splitTextToSize(desc, col.descW);
      const rh = Math.max(dl.length * 4.4 + 3.4, 8.5);
      if (zebra) { d.setFillColor(...tint2); d.rect(M, y, CW, rh, 'F'); }
      d.setTextColor(...ink); d.setFont('helvetica','normal'); d.setFontSize(9);
      d.text(dl, col.desc, y + 5.2);
      d.setFont('courier','normal'); d.setFontSize(8.5); d.setTextColor(...mut);
      if (q !== null) d.text(q, col.qta,    y + 5.2, {align:'right'});
      if (p !== null) d.text(p, col.prezzo, y + 5.2, {align:'right'});
      d.setTextColor(...ink); d.text(imp, col.imp, y + 5.2, {align:'right'});
      y += rh;
      d.setDrawColor(...lineS); d.setLineWidth(0.2); d.line(M, y, RX, y);
    };

    let zebra = false;
    (payload.righe || []).forEach(r => {
      const q = Number(r.qta) || 0, p = Number(r.prezzo) || 0;
      if (q * p === 0 && !r.descrizione) return;
      const qStr = q.toLocaleString('it-IT') + (r.um ? ' ' + r.um : '');
      drawRow(r.descrizione || 'Prestazione', qStr, nf(p), nf(q * p), zebra);
      zebra = !zebra;
    });
    // La rivalsa NON compare come riga aggiuntiva: e' scorporata dal
    // corrispettivo, quindi aggiungerla in fondo farebbe sembrare che il
    // totale cresca. Sta nel blocco totali, come scomposizione.

    // ===== TOTALI (destra) + PAGAMENTO (sinistra) affiancati =====
    const yBlock = y + 7;

    // Totali a destra
    y = yBlock; const tlx = 120;
    const conRivalsa = payload.cassa_perc > 0 && payload.cassa_importo > 0;
    const corrisp = payload.corrispettivo != null
                    ? payload.corrispettivo : payload.imponibile;

    d.setFont('helvetica','normal'); d.setFontSize(9.5); d.setTextColor(...mut);
    d.text(conRivalsa ? 'Corrispettivo' : 'Imponibile', tlx, y);
    d.setFont('courier','normal'); d.setTextColor(...ink);
    d.text(nf(corrisp) + ' €', RX, y, {align:'right'});
    y += 6;

    if (conRivalsa) {
      // Le due voci che servono allo studio per compilare l'XML: compenso
      // in DettaglioLinee, rivalsa in DatiCassaPrevidenziale.
      d.setFont('helvetica','normal'); d.setFontSize(8.5); d.setTextColor(...soft);
      d.text('di cui compenso', tlx + 3, y);
      d.setFont('courier','normal'); d.setTextColor(...mut);
      d.text(nf(payload.compenso != null ? payload.compenso
                : corrisp - payload.cassa_importo) + ' €', RX, y, {align:'right'});
      y += 5;
      d.setFont('helvetica','normal'); d.setTextColor(...soft);
      d.text(`di cui rivalsa INPS ${payload.cassa_perc}%`, tlx + 3, y);
      d.setFont('courier','normal'); d.setTextColor(...mut);
      d.text(nf(payload.cassa_importo) + ' €', RX, y, {align:'right'});
      y += 6.5;
      d.setFontSize(9.5);
    }

    if (payload.bollo_add) {
      d.setFont('helvetica','normal'); d.setTextColor(...mut);
      d.text('Imposta di bollo', tlx, y);
      d.setFont('courier','normal'); d.setTextColor(...ink);
      d.text('2,00 €', RX, y, {align:'right'});
      y += 6;
    }
    y += 1;
    d.setFillColor(...acc); d.roundedRect(tlx - 4, y - 1, RX - (tlx - 4), 10.5, 1.5, 1.5, 'F');
    d.setTextColor(...white); d.setFont('helvetica','bold'); d.setFontSize(10);
    d.text('TOTALE A PAGARE', tlx, y + 5.6);
    d.setFont('courier','bold'); d.setFontSize(11.5);
    d.text(nf(payload.totale) + ' €', RX - 2, y + 5.6, {align:'right'});
    y += 10.5;
    const yTotEnd = y;

    // Pagamento a sinistra
    y = yBlock - 3;
    const hasScad = !!payload.scadenza;
    const pbw = 94;
    const pbh = 14 + (e.iban ? 5 : 0) + (hasScad ? 5 : 0);
    d.setFillColor(...tint2); d.roundedRect(M, y, pbw, pbh, 2, 2, 'F');
    d.setTextColor(...soft); d.setFont('helvetica','bold'); d.setFontSize(7.5);
    d.text('PAGAMENTO', M + 4, y + 6);

    let py = y + 11.5;
    d.setTextColor(...ink); d.setFont('helvetica','normal'); d.setFontSize(9);
    const modo = stripCode(payload.pagamento_mod) || 'Bonifico bancario';
    d.text(modo, M + 4, py); py += 5;

    if (e.iban) {
      d.setFont('courier','normal'); d.setFontSize(8.3); d.setTextColor(...ink);
      d.text('IBAN ' + e.iban, M + 4, py); py += 5;
    }
    if (hasScad) {
      d.setFont('helvetica','normal'); d.setFontSize(8.3); d.setTextColor(...mut);
      d.text('Scadenza: ' + itDate(payload.scadenza), M + 4, py);
    }
    const yPayEnd = y + pbh;

    // ===== NOTE FISCALI =====
    y = Math.max(yTotEnd, yPayEnd) + 9;
    d.setDrawColor(...line); d.setLineWidth(0.3); d.line(M, y, RX, y);
    y += 5;

    d.setFont('helvetica','normal'); d.setFontSize(7.5); d.setTextColor(...mut);
    const notes = [DIC_REGIME, DIC_RITENUTA];
    if (payload.cassa_perc > 0 && payload.cassa_importo > 0) {
      notes.push(`Rivalsa INPS Gestione Separata ${payload.cassa_perc}% scorporata dal `
                 + `corrispettivo ai sensi dell'art. 1, c. 212, L. 662/1996: il totale `
                 + `a carico del committente non varia.`);
    }
    if (payload.bollo_dovuto && !payload.bollo_add) {
      notes.push('Imposta di bollo di € 2,00 assolta virtualmente ai sensi del D.M. 17/06/2014.');
    }
    notes.forEach(nt => {
      const nl = d.splitTextToSize(nt, CW);
      d.text(nl, M, y);
      y += nl.length * 3.6 + 1.6;
    });

    // In calce non c'e' nessun avviso: il foglio che si stampa e si
    // consegna deve leggersi come un documento e basta. Che non sia la
    // fattura elettronica lo dice il badge FACSIMILE in testa, e lo sa
    // chi lo riceve. (Tolto su richiesta esplicita, 01/09/2026.)

    // ===== FOOTER =====
    const fy = 288;
    d.setDrawColor(...acc); d.setLineWidth(0.5); d.line(M, fy, RX, fy);
    d.setFont('helvetica','normal'); d.setFontSize(7); d.setTextColor(...soft);
    const foot = [emName, e.piva ? 'P.IVA ' + e.piva : '', e.email || '']
                 .filter(Boolean).join('     ·     ');
    d.text(foot, PW/2, fy + 4.5, {align:'center'});

    // ===== SALVA (compatibile mobile + PWA) =====
    const safeCli = cNome.replace(/[^\w]+/g, '_').slice(0, 30);
    const fname = `Facsimile_${payload.numero_display}_${safeCli}.pdf`;

    try {
      // Approccio universale: blob + anchor con download attribute
      // Funziona su Chrome/Firefox/Safari desktop e su Chrome Android in PWA.
      const blob = d.output('blob');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fname;
      a.rel = 'noopener';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      // Cleanup differito (Safari iOS a volte perde il blob se lo revochi subito)
      setTimeout(() => {
        try { document.body.removeChild(a); } catch (e) {}
        URL.revokeObjectURL(url);
      }, 2000);
    } catch (err) {
      // Ultima spiaggia: apre il PDF in nuova tab (utente lo salva manualmente)
      try {
        const url = d.output('bloburl');
        window.open(url, '_blank');
      } catch (e2) {
        alert('Impossibile scaricare il PDF: ' + (err.message || err));
      }
    }
    return true;
  };
})();
</script>
"""
