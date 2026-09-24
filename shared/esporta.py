"""
shared/esporta.py — L'app intera dentro un foglio di calcolo.

PERCHE' ESISTE, VISTO CHE UN EXPORT C'ERA GIA'
----------------------------------------------
`fatture/fiscale.py::_build_workbook` esporta **una cosa sola**: la
situazione fiscale di un anno, nella forma esatta del foglio del
commercialista. Serve a quello e va bene cosi'.

Questo invece e' il contrario: tutto quello che l'app sa, in un file solo,
organizzato per essere letto da un umano che non ha l'app davanti. Nasce
da un file vero — il `Budget.xlsx` da cui questa app e' cresciuta, con i
suoi fogli Spese / Totali / Risparmi / Parametri — e ne e' il successore:
stessi dati, ma calcolati dal database invece che da formule di matrice
scritte a mano, e con dentro anche tutto quello che l'app ha aggiunto dopo
(le fatture, il conto P.IVA, il fisco, Revolut, i salvadanai).

LE DUE REGOLE DEL RISPARMIO, AFFIANCATE
---------------------------------------
Il foglio "Periodi di paga" porta **due** colonne di risparmio consigliato,
ed e' il punto piu' importante del file.

`v_risparmi_mese` calcola la base come
`prima + stipendio + altre entrate − ogni uscita tranne i Risparmi`.
Il `Budget.xlsx` la calcolava come
`prima + stipendio − (Fisso + Personale + Benzina + Viaggi)`:
niente altre entrate, e solo quattro categorie di spesa.

Sui dodici periodi che i due sistemi hanno in comune la differenza e'
+2.028,84 € (+24%) — e lo scarto cumulato che l'app chiama "arretrato"
e' 2.323,35 €. Cioe': quasi tutto l'arretrato **e' la differenza fra le
due formule**, non denaro non risparmiato. Finche' non e' deciso quale
delle due regole vale, il file le mostra tutte e due riga per riga e
lascia decidere ai numeri (vedi docs/miglioramenti.md, voce del
24/09/2026).

Per lo stesso motivo c'e' la colonna "bonifico che lo salda": i bonifici
partono il giorno dopo l'arrivo dello stipendio, quindi **saldano il
periodo appena chiuso ma cadono in quello appena aperto**. Confrontare
consigliato ed effettivo sulla stessa riga confronta due periodi diversi.

COME E' FATTO
-------------
Un foglio "Indice" con i collegamenti a tutti gli altri, e ogni foglio con
un collegamento di ritorno: su dodici fogli la barra delle linguette non
basta piu'. Ogni foglio dati ha intestazioni bloccate e filtro automatico,
perche' un export che non si puo' ordinare e filtrare e' una stampa.

Le letture passano da `_tutte()`, che pagina. PostgREST tronca ogni
richiesta a 1000 righe senza dire niente (README §7): `spese` ne ha gia'
di piu', e un export troncato e' peggio di nessun export — sembra
completo.
"""
import io
from datetime import date, datetime

from spese import dati as D
from spese import revolut as R


# Il foglio non e' l'app: qui non ci sono i token del tema, ci sono i
# colori che Excel sa stampare. Restano pero' quelli di casa — il blu
# Horizon per i titoli e i collegamenti, il grigio per le intestazioni.
BLU = "FF0070F2"
BLU_CHIARO = "FFE1F4FF"
GRIGIO = "FF32363A"
GRIGIO_CHIARO = "FFF5F6F7"
VERDE = "FF256F3A"
ROSSO = "FFAA0808"
AMBRA = "FFFFF2CC"

FONT = "Calibri"
EUR = '#,##0.00\\ "€"'
EUR0 = '#,##0\\ "€"'
PCT = "0.0%"
DATA = "DD/MM/YYYY"
INT = "#,##0"


def _n(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _d(v) -> str:
    """Una data ISO in `date`, o None. Excel vuole un oggetto, non testo."""
    s = str(v or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _tutte(client, tabella: str, select: str = "*", ordine: str | None = None,
           desc: bool = False) -> list[dict]:
    """
    Tutte le righe di una tabella, davvero tutte.

    PostgREST tronca a 1000 righe e non lo dice: senza paginare, un export
    di `spese` si fermerebbe a meta' senza nessun errore visibile, e
    sarebbe l'errore peggiore possibile in un file che serve proprio a
    guardare lo storico completo.
    """
    out, offset, passo = [], 0, 1000
    while True:
        try:
            q = client.table(tabella).select(select)
            if ordine:
                q = q.order(ordine, desc=desc)
            r = q.range(offset, offset + passo - 1).execute()
            pagina = getattr(r, "data", None) or []
        except Exception:
            return out
        out.extend(pagina)
        if len(pagina) < passo:
            return out
        offset += passo


# ---------------------------------------------------------------------------
# Impalcatura dei fogli
# ---------------------------------------------------------------------------

def _stili():
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    sottile = Side(style="thin", color="FFD9D9D9")
    return {
        "titolo":  Font(name=FONT, size=16, bold=True, color=GRIGIO),
        "sotto":   Font(name=FONT, size=10, italic=True, color="FF6A6D70"),
        "link":    Font(name=FONT, size=10, color=BLU, underline="single"),
        "th":      Font(name=FONT, size=10, bold=True, color="FFFFFFFF"),
        "td":      Font(name=FONT, size=10),
        "tdb":     Font(name=FONT, size=10, bold=True),
        "fill_th": PatternFill("solid", fgColor=GRIGIO),
        "fill_tot": PatternFill("solid", fgColor=GRIGIO_CHIARO),
        "fill_ev": PatternFill("solid", fgColor=BLU_CHIARO),
        "fill_in": PatternFill("solid", fgColor=AMBRA),
        "bordo":   Border(bottom=sottile),
        "centro":  Alignment(horizontal="center", vertical="center"),
        "wrap":    Alignment(vertical="top", wrap_text=True),
    }


def _apri(wb, nome: str, titolo: str, spiega: str, S) -> tuple:
    """
    Un foglio nuovo con la sua testata: titolo, una riga che dice a che
    domanda risponde, e il ritorno all'indice.

    La riga di spiegazione non e' decorazione. Un foglio di numeri senza
    una frase che dica *che cosa sono* invecchia in tre mesi: fra un anno
    "Totale Speso" da solo non dira' se comprende i giroconti.
    """
    ws = wb.create_sheet(nome)
    ws.sheet_view.showGridLines = False
    ws["A1"] = titolo
    ws["A1"].font = S["titolo"]
    ws["A2"] = spiega
    ws["A2"].font = S["sotto"]
    ws["A3"] = "← Torna all'indice"
    ws["A3"].hyperlink = "#'Indice'!A1"
    ws["A3"].font = S["link"]
    return ws, 5


def _testata(ws, riga: int, colonne: list, S, blocca: bool = True):
    """
    Intestazioni, e — solo per la tabella **principale** del foglio — il
    blocco della finestra e il filtro automatico.

    `blocca=False` sulle tabelle secondarie: un foglio ha una sola
    finestra bloccata e un solo filtro, e se ogni tabella se li prende
    vince l'ultima. Su "Conti" voleva dire congelare le prime trentasette
    righe per filtrare le verifiche dell'estratto, lasciando i saldi —
    cioe' il motivo per cui si apre quel foglio — fuori dalla vista.
    """
    from openpyxl.utils import get_column_letter
    for i, (nome, larghezza, _fmt) in enumerate(colonne, start=1):
        c = ws.cell(row=riga, column=i, value=nome)
        c.font = S["th"]
        c.fill = S["fill_th"]
        c.alignment = S["wrap"]
        larga = ws.column_dimensions[get_column_letter(i)].width or 0
        ws.column_dimensions[get_column_letter(i)].width = max(larga, larghezza)
    if blocca:
        ws.freeze_panes = ws.cell(row=riga + 1, column=1)
        ultima = get_column_letter(len(colonne))
        ws.auto_filter.ref = f"A{riga}:{ultima}{riga}"
    return riga + 1


def _riga(ws, riga: int, valori: list, colonne: list, S, grassetto=False,
          fondo=None):
    for i, v in enumerate(valori, start=1):
        c = ws.cell(row=riga, column=i, value=v)
        c.font = S["tdb"] if grassetto else S["td"]
        fmt = colonne[i - 1][2]
        if fmt:
            c.number_format = fmt
        if fondo:
            c.fill = fondo
    return riga + 1


def _coppie(ws, riga: int, titolo: str, voci: list, S, larghezza=34):
    """
    Un blocchetto "etichetta: valore" — i riquadri dell'app tradotti in
    celle. `voci` e' una lista di (etichetta, valore, formato).
    """
    ws.cell(row=riga, column=1, value=titolo).font = S["tdb"]
    ws.cell(row=riga, column=1).fill = S["fill_ev"]
    ws.cell(row=riga, column=2).fill = S["fill_ev"]
    ws.cell(row=riga, column=3).fill = S["fill_ev"]
    riga += 1
    for etichetta, valore, fmt in voci:
        ws.cell(row=riga, column=1, value=etichetta).font = S["td"]
        c = ws.cell(row=riga, column=2, value=valore)
        c.font = S["td"]
        if fmt:
            c.number_format = fmt
        riga += 1
    ws.column_dimensions["A"].width = larghezza
    ws.column_dimensions["B"].width = 18
    return riga + 1


# ---------------------------------------------------------------------------
# I fogli, uno per uno
# ---------------------------------------------------------------------------

def _foglio_conti(wb, client, S, ctx):
    ws, r = _apri(wb, "Conti", "I tre conti, e quanto c'è davvero",
                  "Il saldo di un conto è apertura + entrate − uscite, e "
                  "nient'altro: gli stessi movimenti che vede la banca.", S)

    conto = ctx["conto"]
    piva = ctx["piva"]
    rev = ctx["rev"]

    r = _coppie(ws, r, "WeBank — conto personale", [
        ("Saldo di apertura", _n(conto.get("saldo_iniziale")), EUR),
        ("…alla data", _d(conto.get("dal")), DATA),
        ("Entrate dall'apertura", _n(conto.get("entrate")), EUR),
        ("Uscite dall'apertura", -_n(conto.get("uscite")), EUR),
        ("SALDO OGGI", _n(conto.get("saldo")), EUR),
        ("di cui finiti nei salvadanai", _n(conto.get("risparmiato")), EUR),
        ("Movimenti contati", conto.get("movimenti") or 0, INT),
    ], S)

    r = _coppie(ws, r, "WeBank — conto P.IVA", [
        ("Entrate (incassi dai clienti)", _n(piva.get("entrate")), EUR),
        ("Uscite (costi della P.IVA)", -_n(piva.get("uscite")), EUR),
        ("Girati sul conto personale", -_n(piva.get("girati")), EUR),
        ("SALDO OGGI", _n(piva.get("saldo")), EUR),
        ("di cui rivalsa INPS incassata", _n(piva.get("rivalsa_incassata")), EUR),
        ("Movimenti contati", piva.get("movimenti") or 0, INT),
    ], S)

    voci_rev = [("Fotografia del", _d(rev.get("data")), DATA),
                ("Conto (liquidità)", _n(rev.get("conto")), EUR)]
    reali = rev.get("salvadanai") or {}
    for chiave, _nome_rev, nome_app, _perc, _col, _alias in R.SALVADANAI:
        if chiave == "altro":
            continue
        voci_rev.append((f"  salvadanaio · {nome_app}", _n(reali.get(chiave)), EUR))
    voci_rev += [
        ("Risparmi in tutto", _n(rev.get("risparmi")), EUR),
        ("Investimenti", _n(rev.get("investimenti")), EUR),
        ("SALDO OGGI", _n(rev.get("saldo")), EUR),
    ]
    r = _coppie(ws, r, "Revolut", voci_rev, S)

    totale = (_n(conto.get("saldo")) + _n(piva.get("saldo"))
              + _n(rev.get("saldo")))
    r = _coppie(ws, r, "In tutto", [
        ("Patrimonio sui tre conti", totale, EUR),
    ], S)

    # Le verifiche contro l'estratto: l'unica misura indipendente che
    # esista. Senza, "il saldo è giusto" è un'affermazione che si fa da
    # sola.
    ver = _tutte(client, "b2f_saldi_verifica", "*", "data", desc=True)
    if ver:
        col = [("Conto", 22, None), ("Data estratto", 14, DATA),
               ("Saldo banca", 15, EUR), ("Note", 50, None)]
        ws.cell(row=r, column=1, value="Verifiche contro l'estratto").font = S["tdb"]
        r += 1
        r = _testata(ws, r, col, S, blocca=False)
        for v in ver[:24]:
            r = _riga(ws, r, [v.get("conto"), _d(v.get("data")),
                              _n(v.get("saldo_banca")), v.get("note")], col, S)
    return ws, 3


def _foglio_movimenti(wb, client, S):
    ws, r = _apri(wb, "Movimenti", "Conto personale — ogni movimento",
                  "Tutte le righe di `spese`, con categoria e "
                  "sottocategoria risolte. L'importo porta il segno: la "
                  "direzione la dà il tipo, non il numero.", S)
    col = [("Data", 12, DATA), ("Tipo", 10, None), ("Categoria", 20, None),
           ("Sottocategoria", 20, None), ("Descrizione", 44, None),
           ("Importo", 14, EUR), ("Metodo", 16, None), ("Anno", 8, INT),
           ("Mese", 8, INT)]
    r = _testata(ws, r, col, S)

    righe = _tutte(client, "v_spese",
                   "data,tipo,categoria,sottocategoria,descrizione,importo,"
                   "metodo_pagamento,anno,mese", "data", desc=True)
    prima = r
    for m in righe:
        segno = D.TIPI_SEGNO.get(m.get("tipo"), 0)
        imp = abs(_n(m.get("importo"))) * (1 if segno >= 0 else -1)
        r = _riga(ws, r, [_d(m.get("data")), m.get("tipo"), m.get("categoria"),
                          m.get("sottocategoria"), m.get("descrizione"), imp,
                          m.get("metodo_pagamento"), m.get("anno"),
                          m.get("mese")], col, S)
    if r > prima:
        r = _riga(ws, r, [f"{r - prima} movimenti", None, None, None, "Totale",
                          f"=SUM(F{prima}:F{r - 1})", None, None, None],
                  col, S, grassetto=True, fondo=S["fill_tot"])
    return ws, len(righe)


def _foglio_piva(wb, client, S):
    ws, r = _apri(wb, "Conto P.IVA", "Conto P.IVA — ogni movimento",
                  "Incassi dai clienti, costi della partita IVA e giroconti "
                  "verso il conto personale. Il giroconto esce di qui ed "
                  "entra di là: è lo stesso euro, contato una volta sola.", S)
    col = [("Data", 12, DATA), ("Tipo", 12, None), ("Categoria", 20, None),
           ("Sottocategoria", 18, None), ("Descrizione", 44, None),
           ("Importo", 14, EUR), ("Fattura", 10, INT), ("Note", 34, None)]
    r = _testata(ws, r, col, S)
    righe = _tutte(client, "b2f_spese_piva", "*", "data", desc=True)
    prima = r
    for m in righe:
        imp = abs(_n(m.get("importo")))
        if m.get("tipo") in ("uscita", "giroconto"):
            imp = -imp
        r = _riga(ws, r, [_d(m.get("data")), m.get("tipo"), m.get("categoria"),
                          m.get("sottocategoria"), m.get("descrizione"), imp,
                          m.get("fattura_id"), m.get("note")], col, S)
    if r > prima:
        r = _riga(ws, r, [f"{r - prima} movimenti", None, None, None, "Totale",
                          f"=SUM(F{prima}:F{r - 1})", None, None],
                  col, S, grassetto=True, fondo=S["fill_tot"])
    return ws, len(righe)


def _consigliato_foglio(p, prima_foglio: float, perc: float) -> float:
    """
    Il risparmio consigliato **con la regola del Budget.xlsx**:

        max(0, (prima + stipendio − speso_4_categorie) × percentuale)

    Non conta le altre entrate e sottrae solo Fisso, Personale, Benzina e
    Viaggi. E' la formula che l'utente ha seguito per diciannove mesi, e
    i suoi bonifici corrispondono a questa al centesimo: va mostrata
    accanto a quella della vista finche' non si decide quale vale.

    `prima_foglio` e' il saldo che il foglio si porta dietro, che non e'
    quello della vista: si accumula con le stesse esclusioni.
    """
    speso4 = (_n(p.get("fisso")) + _n(p.get("personale"))
              + _n(p.get("benzina")) + _n(p.get("viaggi")))
    base = prima_foglio + _n(p.get("bonifico")) - speso4
    return max(0.0, round(base * perc, 2)), round(base, 2), round(speso4, 2)


def _foglio_periodi(wb, client, S, ctx):
    ws, r = _apri(
        wb, "Periodi di paga", "Da uno stipendio al successivo",
        "Un periodo va da un'entrata di stipendio o giroconto P.IVA alla "
        "successiva: un mese solare può contenerne due, e non sono "
        "doppioni. Le due colonne di consigliato sono le due regole "
        "diverse — vedi la nota in fondo.", S)

    periodi = ctx["periodi"]          # dal più recente
    risparmi = ctx["mov_risparmi"]    # i bonifici veri, per data crescente

    col = [("Dal", 11, DATA), ("Al", 11, DATA), ("Giorni", 8, INT),
           ("Stato", 10, None),
           ("Sul conto prima", 15, EUR), ("Stipendio", 13, EUR),
           ("Altre entrate", 13, EUR), ("Speso", 13, EUR),
           ("Base (app)", 14, EUR), ("Quota", 8, PCT),
           ("Consigliato APP", 15, EUR),
           ("Base (foglio)", 14, EUR), ("Consigliato FOGLIO", 17, EUR),
           ("Differenza", 13, EUR),
           ("Messo via (per data)", 18, EUR),
           ("Bonifico che lo salda", 18, EUR),
           ("Quando", 11, DATA)]
    r = _testata(ws, r, col, S)

    oggi = date.today().isoformat()
    cronologici = list(reversed(periodi))

    # --- Quale bonifico salda quale periodo ------------------------------
    # Un bonifico appartiene, per data, al periodo che lo contiene: e' la
    # regola del progetto e non si tocca. Ma quello che *paga* e' il
    # periodo appena chiuso, perche' parte il giorno dopo l'arrivo dello
    # stipendio. Qui ogni bonifico viene assegnato **all'ultimo periodo
    # chiuso prima della sua data**, cosi' ogni bonifico conta una volta
    # sola: prendendo invece "il primo movimento dopo la fine" lo stesso
    # bonifico risultava saldare tre periodi diversi.
    salda_per: dict[str, list] = {}
    chiusure = [(D.confini_periodo(p, oggi)[1], D.confini_periodo(p, oggi)[0])
                for p in cronologici if D.periodo_chiuso(p)]
    for mov in risparmi:
        precedenti = [dal for al_, dal in chiusure if al_ < mov["data"]]
        if not precedenti:
            continue
        v = salda_per.setdefault(precedenti[-1], [0.0, None])
        v[0] = round(v[0] + mov["importo"], 2)
        v[1] = v[1] or mov["data"]

    # Il saldo che si porta dietro la regola del foglio. Parte dal
    # `saldo_iniziale` del **primo periodo in elenco**, non da quello
    # delle impostazioni: cosi' le due colonne partono dallo stesso punto
    # e la divergenza che si legge e' solo quella delle due formule, non
    # un disallineamento di partenza (l'elenco dei periodi e' comunque
    # limitato, e potrebbe non cominciare dall'apertura del conto).
    prima_foglio = _n(cronologici[0].get("saldo_iniziale")) if cronologici else 0.0

    prima_riga = r
    for p in cronologici:
        dal, al = D.confini_periodo(p, oggi)
        chiuso = D.periodo_chiuso(p)
        base_app = round(_n(p.get("saldo_iniziale")) + _n(p.get("bonifico"))
                         + _n(p.get("altre_entrate")) - _n(p.get("speso")), 2)
        cons_app = _n(p.get("risparmio_consigliato"))
        # La percentuale in vigore **in quel periodo**, ricavata dai suoi
        # numeri: sui periodi prima del 25/02/2026 era il 25%, non il 35%,
        # e leggerla dalle impostazioni di oggi riscriverebbe il passato.
        perc = round(cons_app / base_app, 6) if base_app > 0 else 0.0
        cons_fg, base_fg, _speso4 = _consigliato_foglio(p, prima_foglio, perc)
        eff = _n(p.get("risparmio_effettivo"))
        salda, quando_iso = salda_per.get(dal, [0.0, None])
        quando = _d(quando_iso)

        g = None
        try:
            g = (date.fromisoformat(al) - date.fromisoformat(dal)).days + 1
        except ValueError:
            pass

        r = _riga(ws, r, [
            _d(dal), _d(al) if chiuso else None, g,
            "chiuso" if chiuso else "in corso",
            _n(p.get("saldo_iniziale")), _n(p.get("bonifico")),
            _n(p.get("altre_entrate")), -_n(p.get("speso")),
            base_app, perc, cons_app,
            base_fg, cons_fg, round(cons_app - cons_fg, 2),
            eff, salda, quando,
        ], col, S, fondo=None if chiuso else S["fill_in"])

        prima_foglio = round(base_fg - eff, 2)

    if r > prima_riga:
        u = r - 1
        r = _riga(ws, r, [
            "Totale", None, None, f"{u - prima_riga + 1} periodi",
            None, f"=SUM(F{prima_riga}:F{u})", f"=SUM(G{prima_riga}:G{u})",
            f"=SUM(H{prima_riga}:H{u})", None, None,
            f"=SUM(K{prima_riga}:K{u})", None, f"=SUM(M{prima_riga}:M{u})",
            f"=K{r}-M{r}", f"=SUM(O{prima_riga}:O{u})", None, None,
        ], col, S, grassetto=True, fondo=S["fill_tot"])

    r += 1
    nota = (
        "Le due regole. «Consigliato APP» è la colonna di v_risparmi_mese: "
        "quota × (prima + stipendio + altre entrate − ogni uscita tranne i "
        "Risparmi). «Consigliato FOGLIO» è la formula del Budget.xlsx: "
        "quota × (prima + stipendio − Fisso − Personale − Benzina − Viaggi), "
        "senza altre entrate. La colonna Differenza dice quanto chiede in più "
        "l'app. Nota anche le ultime due colonne: i bonifici partono il giorno "
        "dopo l'arrivo dello stipendio, quindi saldano il periodo appena "
        "chiuso ma sono datati in quello appena aperto — «Messo via (per data)» "
        "e «Bonifico che lo salda» sono due domande diverse, e solo la seconda "
        "si confronta con il consigliato."
    )
    c = ws.cell(row=r, column=1, value=nota)
    c.font = S["sotto"]
    c.alignment = S["wrap"]
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 5, end_column=8)
    return ws, len(ctx['periodi'])


def _foglio_salvadanai(wb, client, S, ctx):
    ws, r = _apri(
        wb, "Salvadanai", "Dove finisce quello che metti via",
        "Le quote di ogni periodo secondo le percentuali in vigore, e in "
        "fondo il confronto con quanto c'è davvero su Revolut.", S)

    quote = [(k, nome_app, col, _n(ctx["impostazioni"].get(campo)))
             for k, _rev, nome_app, campo, col, _alias in R.SALVADANAI]

    col = ([("Dal", 11, DATA), ("Al", 11, DATA), ("Messo via", 14, EUR)]
           + [(nome, 15, EUR) for _k, nome, _c, _p in quote])
    r = _testata(ws, r, col, S)

    oggi = date.today().isoformat()
    prima = r
    for p in reversed(ctx["periodi"]):
        dal, al = D.confini_periodo(p, oggi)
        eff = _n(p.get("risparmio_effettivo"))
        r = _riga(ws, r, [_d(dal), _d(al), eff]
                  + [round(eff * perc, 2) for _k, _n2, _c, perc in quote],
                  col, S)
    if r > prima:
        u = r - 1
        from openpyxl.utils import get_column_letter
        tot = ["Totale", None, f"=SUM(C{prima}:C{u})"]
        for i in range(len(quote)):
            L = get_column_letter(4 + i)
            tot.append(f"=SUM({L}{prima}:{L}{u})")
        r = _riga(ws, r, tot, col, S, grassetto=True, fondo=S["fill_tot"])
    riga_tot = r - 1

    r += 1
    reali = (ctx["rev"].get("salvadanai") or {})
    col2 = [("Salvadanaio", 24, None), ("Quota", 10, PCT),
            ("Dovrebbe averne", 17, EUR), ("C'è su Revolut", 16, EUR),
            ("Scarto", 14, EUR), ("Nota", 46, None)]
    ws.cell(row=r, column=1, value="Atteso contro reale").font = S["tdb"]
    r += 1
    r = _testata(ws, r, col2, S, blocca=False)
    from openpyxl.utils import get_column_letter
    for i, (k, nome, _c, perc) in enumerate(quote):
        L = get_column_letter(4 + i)
        atteso = f"={L}{riga_tot}"
        if k == "altro":
            # "Altro" non e' un salvadanaio: quella quota va dritta negli
            # investimenti, e infatti su Revolut la voce non esiste.
            # Confrontarla con un secchiello inesistente dava un ammanco
            # fantasma permanente.
            r = _riga(ws, r, [nome + " → investimenti", perc, atteso,
                              _n(ctx["rev"].get("investimenti")), None,
                              "Non è un salvadanaio: va negli investimenti. "
                              "A destra il valore del portafoglio, che "
                              "comprende anche la crescita: i due numeri non "
                              "sono confrontabili."], col2, S)
            continue
        reale = _n(reali.get(k))
        r = _riga(ws, r, [nome, perc, atteso, reale, f"=D{r}-C{r}",
                          "Uno scarto non è di per sé un errore: dai "
                          "salvadanai si preleva."], col2, S)
    return ws, len(ctx['periodi'])


def _foglio_fatture(wb, client, S, ctx):
    ws, r = _apri(
        wb, "Fatture", "Tutte le fatture emesse",
        "Il regime forfettario è per cassa: quello che conta per le imposte "
        "è la data di incasso, non quella di emissione.", S)
    from fatture.costanti import STATI_LABEL, STATI_EMOJI

    col = [("Numero", 12, None), ("Data", 12, DATA), ("Cliente", 34, None),
           ("Imponibile", 14, EUR), ("Rivalsa INPS", 13, EUR),
           ("Bollo", 10, EUR), ("Totale", 14, EUR), ("Stato", 20, None),
           ("Incassata il", 13, DATA), ("Girata il", 12, DATA),
           ("Girato", 13, EUR), ("Accantonato", 13, EUR),
           ("Inviata a Nadia", 14, DATA), ("Allo studio", 12, DATA),
           ("A SDI", 12, DATA), ("Note", 34, None)]
    r = _testata(ws, r, col, S)

    fatture = _tutte(client, "b2f_fatture", "*", "data", desc=True)
    prima = r
    for f in fatture:
        snap = f.get("cliente_snapshot") or {}
        cliente = (snap.get("denominazione")
                   or " ".join(x for x in (snap.get("nome"), snap.get("cognome")) if x)
                   or "—")
        stato = f.get("stato") or ""
        etichetta = f'{STATI_EMOJI.get(stato, "")} {STATI_LABEL.get(stato, stato)}'.strip()
        r = _riga(ws, r, [
            f.get("numero") or f'{f.get("anno")}/{f.get("progressivo")}',
            _d(f.get("data")), cliente,
            _n(f.get("imponibile")), _n(f.get("cassa_importo")),
            _n(f.get("bollo")), _n(f.get("totale")), etichetta,
            _d(f.get("data_incasso")), _d(f.get("data_giroconto")),
            _n(f.get("giroconto_importo")), _n(f.get("accantonamento_importo")),
            _d(f.get("data_invio_nadia")), _d(f.get("data_invio_studio")),
            _d(f.get("data_trasmissione_sdi")), f.get("note"),
        ], col, S)
    if r > prima:
        u = r - 1
        r = _riga(ws, r, [f"{u - prima + 1} fatture", None, "Totale",
                          f"=SUM(D{prima}:D{u})", f"=SUM(E{prima}:E{u})",
                          f"=SUM(F{prima}:F{u})", f"=SUM(G{prima}:G{u})",
                          None, None, None, f"=SUM(K{prima}:K{u})",
                          f"=SUM(L{prima}:L{u})", None, None, None, None],
                  col, S, grassetto=True, fondo=S["fill_tot"])
    return ws, len(fatture)


def _foglio_clienti(wb, client, S):
    ws, r = _apri(wb, "Clienti", "Anagrafica clienti",
                  "Quello che finisce nell'intestazione della fattura. "
                  "La fattura ne tiene comunque una copia propria: "
                  "cambiare un indirizzo qui non riscrive il passato.", S)
    col = [("Tipo", 10, None), ("Denominazione / Nome", 34, None),
           ("P.IVA", 16, None), ("Codice fiscale", 20, None),
           ("Indirizzo", 30, None), ("CAP", 8, None), ("Comune", 20, None),
           ("Prov", 6, None), ("SDI", 10, None), ("PEC", 26, None),
           ("Email", 26, None), ("Attivo", 8, None), ("Note", 30, None)]
    r = _testata(ws, r, col, S)
    elenco = _tutte(client, "b2f_clienti", "*", "denominazione")
    n = len(elenco)
    for c in elenco:
        nome = (c.get("denominazione")
                or " ".join(x for x in (c.get("nome"), c.get("cognome")) if x))
        r = _riga(ws, r, [c.get("tipo"), nome, c.get("piva"), c.get("cf"),
                          c.get("indirizzo"), c.get("cap"), c.get("comune"),
                          c.get("provincia"), c.get("sdi"), c.get("pec"),
                          c.get("email"), "sì" if c.get("attivo") else "no",
                          c.get("note")], col, S)
    return ws, n


def _foglio_fisco(wb, client, S, ctx):
    ws, r = _apri(
        wb, f'Fisco {ctx["anno"]}', f'Situazione fiscale {ctx["anno"]}',
        "Forfettario, aliquota sul reddito imponibile calcolato col "
        "coefficiente ATECO. La tabella mensile è sull'emesso per restare "
        "allineata al foglio del commercialista; l'accantonamento è "
        "sull'incassato, che è la regola per cassa.", S)
    s = ctx["situazione"]
    if not s:
        ws.cell(row=r, column=1, value="Dati fiscali non disponibili.").font = S["td"]
        return ws, 0
    param = s.get("parametri") or {}

    r = _coppie(ws, r, "Parametri in vigore", [
        ("Coefficiente ATECO", _n(param.get("coeff_ateco")), PCT),
        ("Aliquota imposta", _n(param.get("aliquota_imposta")), PCT),
        ("Aliquota INPS", _n(param.get("aliquota_inps")), PCT),
        ("Aliquota acconto", _n(param.get("aliquota_acconto")), PCT),
        ("Limite fatturato", _n(param.get("limite_fatturato_anno")), EUR),
        ("Mesi di attività", s.get("mesi_attivita"), INT),
    ], S)

    col = [("Mese", 14, None), ("Fatturato (emesso)", 17, EUR),
           ("Imponibile", 14, EUR), ("Incassato", 14, EUR),
           ("Imposta", 13, EUR), ("INPS saldo", 13, EUR),
           ("INPS acconto", 13, EUR), ("Bollo", 10, EUR),
           ("Commercialista", 14, EUR), ("Rivalsa INPS", 13, EUR)]
    r = _testata(ws, r, col, S)
    prima = r
    for m in s.get("mensile") or []:
        r = _riga(ws, r, [
            m.get("nome"), _n(m.get("fatturato")), _n(m.get("imponibile")),
            _n(m.get("incasso")), _n(m.get("imposta")), _n(m.get("inps_saldo")),
            _n(m.get("inps_acconto")), _n(m.get("bollo")),
            _n(m.get("commercialista")), _n(m.get("rivalsa")),
        ], col, S)
    if r > prima:
        u = r - 1
        from openpyxl.utils import get_column_letter
        tot = ["Totale"] + [f"=SUM({get_column_letter(i)}{prima}:"
                            f"{get_column_letter(i)}{u})" for i in range(2, 11)]
        r = _riga(ws, r, tot, col, S, grassetto=True, fondo=S["fill_tot"])
    return ws, len(s.get('mensile') or [])


def _foglio_scadenze(wb, client, S, ctx):
    ws, r = _apri(wb, "Scadenze", "Quando esce il denaro delle imposte",
                  "Metà della risposta è QUANDO: è quello che dice se a "
                  "giugno i soldi ci sono.", S)
    col = [("Scadenza", 13, DATA), ("Che cosa", 40, None),
           ("Importo", 14, EUR), ("Anno di riferimento", 18, INT)]
    r = _testata(ws, r, col, S)
    prima = r
    for s in ctx.get("scadenze") or []:
        r = _riga(ws, r, [_d(s.get("data")), s.get("descrizione"),
                          _n(s.get("importo")), s.get("anno_comp")], col, S)
    if r > prima:
        r = _riga(ws, r, ["Totale", None, f"=SUM(C{prima}:C{r - 1})", None],
                  col, S, grassetto=True, fondo=S["fill_tot"])
    return ws, len(ctx.get('scadenze') or [])


def _foglio_categorie(wb, client, S, ctx):
    ws, r = _apri(wb, "Categorie", "Categorie e sottocategorie",
                  "Le coppie ammesse, e quanto ha attraversato ciascuna. "
                  "Una categoria non è un testo libero: è un rimando a "
                  "cfg_categoria_sottocategoria.", S)
    col = [("Categoria", 24, None), ("Sottocategoria", 24, None),
           ("Movimenti", 12, INT), ("Uscite", 15, EUR), ("Entrate", 15, EUR)]
    r = _testata(ws, r, col, S)

    conta: dict = {}
    for m in ctx["movimenti"]:
        chiave = (m.get("categoria") or "—", m.get("sottocategoria") or "")
        v = conta.setdefault(chiave, [0, 0.0, 0.0])
        v[0] += 1
        imp = abs(_n(m.get("importo")))
        if D.TIPI_SEGNO.get(m.get("tipo"), 0) < 0:
            v[1] += imp
        else:
            v[2] += imp

    scritte, viste = 0, set()
    for (cat, sub), (quanti, usc, ent) in sorted(conta.items()):
        viste.add((cat, sub))
        r = _riga(ws, r, [cat, sub or "—", quanti, round(usc, 2),
                          round(ent, 2)], col, S)
        scritte += 1
    # Le coppie ammesse ma mai usate: dicono che il menu offre una scelta
    # che non e' mai servita, ed e' un'informazione — non un buco.
    for v in ctx.get("coppie") or []:
        chiave = (v.get("categoria") or "—", v.get("sottocategoria") or "")
        if chiave in viste:
            continue
        viste.add(chiave)
        r = _riga(ws, r, [chiave[0], chiave[1] or "—", 0, 0.0, 0.0], col, S)
        scritte += 1
    return ws, scritte


def _foglio_parametri(wb, client, S, ctx):
    ws, r = _apri(wb, "Parametri", "Le manopole",
                  "I numeri che l'app usa per calcolare tutto il resto. "
                  "Cambiarli qui non cambia l'app: questo è un export.", S)
    imp = ctx["impostazioni"]
    r = _coppie(ws, r, "Risparmio", [
        ("Saldo di apertura", _n(imp.get("saldo_iniziale")), EUR),
        ("In vigore dal", _d(imp.get("valido_dal")), DATA),
        ("Quota di risparmio", _n(imp.get("percentuale_risparmio")), PCT),
        ("→ Fondo emergenze", _n(imp.get("perc_fondo_emergenze")), PCT),
        ("→ Viaggi", _n(imp.get("perc_viaggi")), PCT),
        ("→ Fondo casa", _n(imp.get("perc_fondo_casa")), PCT),
        ("→ Regali", _n(imp.get("perc_regali")), PCT),
        ("→ Altro (investimenti)", _n(imp.get("perc_altro")), PCT),
    ], S)

    p = ctx.get("parametri") or {}
    r = _coppie(ws, r, "Fisco", [
        ("Regime", p.get("regime"), None),
        ("Codice ATECO", p.get("ateco"), None),
        ("Descrizione ATECO", p.get("ateco_descrizione"), None),
        ("Coefficiente", _n(p.get("coeff_ateco")), PCT),
        ("Aliquota imposta", _n(p.get("aliquota_imposta")), PCT),
        ("Aliquota INPS", _n(p.get("aliquota_inps")), PCT),
        ("Aliquota acconto", _n(p.get("aliquota_acconto")), PCT),
        ("Soglia bollo", _n(p.get("bollo_soglia")), EUR),
        ("Importo bollo", _n(p.get("bollo_importo")), EUR),
        ("Limite fatturato", _n(p.get("limite_fatturato_anno")), EUR),
        ("Apertura P.IVA", _d(p.get("data_apertura_piva")), DATA),
        ("Fine regime agevolato", p.get("anno_fine_regime_agevolato"), INT),
        ("Margine di sicurezza", _n(p.get("margine_sicurezza")), PCT),
        ("Costi fissi annui", _n(p.get("costi_fissi_annui")), EUR),
        ("Fatturato atteso", _n(p.get("fatturato_atteso_anno")), EUR),
        ("Scenario preferito", p.get("scenario_preferito"), None),
        ("Tariffa giornaliera", _n(p.get("tariffa_giornaliera")), EUR),
    ], S)
    return ws, 25


def _foglio_indice(wb, S, ctx, fogli: list):
    """
    L'indice, che e' il primo foglio e l'unico che si apre da solo.

    Su dodici fogli le linguette in fondo non bastano piu': servono un
    elenco che dica che cosa c'e' dentro ciascuno e un collegamento che
    ci porti. Sopra l'elenco, i quattro numeri per cui uno apre il file.
    """
    ws = wb.create_sheet("Indice", 0)
    ws.sheet_view.showGridLines = False
    ws["A1"] = "B2F Hub — esportazione completa"
    ws["A1"].font = S["titolo"]
    ws["A2"] = (f'Generato il {datetime.now().strftime("%d/%m/%Y alle %H:%M")}'
                f' · tutti i dati dell\'app, alla data di oggi')
    ws["A2"].font = S["sotto"]

    conto, piva, rev = ctx["conto"], ctx["piva"], ctx["rev"]
    r = _coppie(ws, 4, "In due righe", [
        ("Conto personale", _n(conto.get("saldo")), EUR),
        ("Conto P.IVA", _n(piva.get("saldo")), EUR),
        ("Revolut", _n(rev.get("saldo")), EUR),
        ("In tutto", _n(conto.get("saldo")) + _n(piva.get("saldo"))
         + _n(rev.get("saldo")), EUR),
        ("Movimenti registrati", len(ctx["movimenti"]), INT),
        ("Periodi di paga", len(ctx["periodi"]), INT),
        ("Fatture", ctx.get("n_fatture", 0), INT),
    ], S)

    col = [("Foglio", 22, None), ("Che cosa c'è dentro", 76, None),
           ("Voci", 9, INT)]
    r = _testata(ws, r, col, S, blocca=False)
    for nome, descrizione, righe in fogli:
        c = ws.cell(row=r, column=1, value=nome)
        c.hyperlink = f"#'{nome}'!A1"
        c.font = S["link"]
        d = ws.cell(row=r, column=2, value=descrizione)
        d.font = S["td"]
        d.alignment = S["wrap"]
        n = ws.cell(row=r, column=3, value=righe)
        n.font = S["td"]
        n.number_format = INT
        ws.row_dimensions[r].height = 28
        r += 1
    return ws


# ---------------------------------------------------------------------------
# Il file
# ---------------------------------------------------------------------------

DESCRIZIONI = {
    "Conti": "I tre conti con la formula del saldo aperta voce per voce, e le "
             "verifiche contro l'estratto della banca.",
    "Movimenti": "Ogni riga del conto personale: data, categoria, "
                 "sottocategoria, importo col segno, metodo di pagamento.",
    "Conto P.IVA": "Ogni riga del conto partita IVA: incassi, costi e "
                   "giroconti verso il personale.",
    "Periodi di paga": "Da uno stipendio al successivo: base del calcolo, "
                       "risparmio consigliato con ENTRAMBE le regole (app e "
                       "Budget.xlsx), quanto è stato messo via e quale "
                       "bonifico salda quale periodo.",
    "Salvadanai": "Come si divide quello che metti via fra i cinque "
                  "secchielli, e il confronto con i saldi Revolut.",
    "Fatture": "Tutte le fatture con stato, date del percorso, incasso, "
               "giroconto e accantonamento.",
    "Clienti": "Anagrafica completa, quella che finisce in fattura.",
    "Scadenze": "Le scadenze fiscali con data e importo.",
    "Categorie": "Categorie e sottocategorie ammesse, con quanto ha "
                 "attraversato ciascuna.",
    "Parametri": "Le manopole: quote di risparmio e parametri fiscali.",
}


def _contesto(client) -> dict:
    """Tutto quello che serve, letto una volta sola."""
    anno = date.today().year
    ctx = {
        "anno": anno,
        "conto": D.saldo_conto(client),
        "periodi": D.periodi_risparmio(client),
        "impostazioni": D.impostazioni(client),
        "rev": R.saldo_revolut(client),
        "movimenti": _tutte(client, "v_spese",
                            "data,tipo,categoria,sottocategoria,importo",
                            "data", desc=True),
        # `voci_categoria` e non la tabella grezza: li' ci sono gli id, e
        # un export con dentro `categoria_link_id: 37` non serve a nessuno.
        "coppie": D.voci_categoria(client),
    }

    # I bonifici di risparmio in ordine di data: servono a dire quale
    # salda quale periodo (vedi _foglio_periodi).
    mov = []
    for m in ctx["movimenti"]:
        if (m.get("categoria") or "") != D.CATEGORIA_RISPARMIO:
            continue
        if D.TIPI_SEGNO.get(m.get("tipo"), 0) >= 0:
            continue
        mov.append({"data": str(m.get("data") or "")[:10],
                    "importo": abs(_n(m.get("importo")))})
    ctx["mov_risparmi"] = sorted(mov, key=lambda x: x["data"])

    # L'area fiscale sta dietro un try: se non e' raggiungibile il file
    # perde due fogli, non si rompe.
    try:
        from fatture import fiscale as F
        ctx["piva"] = F.saldo_piva(client)
        ctx["parametri"] = F.get_parametri(client)
        ctx["situazione"] = F.situazione_data(client, anno)
        ctx["scadenze"] = F._scadenze_tutte(
            client, ctx["parametri"], ctx["situazione"], anno) or []
    except Exception:
        ctx.setdefault("piva", {})
        ctx.setdefault("parametri", {})
        ctx.setdefault("situazione", None)
        ctx.setdefault("scadenze", [])

    try:
        r = client.table("b2f_fatture").select("id").execute()
        ctx["n_fatture"] = len(getattr(r, "data", None) or [])
    except Exception:
        ctx["n_fatture"] = 0
    return ctx


def costruisci(client) -> io.BytesIO:
    """La cartella di lavoro completa, pronta da scaricare."""
    from openpyxl import Workbook

    S = _stili()
    ctx = _contesto(client)

    wb = Workbook()
    wb.remove(wb.active)          # il foglio vuoto che openpyxl crea da solo

    costruttori = [
        ("Conti",           lambda: _foglio_conti(wb, client, S, ctx)),
        ("Periodi di paga", lambda: _foglio_periodi(wb, client, S, ctx)),
        ("Salvadanai",      lambda: _foglio_salvadanai(wb, client, S, ctx)),
        ("Movimenti",       lambda: _foglio_movimenti(wb, client, S)),
        ("Conto P.IVA",     lambda: _foglio_piva(wb, client, S)),
        ("Fatture",         lambda: _foglio_fatture(wb, client, S, ctx)),
        ("Clienti",         lambda: _foglio_clienti(wb, client, S)),
        (f'Fisco {ctx["anno"]}', lambda: _foglio_fisco(wb, client, S, ctx)),
        ("Scadenze",        lambda: _foglio_scadenze(wb, client, S, ctx)),
        ("Categorie",       lambda: _foglio_categorie(wb, client, S, ctx)),
        ("Parametri",       lambda: _foglio_parametri(wb, client, S, ctx)),
    ]

    # Ogni costruttore dice quante righe di **dati** ha scritto. Contarle
    # da `ws.max_row` sarebbe sbagliato: comprende testate, note e
    # blocchetti chiave/valore, e un foglio vuoto direbbe comunque "5".
    fogli = []
    for nome, fai in costruttori:
        ws, quante = fai()
        fogli.append((ws.title, DESCRIZIONI.get(nome)
                      or f"Situazione fiscale {ctx['anno']}, mese per mese, "
                         f"con i parametri in vigore.", quante))

    _foglio_indice(wb, S, ctx, fogli)
    wb.active = 0

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def nome_file() -> str:
    return f'B2F_Hub_{date.today().isoformat()}.xlsx'
