"""
spese/risparmi.py — I periodi di stipendio e quanto metti da parte.

COME RAGIONA QUESTA PAGINA
--------------------------
Il conto personale non ragiona per mesi solari ma per periodi che vanno
da un bonifico dello stipendio al successivo: e' v_periodi_stipendio a
delimitarli, prendendo le entrate di categoria "Stipendio" **o**
"Giroconto P.IVA" — il giroconto dalla P.IVA e' il tuo stipendio di
fatto da quando hai aperto la partita IVA, quindi apre un periodo
esattamente come faceva prima lo stipendio da dipendente. Richiede la
migrazione README §8.7; prima di applicarla il giroconto restava
"altre entrate" dentro un periodo che non si chiudeva mai.

**Il periodo non e' il mese, e la differenza si vede.** In agosto 2026
sono arrivate due entrate che aprono un periodo (il 5 e il 13): agosto
sono due periodi, non uno. Per questo il menu in cima non elenca mesi
ma periodi, e ognuno porta scritti i suoi estremi — "Agosto 2026 ·
13 ago → 2 set" — altrimenti due voci identiche sarebbero
indistinguibili. Per la stessa ragione l'ordine e' cronologico e non
alfabetico: qui la sequenza e' informazione (vedi CLAUDE.md).

LA CASCATA, E PERCHE' DEVE QUADRARE
------------------------------------
Il dettaglio del periodo e' una cascata di addendi che finisce sul
numero da cui si calcola il consigliato:

    sul conto prima dello stipendio
  + stipendio (o giroconto P.IVA)
  + altre entrate
  − ogni uscita, categoria per categoria
  = base del calcolo        × percentuale = risparmio consigliato

Prima non quadrava, e per due motivi insieme. Il totale "Speso" della
vista somma *ogni* uscita tranne i Risparmi, ma il dettaglio ne
mostrava solo quattro categorie: quello che cadeva fuori spariva dalla
vista pur restando nel totale (1.068,33 € su 1.807,10 nel periodo
13/08-02/09/2026, un giroconto di rientro sulla P.IVA). E il totale era
elencato come riga sorella delle sue stesse parti, tutte col meno,
come se venissero sottratte due volte. Adesso le parti sono rientrate
sotto il totale che le raccoglie, e `D.dettaglio_periodo` garantisce
per costruzione che la somma torni.

APERTO E CHIUSO, E PERCHE' CAMBIA TUTTO
---------------------------------------
Un periodo e' **chiuso** quando e' arrivato lo stipendio dopo. Finche'
non arriva, il periodo e' aperto: le spese non sono finite e l'entrata
successiva non c'e' ancora, quindi la base del calcolo cambia ogni
giorno e con lei il "consigliato". Al mattino consiglierebbe di piu' di
quanto consigliera' la sera, dopo la spesa.

Per questo il periodo aperto porta una **stima** e non un consiglio:
niente chip "da allineare", niente cifra precompilata nella procedura,
niente riga nell'arretrato, niente avviso in home. Quando lo stipendio
(o il giroconto dalla P.IVA) viene incassato, il periodo si chiude, il
numero si ferma e da quel momento e' un consigliato come gli altri.

La procedura resta comunque disponibile sul periodo aperto, ma per una
ragione diversa: il bonifico si esegue **oggi**, quindi per forza cade
nel periodo aperto, e quello che salda sono i periodi chiusi rimasti
scoperti. La cifra proposta li' e' l'arretrato dei chiusi, non la stima
di quello aperto.

L'ARRETRATO
-----------
Un periodo si "allinea" registrando il bonifico ai salvadanai. Se un
periodo viene saltato non c'e' modo di recuperarlo retrodatando: la
regola del progetto e' che ogni movimento porta la sua data vera (vedi
README, la riconciliazione da 829,78 €), e un movimento appartiene al
periodo che contiene la sua data. Quindi un bonifico fatto oggi per
recuperare agosto finisce, giustamente, nel periodo di oggi.

Quello che serve allora non e' retrodatare ma **vedere l'arretrato**:
`D.arretrato_risparmio` cammina all'indietro fino al primo periodo
saldato e dice quali sono rimasti scoperti e per quanto. E' gia'
successo a luglio 2026 — 2.307,48 € usciti contro 847,49 consigliati,
un recupero di arretrato che la pagina non nominava da nessuna parte,
mostrando solo un periodo che sembrava aver risparmiato il triplo.

Rotte HTML:
  GET /spese/risparmi[?periodo=AAAA-MM-GG]

Rotte JSON:
  GET   /spese/api/risparmi
  POST  /spese/api/risparmi/esegui  {importo, data}
  PATCH /spese/api/risparmi         -> 409, chiuso (vedi sotto)
"""
import json as _json
from datetime import date

from flask import Response, request, jsonify

from . import spese_bp
from . import dati as D
from . import revolut
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_it, data_breve, mese_anno, pct
# Una sola domanda, una sola risposta: "i soldi sono arrivati?" la sa
# il modulo fatture, e la risposta e' la data di incasso (non lo stato).
from fatture.costanti import ha_incassato


# Come si chiamano nel dettaglio le categorie di uscita. Quelle che non
# compaiono qui si mostrano col nome che hanno nel database: meglio un
# nome grezzo che una riga che sparisce.
ETICHETTE_USCITA = {
    "Fisso":           "Spese fisse",
    "Personale":       "Spese personali",
    "Giroconto P.IVA": "Rientro sul conto P.IVA",
    "":                "Senza categoria",
}

# Le uscite che non sono spese: denaro che cambia conto, non che se ne
# va. Restano nel totale — dal conto personale sono uscite davvero, e il
# consigliato si calcola su quello che resta li' — ma chiamarle "spesa"
# e' falso, ed e' il motivo per cui il numero sembrava sbagliato.
NOTE_USCITA = {
    "Giroconto P.IVA": "non è una spesa: è denaro tornato sul conto P.IVA",
}


def _delta(v) -> str:
    """
    Un addendo della cascata: '+1.234,50', '−1.234,50' — ma '0,00' senza
    segno quando e' zero. `eur_segno` su -0.0 stampa '+0,00', perche' in
    Python `-0.0 >= 0` e' vero: in una colonna di sottrazioni quel piu'
    si legge come un'entrata che non c'e'.
    """
    return eur(0) if abs(v) < 0.005 else eur_segno(v)


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _fatture_da_girocontare(client) -> list[dict]:
    """
    Le fatture gia' incassate il cui denaro sta ancora sul conto P.IVA.

    Legge `b2f_fatture` da qui, che e' l'area Spese, e lo fa apposta: il
    passo 1 della procedura non ha senso senza sapere se c'e' qualcosa da
    spostare. La query e' in sola lettura e sotto `try` — se l'area
    Fatture non e' raggiungibile la procedura perde un riquadro, non la
    pagina.

    Il filtro su `data_giroconto` e' in Python e non nella query: il
    "non ancora fatto" e' un NULL, e PostgREST vuole `is.null` mentre
    l'harness di anteprima non lo implementa. Le fatture incassate sono
    poche decine l'anno: filtrarle qui non costa niente. Per lo stesso
    motivo ci sta anche il filtro sull'incasso: `ha_incassato` guarda
    `data_incasso`, non lo stato, perche' dopo l'incasso la fattura
    prosegue verso lo studio e lo SDI e resta pagata.
    """
    try:
        r = (client.table("b2f_fatture")
             .select("id,numero,totale,data_incasso,data_giroconto,stato")
             .neq("stato", "annullata")
             .order("data_incasso", desc=True).execute())
        righe = getattr(r, "data", None) or []
    except Exception:
        return []
    return [f for f in righe
            if ha_incassato(f) and not f.get("data_giroconto")]


def _estremi(p, oggi: str) -> tuple[str, str]:
    """Primo e ultimo giorno del periodo, come li intende la vista."""
    return D.confini_periodo(p, oggi)


def _etichetta_periodo(p, oggi: str, corrente: bool = False) -> str:
    """
    "Agosto 2026 · 13 ago → 2 set".

    Il mese da solo non basta a identificare un periodo — agosto 2026 ne
    contiene due — quindi gli estremi fanno parte del nome, non sono una
    decorazione.
    """
    dal, al = _estremi(p, oggi)
    fine = data_breve(al) if D.periodo_chiuso(p) else "oggi"
    return f"{mese_anno(dal)} · {data_breve(dal)} → {fine}"


def _intervallo(p, oggi: str) -> str:
    """Solo gli estremi: "13 ago → 2 set", oppure "3 set → oggi"."""
    dal, al = _estremi(p, oggi)
    return f"{data_breve(dal)} → {data_breve(al) if D.periodo_chiuso(p) else 'oggi'}"


# Lo stato di un periodo, in una parola, un'emoji e una classe di colore.
#
# Sono quattro e non due. "In corso" non e' un "da allineare" piu' tenue:
# non c'e' niente da allineare finche' il periodo non si chiude (vedi
# `D.periodo_chiuso`). E un bonifico piu' basso del consigliato non e'
# un periodo allineato: luglio 2026 ha 400 € messi via contro 2.142
# consigliati, e mostrava la spunta verde accanto a un numero rosso —
# due segni opposti sulla stessa riga, uno dei due sbagliato.
def _stato_periodo(p) -> tuple[str, str, str]:
    eff = _n(p.get("risparmio_effettivo"))
    cons = _n(p.get("risparmio_consigliato"))
    if eff > 0:
        # Un euro di tolleranza: gli arrotondamenti della vista non devono
        # far comparire un "parziale" su un periodo saldato al centesimo.
        if eff >= cons - 1:
            return ("✅", "allineato", "pos")
        return ("🟡", "sotto il consigliato", "warn")
    if not D.periodo_chiuso(p):
        return ("⏳", "in corso", "accent")
    return ("⚠️", "da allineare", "warn")


def _card_procedura(client, periodo, dal: str, al: str, consigliato: float,
                    gia_messo: float, anteprima: str, arretrato: dict,
                    e_corrente: bool, e_aperto: bool, proposta: float) -> str:
    """
    La procedura di fine periodo: dall'incasso ai salvadanai, un passo
    alla volta e con la conferma di chi la esegue.

    Sostituisce il campo "Risparmio effettivo" che stava qui prima. Non
    e' un cambio di interfaccia: quel campo scriveva un numero su
    `risparmi_periodo` **al posto** del movimento bancario, ed e' la
    seconda strada che la migrazione §8.11 ha chiuso — dopo di lei
    nessuno legge piu' quella colonna. Qui invece si registra l'uscita
    vera dal conto, con la sua data, come la vede la banca.

    Il denaro non lo muove l'app: il bonifico lo fai tu. Questa pagina
    dice **quanto** (la percentuale di `impostazioni` sulla base del
    calcolo), **come si divide** fra i cinque salvadanai, e tiene il
    conto che e' stato fatto.

    **Sul periodo aperto la cifra proposta non e' la sua.** Un periodo
    aperto non ha un consigliato — ha una stima che cambia a ogni spesa
    (vedi `D.periodo_chiuso`) — quindi proporne il versamento sarebbe
    chiedere di spostare un numero provvisorio. Quello che si puo'
    saldare oggi e' l'arretrato dei periodi **chiusi**, ed e' quello che
    la procedura precompila: il bonifico cade comunque nel periodo
    aperto, perche' porta la data di oggi, ma paga i chiusi.

    `gia_messo` arriva da `risparmio_del_periodo(dal, al)` **con
    l'estremo superiore**: senza, guardando un periodo passato si
    conterebbero anche i bonifici dei periodi successivi, e un periodo
    mai allineato sembrerebbe allineato.
    """
    oggi = date.today().isoformat()
    etichetta = _etichetta_periodo(periodo, oggi, e_corrente)

    if gia_messo > 0:
        return f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Procedura — {mese_anno(dal)}</div>
            <span class="chip pos">✅ fatta</span>
          </div>
          <div class="stat">
            <div class="val tnum pos">€ {eur(gia_messo)}</div>
            <div class="lbl">messi via in questo periodo</div>
          </div>
          <p class="small muted mt-3">
            Sono le uscite di categoria "Risparmi" datate fra il
            {data_it(dal)} e il {data_it(al)}, meno gli eventuali rientri.
            Il consigliato era € {eur(consigliato)}.
          </p>
          <a class="btn ghost block mt-4"
             href="/conti/webank/personale?categoria=Risparmi">Vedi i movimenti</a>
        </div>'''

    # --- Periodo aperto, e niente di chiuso da saldare --------------------
    # Nessun campo e nessun bottone: non c'e' un numero da versare. E'
    # il caso in cui l'app prima proponeva la quota del periodo in corso,
    # cioe' una cifra che il giorno dopo era un'altra.
    if e_aperto and proposta <= 0:
        return f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Procedura — {mese_anno(dal)}</div>
            <span class="chip accent">⏳ periodo in corso</span>
          </div>
          <div class="notice info">
            <strong>Non c’è ancora niente da allineare.</strong>
            Questo periodo è aperto: le spese non sono finite e il prossimo
            stipendio non è arrivato, quindi la quota di risparmio è una
            <strong>stima</strong> (€ {eur(consigliato)} con i numeri di
            oggi) e non un importo da spostare. Si fissa quando incassi il
            prossimo stipendio o giroconto dalla P.IVA: da quel momento il
            periodo è chiuso, il conto non cambia più e la procedura
            compare qui con la cifra definitiva.
          </div>
          <p class="small muted mt-3">
            Tutti i periodi chiusi risultano allineati: non c’è arretrato
            da recuperare.
          </p>
        </div>'''

    da_girocontare = _fatture_da_girocontare(client)
    passo1 = ""
    if da_girocontare and e_corrente:
        righe = "".join(
            f'<div class="row"><span class="t">'
            f'<a href="/fatture/{f.get("id")}">{f.get("numero") or ("#" + str(f.get("id")))}</a>'
            f'<span class="sub">incassata il {data_it(f.get("data_incasso"))}</span></span>'
            f'<span class="v tnum">€ {eur(f.get("totale"))}</span></div>'
            for f in da_girocontare[:5])
        passo1 = f'''
          <div class="notice warn">
            <span class="emo">📥</span>
            <strong>Prima:</strong> {len(da_girocontare)} fattur{"a" if len(da_girocontare) == 1 else "e"}
            incassat{"a" if len(da_girocontare) == 1 else "e"} con il denaro ancora
            sul conto P.IVA. Ripartiscil{"a" if len(da_girocontare) == 1 else "e"}
            prima di calcolare il risparmio: la quota si applica a quel che
            resta sul conto personale, e finché l’incasso non è arrivato lì
            quel numero è più basso del vero.
          </div>
          <div class="rows detail mb-4">{righe}</div>'''

    # Da dove viene la cifra precompilata, detto a chiare lettere: sul
    # periodo aperto non è la sua, ed è l'unico posto in cui si può
    # spiegare perché.
    n_scoperti = len(arretrato.get("periodi") or [])
    if e_aperto:
        origine = f'''
          <div class="notice info">
            <span class="emo">⏳</span>
            <strong>Questo periodo è ancora aperto</strong>, quindi non ha un
            risparmio consigliato: con i numeri di oggi la stima è
            € {eur(consigliato)}, ma cambia a ogni spesa e si fissa solo
            quando arriva il prossimo stipendio. La cifra qui sotto è invece
            <strong>l’arretrato {"del periodo già chiuso" if n_scoperti == 1
              else f"dei {n_scoperti} periodi già chiusi"}</strong>
            e mai allineat{"o" if n_scoperti == 1 else "i"}:
            quella è definitiva, e il bonifico la salda.
          </div>'''
    else:
        origine = f'''
          <div class="notice info">
            <span class="emo">🔒</span>
            <strong>Periodo chiuso il {data_it(al)}</strong>: dopo di lui è
            arrivato un altro stipendio, quindi entrate e uscite sono tutte
            quelle che saranno mai e il consigliato di € {eur(consigliato)}
            è definitivo.
          </div>'''

    # Il bonifico porta la data vera, sempre. Un periodo passato non si
    # allinea retrodatando — sarebbe la strada che ha prodotto lo scarto
    # di 829,78 € — quindi qui si dice a chiare lettere dove finira'
    # quel movimento, invece di lasciarlo scoprire dopo.
    fuori_periodo = not (dal <= oggi <= al)
    avviso_data = f'''
      <div class="notice info mt-3" id="avvisoData"
           style="{'' if fuori_periodo else 'display:none'}">
        <span class="emo">📅</span>
        La data è fuori dal periodo che stai guardando
        ({data_it(dal)} – {data_it(al)}): il movimento conterà nel periodo
        che contiene la sua data, non in questo. È corretto così — la data
        di un bonifico è quella in cui la banca lo esegue — e l’arretrato
        qui sopra tiene il conto di quello che resta scoperto.
      </div>'''

    # --- Allineare più periodi in una volta ------------------------------
    # Il bonifico resta UNO, con la sua data vera: non si retrodata niente
    # e non si inventano movimenti per i periodi passati. Quello che
    # cambia e' la cifra proposta, e le proposte sensate sono due —
    # rispondono a due domande diverse (vedi `D.arretrato_risparmio`).
    scelte = []
    if arretrato.get("totale", 0) > 0 and n_scoperti > 1:
        scelte.append((
            arretrato["totale"],
            f"i {n_scoperti} periodi scoperti",
            f"€ {eur(arretrato['totale'])}"))
    mancante = -(arretrato.get("cum_scarto") or 0)
    if mancante > 1 and abs(mancante - arretrato.get("totale", 0)) > 1:
        scelte.append((
            mancante,
            f"tutto l’arretrato dei {arretrato.get('n_periodi', 0)} periodi chiusi",
            f"€ {eur(mancante)}"))

    scorciatoia = ""
    if scelte:
        bottoni = " · ".join(
            f'<button type="button" class="linklike" onclick="metti({v:.2f})">'
            f'{etichetta_b} ({cifra})</button>' for v, etichetta_b, cifra in scelte)
        scorciatoia = f'''
        <p class="hint mt-2">Allinea in una volta: {bottoni}. Resta un bonifico
          solo, con la data di oggi — i periodi passati non si riaprono, e
          l’arretrato qui sopra tiene il conto di quello che resta.</p>'''

    return f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">Procedura — {mese_anno(dal)}</div>
        <span class="chip {"accent" if e_aperto else "warn"}">
          {"⏳ arretrato da saldare" if e_aperto else "⚠️ da allineare"}</span>
      </div>
      {passo1}
      {origine}
      <p class="small muted mt-3">Il bonifico ai salvadanai lo fai tu dalla banca:
        qui si registra che è successo, come uscita vera dal conto. È quello
        che tiene il saldo dell’app uguale a quello di WeBank.</p>
      <div class="field-group mt-4">
        <div class="field">
          <label>Quanto metti via (€)</label>
          <input type="number" step="0.01" min="0" inputmode="decimal" id="f_imp"
                 value="{proposta:.2f}" oninput="aggiornaQuote()">
        </div>
        <div class="field">
          <label>Data del bonifico</label>
          <input type="date" id="f_data" value="{oggi}" onchange="controllaData()">
        </div>
      </div>
      {avviso_data}
      <div class="rows detail mt-3">{anteprima}</div>
      <div class="actions mt-4">
        <button type="button" class="btn block" id="btnEsegui"
                onclick="onEsegui()">Registra il bonifico ai salvadanai</button>
      </div>
      <p class="hint mt-2">Cambia la cifra se hai spostato un importo diverso:
        quello che conta è che qui ci sia il numero che è uscito davvero dal
        conto.</p>
      {scorciatoia}
    </div>'''


def _card_posizione(arretrato: dict, periodi: list) -> str:
    """
    La posizione complessiva: consigliato contro messo via, da sempre.

    E' il numero che mancava. La pagina rispondeva solo a "il mese scorso
    l'ho fatto?", e quella domanda guarda gli ultimi periodi: al
    20/09/2026 dava 2.577,01. Ma sommando tutti i diciannove mesi lo
    scarto e' 3.630,69 — piu' del doppio, accumulato un pezzo alla volta
    senza che niente lo mostrasse. Un periodo che chiude in pari non
    riporta a zero quello che si e' perso prima.
    """
    cons = _n(arretrato.get("cum_consigliato"))
    eff = _n(arretrato.get("cum_effettivo"))
    scarto = _n(arretrato.get("cum_scarto"))
    if not cons:
        return ""
    primo = periodi[-1] if periodi else {}
    da_quando = mese_anno(primo.get("data_bonifico")) or "sempre"
    in_pari = scarto >= -1
    return f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">La posizione complessiva</div>
        <span class="chip {"pos" if in_pari else "warn"}">
          {"in pari" if in_pari else "sotto di € " + eur(abs(scarto), 0)}</span>
      </div>
      <div class="rows detail">
        <div class="row">
          <span class="t">Consigliato in tutto
            <span class="sub">{arretrato.get("n_periodi", 0)} periodi chiusi,
              da {da_quando} · quello in corso non conta, la sua è una
              stima</span></span>
          <span class="v tnum">€ {eur(cons)}</span>
        </div>
        <div class="row">
          <span class="t">Messo via davvero
            <span class="sub">le uscite di categoria «Risparmi», al netto
              dei rientri</span></span>
          <span class="v tnum pos">€ {eur(eff)}</span>
        </div>
        <div class="row tot">
          <span class="t">Scarto accumulato</span>
          <span class="v tnum {"pos" if in_pari else "neg"}">{eur_segno(scarto)}</span>
        </div>
      </div>
      <p class="small muted mt-3">
        {"Da quando tieni il conto hai messo via quanto consigliato, o di più."
         if in_pari else
         f"È un'altra domanda da «il mese scorso l'ho fatto?»: quella guarda "
         f"gli ultimi periodi scoperti, questa somma tutto. Un periodo chiuso "
         f"in pari non recupera quello che manca dai periodi prima, e lo "
         f"scarto resta finché non si mette via di più del consigliato."}
      </p>
    </div>'''


def _card_dettaglio(dettaglio, prima: float, bonifico: float,
                    base: float, consigliato: float, effettivo: float,
                    perc: float, dal: str, al: str, e_corrente: bool,
                    e_aperto: bool) -> str:
    """
    La cascata che porta dal saldo di partenza al risparmio consigliato.

    Ogni riga e' un addendo, il totale sta sotto le sue parti e non
    accanto a loro, e la somma torna: e' la differenza fra una schermata
    che si puo' verificare e una di cui bisogna fidarsi.
    """
    righe = [f'''
      <div class="row">
        <span class="t">Sul conto prima dello stipendio
          <span class="sub">quel che era rimasto dal periodo prima</span></span>
        <span class="v tnum">€ {eur(prima)}</span>
      </div>
      <div class="row">
        <span class="t">Stipendio / giroconto dalla P.IVA
          <span class="sub">del {data_it(dal)}, apre il periodo</span></span>
        <span class="v tnum pos">{_delta(bonifico)}</span>
      </div>''']

    for cat, val in dettaglio.get("entrate") or []:
        righe.append(f'''
      <div class="row voce">
        <span class="t">{cat or "Altra entrata"}</span>
        <span class="v tnum pos">{_delta(val)}</span>
      </div>''')

    tot_uscite = _n(dettaglio.get("tot_uscite"))
    quanti = dettaglio.get("n_uscite") or 0
    righe.append(f'''
      <div class="row">
        <span class="t">Speso nel periodo
          <span class="sub">{quanti} moviment{"o" if quanti == 1 else "i"}
            fra il {data_it(dal)} e il {data_it(al)}</span></span>
        <span class="v tnum neg">{_delta(-tot_uscite)}</span>
      </div>''')
    for cat, val in dettaglio.get("uscite") or []:
        nota = NOTE_USCITA.get(cat)
        sub = f'<span class="sub">{nota}</span>' if nota else ""
        righe.append(f'''
      <div class="row voce">
        <span class="t">{ETICHETTE_USCITA.get(cat, cat or "Senza categoria")}{sub}</span>
        <span class="v tnum">{_delta(-val)}</span>
      </div>''')

    saldo_periodo = round(bonifico + _n(dettaglio.get("tot_entrate"))
                          - tot_uscite, 2)
    fatto = effettivo > 0
    quota = effettivo if fatto else consigliato
    # Su un periodo aperto la stessa formula da' un numero provvisorio: la
    # riga lo dice, invece di stampare una cifra che domani sara' un'altra
    # e lasciar credere che fosse una decisione.
    if fatto:
        titolo_quota, sub_quota, cls_quota = (
            "Messo via", f"{pct(perc)} della base", "pos")
    elif e_aperto:
        titolo_quota, sub_quota, cls_quota = (
            "Stima del risparmio",
            f"{pct(perc)} della base, ma provvisoria: il periodo non è "
            f"chiuso e la base cambia a ogni movimento", "")
    else:
        titolo_quota, sub_quota, cls_quota = (
            "Risparmio consigliato",
            f"{pct(perc)} della base, da spostare sui salvadanai", "accent")
    righe.append(f'''
      <div class="row tot">
        <span class="t">Base del calcolo{'' if not e_aperto else
          '<span class="sub">ancora in movimento: mancano le spese da qui a '
          'fine periodo e l’entrata che lo chiude</span>'}</span>
        <span class="v tnum">€ {eur(base)}</span>
      </div>
      <div class="row">
        <span class="t">{titolo_quota}
          <span class="sub">{sub_quota}</span></span>
        <span class="v tnum {cls_quota}">{_delta(-quota)}</span>
      </div>
      <div class="row tot">
        <span class="t">Sul conto dopo il risparmio</span>
        <span class="v tnum">€ {eur(base - quota)}</span>
      </div>''')

    quando = (f"dal {data_it(dal)} — ancora aperto, si chiude col prossimo "
              f"stipendio" if e_aperto
              else f"dal {data_it(dal)} al {data_it(al)} — chiuso")
    if fatto and quota >= consigliato - 1:
        chip = '<span class="chip pos">✅ allineato</span>'
    elif fatto:
        chip = '<span class="chip warn">🟡 sotto il consigliato</span>'
    elif e_aperto:
        chip = '<span class="chip accent">⏳ in corso</span>'
    else:
        chip = '<span class="chip warn">⚠️ da allineare</span>'
    return f'''
    <div class="card">
      <div class="card-head">
        <div class="eyebrow">Il conto del periodo</div>
        {chip}
      </div>
      <div class="h2" style="margin:0 0 2px">{mese_anno(dal)}</div>
      <div class="small muted mb-4">{quando}</div>
      <div class="rows detail">{"".join(righe)}</div>
      <details class="explain mt-3">
        <summary>Perché il consigliato non è una percentuale dello stipendio</summary>
        <p class="small muted mt-2">
          La quota si applica alla <strong>base del calcolo</strong>, cioè a
          tutto quello che hai sul conto a fine periodo — il residuo del
          periodo prima compreso — non al solo stipendio. Preso da solo,
          questo periodo si chiude a {_delta(saldo_periodo)}; è per questo
          che un periodo può andare in rosso e avere comunque un consigliato
          sopra zero, oppure chiudere bene e consigliarti più del suo
          stipendio: i soldi che contano sono quelli che ci sono, non quelli
          che sono arrivati.
        </p>
      </details>
    </div>'''


@spese_bp.get("/risparmi")
def risparmi_pagina():
    breadcrumb = [("Risparmi", "")]
    client = D.sb()
    if client is None:
        return _render('<div class="notice warn">Supabase non configurato.</div>',
                       breadcrumb=breadcrumb)

    periodi = D.periodi_risparmio(client)
    imp = D.impostazioni(client)
    oggi = date.today().isoformat()

    if not periodi:
        corpo = f'''<div class="empty">{icon("spese")}
          <div class="t">Nessun periodo</div>
          <div class="s">I periodi nascono dalle entrate di categoria
            "Stipendio" o "Giroconto P.IVA": registrane una e questa
            pagina si popola.</div></div>'''
        return _render(corpo, breadcrumb=breadcrumb)

    # --- Quale periodo stiamo guardando ---------------------------------
    # La chiave e' `data_bonifico`, che e' anche l'identita' del periodo
    # nella vista. Un valore che non corrisponde a niente (link vecchio,
    # URL scritto a mano) non e' un errore: si torna al corrente.
    scelto = (request.args.get("periodo") or "").strip()[:10]
    corrente = next((p for p in periodi
                     if str(p.get("data_bonifico") or "")[:10] == scelto),
                    periodi[0])
    e_corrente = corrente is periodi[0]
    # Aperto = non e' ancora arrivato lo stipendio successivo. Quasi
    # sempre coincide col piu' recente, ma non e' la stessa cosa e la
    # distinzione che conta e' questa: e' `prossimo_bonifico` a dire se i
    # numeri del periodo sono fermi (vedi `D.periodo_chiuso`).
    e_aperto = not D.periodo_chiuso(corrente)
    dal, al = _estremi(corrente, oggi)

    n = _n

    # Quote di destinazione del risparmio, dalle impostazioni in vigore.
    # La corrispondenza fra il secchiello, la sua percentuale e la colonna
    # della vista sta in `revolut.SALVADANAI`, una volta sola: e' la stessa
    # che serve per confrontarli con i saldi Revolut, e due elenchi
    # paralleli prima o poi divergono.
    quote = [(chiave_rev, nome_app, colonna, imp.get(campo_perc))
             for chiave_rev, _, nome_app, campo_perc, colonna, _
             in revolut.SALVADANAI]

    # --- I numeri del periodo scelto ------------------------------------
    consigliato = n(corrente.get("risparmio_consigliato"))
    prima = n(corrente.get("saldo_iniziale"))
    bonifico = n(corrente.get("bonifico"))
    altre = n(corrente.get("altre_entrate"))
    speso = n(corrente.get("speso"))
    # La base su cui si calcola il consigliato. La ricalcoliamo dai suoi
    # addendi invece di leggere "Totale Rimanente (finale)" perche' e'
    # esattamente la somma che la cascata mostra riga per riga: se i due
    # numeri divergessero, il dettaglio smetterebbe di quadrare in
    # silenzio — che e' il guasto che questa pagina aveva.
    base = round(prima + bonifico + altre - speso, 2)
    # La percentuale in vigore **in quel periodo**, non l'ultima scritta
    # in `impostazioni`: la vista usa la riga valida alla data del
    # bonifico, e sui periodi prima del 25/02/2026 era il 25%, non il 35%.
    perc = (consigliato / base) if base > 0 else n(imp.get("percentuale_risparmio"))

    # La vista espone sempre un numero (mai vuoto: coalesce a 0 quando il
    # periodo non e' ancora stato registrato). Non potendo distinguere
    # "registrato a zero" da "mai registrato", trattiamo lo zero come "non
    # ancora fatto" — nella pratica nessuno registra zero di proposito.
    effettivo = n(corrente.get("risparmio_effettivo"))
    gia_registrato = effettivo > 0

    dettaglio = D.dettaglio_periodo(client, dal, al)
    arretrato = D.arretrato_risparmio(periodi)

    # La cifra che la procedura precompila. Su un periodo chiuso e' il suo
    # consigliato, che e' definitivo. Su quello aperto **non** e' la sua
    # stima — sarebbe chiedere di spostare un numero che domani e' un
    # altro — ma l'arretrato dei periodi gia' chiusi: il bonifico porta la
    # data di oggi, quindi cade qui per forza, ma quello che salda sta
    # dietro (vedi `_card_procedura`).
    proposta = round(arretrato.get("totale", 0.0) if e_aperto
                     else consigliato, 2)

    # --- Il menu dei periodi --------------------------------------------
    # Cronologico e non alfabetico: qui la sequenza e' informazione (vedi
    # CLAUDE.md, i menu che restano nel loro ordine naturale).
    # Le `data-*` non servono al `<select>` nativo: le legge il
    # componente Fiori di shared/theme.py, che al posto della tendina di
    # sistema disegna una lista con icona, estremi e importo. Se il JS non
    # gira resta il select con il suo testo, che infatti continua a
    # contenere tutto quello che serve a distinguere i periodi.
    opzioni = []
    for p in periodi:
        chiave = str(p.get("data_bonifico") or "")[:10]
        emo, stato, cls = _stato_periodo(p)
        cifra = (n(p.get("risparmio_effettivo")) or
                 n(p.get("risparmio_consigliato")))
        sel = " selected" if p is corrente else ""
        opzioni.append(
            f'<option value="{chiave}"{sel}'
            f' data-icona="{emo}" data-sub="{_intervallo(p, oggi)}"'
            f' data-breve="{_etichetta_periodo(p, oggi, p is periodi[0])}"'
            f' data-titolo="{mese_anno(p.get("data_bonifico")) or (p.get("mese") or "—").capitalize()}"'
            f' data-info="€ {eur(cifra, 0)}" data-stato="{cls}"'
            f' data-nota="{stato}">'
            f'{_etichetta_periodo(p, oggi, p is periodi[0])} — {stato}</option>')
    torna = ("" if e_corrente else
             '<a class="btn ghost" href="/risparmi">Torna al periodo in corso</a>')
    toolbar = f'''
    <div class="toolbar">
      <select class="select-pill" aria-label="Periodo" style="min-width:260px"
              data-etichetta="Periodo di paga" data-icona="📅"
              data-aiuto="Ogni periodo va da uno stipendio al successivo, non dal 1 al 31: un mese può contenerne due."
              onchange="vaiA(this.value)">{"".join(opzioni)}</select>
      {torna}
    </div>'''

    # --- L'arretrato ----------------------------------------------------
    # Solo periodi **chiusi**: `D.arretrato_risparmio` salta quello ancora
    # aperto, perche' il suo consigliato e' una stima e un arretrato fatto
    # di stime non e' un arretrato.
    banner = ""
    scoperti = arretrato.get("periodi") or []
    if scoperti:
        link = " · ".join(
            f'<a href="/risparmi?periodo={str(p.get("data_bonifico") or "")[:10]}">'
            f'{_etichetta_periodo(p, oggi, p is periodi[0])}</a>'
            for p in scoperti)
        ecc = arretrato.get("eccedenza") or 0
        nota_ecc = (f" Nell'ultimo periodo saldato avevi messo via € {eur(ecc)} "
                    f"in più del consigliato: se quel margine copriva già questi, "
                    f"l'arretrato vero è più basso." if ecc > 0 else "")
        # Il bottone porta alla procedura con la cifra gia' dentro: e'
        # l'"allinea tutto" — un bonifico solo, con la data di oggi, per
        # la somma dei periodi scoperti. Non retrodata niente e non
        # inventa un movimento per ogni periodo: la banca ne vede uno.
        azione = ("" if not e_corrente else
                  f'<button type="button" class="btn sm mt-3" '
                  f'onclick="allineaTutto({arretrato.get("totale", 0):.2f})">'
                  f'Allinea tutti e {len(scoperti)} → € {eur(arretrato.get("totale"))}'
                  f'</button>' if len(scoperti) > 1 else "")
        banner = f'''
    <div class="notice warn mb-3">
      <span class="emo">⚠️</span>
      <strong>{len(scoperti)} period{"o chiuso" if len(scoperti) == 1 else "i chiusi"} senza
      un bonifico ai salvadanai</strong>, per € {eur(arretrato.get("totale"))}
      di risparmio consigliato in tutto: {link}.{nota_ecc}
      {azione}
    </div>'''
    elif e_aperto:
        # Niente arretrato e periodo in corso: e' lo stato normale, e
        # merita una riga che lo dica invece del silenzio — altrimenti
        # l'assenza del banner si legge come "non ho ancora capito".
        banner = f'''
    <div class="notice mb-3">
      <span class="emo">⏳</span>
      <strong>Periodo in corso</strong>: i periodi chiusi sono tutti allineati.
      Qui sotto c’è la stima con i numeri di oggi — diventa un importo da
      spostare quando incassi il prossimo stipendio e il periodo si chiude.
    </div>'''

    # --- Quanto dovrebbe esserci in ogni salvadanaio, e quanto c'è ------
    # La quota per periodo dice poco da sola: quello che serve sapere e'
    # se il secchiello, sommato da sempre, contiene quello che dovrebbe.
    # Il "dovrebbe" e' la somma delle quote di tutti i periodi; il "c'e'"
    # arriva dai saldi Revolut, che sono l'unica misura indipendente.
    rev = revolut.saldo_revolut(client)
    reali = rev.get("salvadanai") or {}
    blocco_salvadanai = ""
    if reali:
        righe_sv = ""
        for chiave_rev, nome, colonna, _p in quote:
            atteso = round(sum(n(x.get(colonna)) for x in periodi), 2)
            # "Altro" non e' un salvadanaio: quella quota va dritta negli
            # investimenti, e infatti nello snapshot Revolut la chiave non
            # esiste proprio. Confrontarla con un secchiello inesistente
            # dava un ammanco fantasma di 3.134,43 €, rosso e permanente.
            if chiave_rev == "altro":
                reale = n(rev.get("investimenti"))
                if not atteso and not reale:
                    continue
                righe_sv += f'''
          <div class="row">
            <span class="t">{nome} → investimenti
              <span class="sub">ci sono finiti € {eur(atteso)} di quote ·
                a fianco il <strong>valore</strong> del portafoglio, che
                comprende anche quanto è cresciuto: i due numeri non sono
                confrontabili come gli altri</span></span>
            <span class="v tnum">€ {eur(reale)}</span>
          </div>'''
                continue
            reale = n(reali.get(chiave_rev))
            if not atteso and not reale:
                continue
            scarto = round(reale - atteso, 2)
            cls = "pos" if scarto >= -1 else "neg"
            verso = "in più" if scarto >= 0 else "in meno"
            righe_sv += f'''
          <div class="row">
            <span class="t">{nome}
              <span class="sub">dovrebbe averne € {eur(atteso)} ·
                € {eur(abs(scarto))} {verso}</span></span>
            <span class="v tnum {cls}">€ {eur(reale)}</span>
          </div>'''
        if righe_sv:
            tot_reale = round(sum(n(v) for v in reali.values()), 2)
            blocco_salvadanai = f'''
        <div class="card">
          <div class="card-head">
            <div class="eyebrow">Nei salvadanai, davvero</div>
            <span class="chip">€ {eur(tot_reale, 0)}</span>
          </div>
          <div class="rows detail">{righe_sv}</div>
          <p class="small muted mt-3">
            A destra quanto c'è oggi su Revolut (saldi al
            {data_it(rev.get("data"))}); sotto la riga, quanto dovrebbe
            esserci sommando le quote di tutti i periodi registrati. Uno
            scarto non è di per sé un errore — dai salvadanai si preleva —
            ma è l'unico posto in cui si vede.
          </p>
        </div>'''
    elif rev.get("disponibile"):
        blocco_salvadanai = f'''
        <div class="card">
          <div class="card-head"><div class="eyebrow">Nei salvadanai, davvero</div></div>
          <p class="small muted">
            Su Revolut ci sono € {eur(rev.get("risparmi"), 0)} di risparmi, ma
            non è registrato come sono divisi fra i secchielli: l'estratto ne
            dà solo il totale. Scrivilo una volta e questa scheda mostrerà,
            secchiello per secchiello, quanto c'è contro quanto dovrebbe
            esserci.
          </p>
          <a class="btn ghost block mt-4" href="/conti/revolut">Vai a Revolut</a>
        </div>'''

    # --- Come si divide -------------------------------------------------
    # Sulla cifra che conta adesso: quella messa via se il periodo e' gia'
    # allineato, il consigliato altrimenti. Prima leggeva le colonne
    # `quota_*` della vista, che valgono `effettivo × percentuale`: su un
    # periodo non ancora allineato l'effettivo e' zero, e la scheda
    # mostrava cinque zeri proprio quando serviva sapere come dividere.
    base_quote = effettivo if gia_registrato else (proposta or consigliato)
    quote_html = "".join(f'''
      <div class="row">
        <span class="t">{nome}<span class="sub">{pct(n(p))} del risparmio</span></span>
        <span class="v tnum">€ {eur(base_quote * n(p))}</span>
      </div>''' for _, nome, _col, p in quote if n(p) > 0)

    # Il tetto superiore c'e' per i periodi **chiusi** e non per quello
    # aperto, ed e' una differenza voluta. Su un periodo passato senza
    # tetto si conterebbero i bonifici dei periodi successivi, e uno mai
    # allineato sembrerebbe allineato. Sul periodo aperto invece il tetto
    # riaprirebbe il buco opposto, quello che il vecchio codice evitava
    # apposta: un bonifico datato domani e' gia' registrato, e fermarsi a
    # oggi direbbe di no — la procedura lo farebbe registrare due volte.
    gia_messo = D.risparmio_del_periodo(client, dal, None if e_corrente else al)


    quote_js = _json.dumps(
        [{"chiave": k, "perc": n(p)} for k, _nome, _col, p in quote if n(p) > 0],
        ensure_ascii=False)
    anteprima = "".join(
        f'<div class="row"><span class="t">{nome}'
        f'<span class="sub">{pct(n(p))}</span></span>'
        f'<span class="v tnum" id="q_{k}">€ {eur(proposta * n(p))}</span></div>'
        for k, nome, _col, p in quote if n(p) > 0)
    procedura_html = _card_procedura(
        client, corrente, dal, al, consigliato=consigliato,
        gia_messo=gia_messo, anteprima=anteprima, arretrato=arretrato,
        e_corrente=e_corrente, e_aperto=e_aperto, proposta=proposta)

    def _riga_storico(p):
        # ".v" e' pensato per UN numero, riga singola, mai per contenuto
        # annidato (vedi shared/design.py: white-space:nowrap): il
        # confronto consigliato/effettivo va nella riga ".sub", che invece
        # va a capo normalmente dentro ".rows.detail".
        cons = n(p.get("risparmio_consigliato"))
        eff = n(p.get("risparmio_effettivo"))
        chiave = str(p.get("data_bonifico") or "")[:10]
        emo, stato, cls_stato = _stato_periodo(p)
        chiuso = D.periodo_chiuso(p)
        # "consigliato" su un periodo aperto sarebbe una parola di troppo:
        # quel numero non e' un consiglio ma una fotografia di oggi.
        voce = "consigliato" if chiuso else "stima di oggi"
        if eff > 0:
            cls_v = "pos" if eff >= cons else "neg"
            valore = eff
            extra = f' · messi via € {eur(eff, 0)} ({eur_segno(eff - cons, 0)})'
        elif not chiuso:
            cls_v = ""
            valore = cons
            extra = " · si fissa col prossimo stipendio"
        else:
            cls_v = ""
            valore = cons
            # Non "mai allineato": e' un giudizio, e spesso falso — quel
            # periodo puo' essere coperto da un bonifico successivo, che
            # per forza sta in un altro periodo. Qui si dice il fatto.
            extra = " · nessun bonifico in questo periodo"
        # Gli estremi, come nel menu: in agosto 2026 sono arrivati due
        # giroconti, quindi "Agosto 2026" compare due volte, e senza il
        # periodo scritto accanto le due righe sono indistinguibili. Non
        # sono un doppione: sono due periodi di paga veri.
        qui = " is-qui" if p is corrente else ""
        return f'''
      <div class="row clickable per{qui}"
           onclick="vaiA('{chiave}')">
        <span class="per-emo" title="{stato}">{emo}</span>
        <span class="t">{mese_anno(p.get("data_bonifico")) or (p.get("mese") or "—").capitalize()}
          <span class="sub"><span class="per-est">{_intervallo(p, oggi)}</span>
            <span class="per-st {cls_stato}">{stato}</span>
            <span class="per-num">{voce} € {eur(cons, 0)}{extra}</span></span></span>
        <span class="v tnum {cls_v}">€ {eur(valore, 0)}</span>
      </div>'''

    storico = "".join(_riga_storico(p) for p in periodi[:12])

    dettaglio_html = _card_dettaglio(
        dettaglio, prima=prima, bonifico=bonifico, base=base,
        consigliato=consigliato, effettivo=effettivo, perc=perc,
        dal=dal, al=al, e_corrente=e_corrente, e_aperto=e_aperto)

    entrato = round(bonifico + altre, 2)
    dopo = round(base - (effettivo if gia_registrato else consigliato), 2)

    # Il numero grande in cima. Su un periodo aperto non e' "da mettere
    # via": e' una stima, e chiamarla col nome di un importo da eseguire
    # era esattamente il fraintendimento — un numero che cambia a ogni
    # spesa presentato come una decisione presa.
    if gia_registrato:
        kpi_val, kpi_lbl, kpi_cls = effettivo, "Messo via", "pos"
        kpi_hint = f"{pct(perc)} di € {eur(base, 0)}"
    elif e_aperto:
        kpi_val, kpi_lbl, kpi_cls = consigliato, "Stima, periodo in corso", ""
        kpi_hint = (f"{pct(perc)} di € {eur(base, 0)} · cambia a ogni spesa, "
                    f"si fissa col prossimo stipendio")
    else:
        kpi_val, kpi_lbl, kpi_cls = consigliato, "Da mettere via", "accent"
        kpi_hint = f"{pct(perc)} di € {eur(base, 0)} · consigliato, periodo chiuso"

    body = f'''
    {toolbar}
    {banner}
    <div class="grid kpi lead mb-3">
      <div class="card"><div class="stat">
        <div class="val tnum {kpi_cls}">€ {eur(kpi_val)}</div>
        <div class="lbl">{kpi_lbl}</div>
        <div class="hint">{kpi_hint}</div>
      </div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum neg">€ {eur(speso, 0)}</div>
        <div class="lbl">Speso {"finora" if e_aperto else "nel periodo"}</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum pos">€ {eur(entrato, 0)}</div>
        <div class="lbl">Entrato {"finora" if e_aperto else "nel periodo"}</div></div></div>
      <div class="card"><div class="stat sm">
        <div class="val tnum">€ {eur(dopo, 0)}</div>
        <div class="lbl">Sul conto dopo il risparmio</div></div></div>
    </div>

    <div class="grid split">
      <div class="stack">
        {dettaglio_html}

        {_card_posizione(arretrato, periodi)}

        <div class="card">
          <div class="card-head"><div class="eyebrow">Tutti i periodi</div></div>
          <div class="rows detail">{storico}</div>
          <p class="small muted mt-2">Tocca una riga per aprire quel periodo.
            Sotto il mese ci sono gli estremi: un mese solare può contenere due
            periodi — in agosto 2026 sono arrivati due giroconti, a luglio 2025
            stipendio e tredicesima — e sono periodi di paga distinti, non
            doppioni. A destra quanto hai messo via se c'è stato un bonifico,
            altrimenti il consigliato. ✅ allineato · 🟡 un bonifico
            c'è stato ma sotto il consigliato · ⚠️ chiuso e scoperto ·
            ⏳ ancora in corso, quindi con una stima e non un consigliato.</p>
        </div>
      </div>

      <div class="stack">
        {procedura_html}

        {f"""<div class="card">
          <div class="card-head">
            <div class="eyebrow">Come si divide</div>
            <span class="chip">€ {eur(base_quote, 0)}</span>
          </div>
          <div class="rows detail">{quote_html}</div>
          <p class="small muted mt-3">
            {"Come si è diviso quello che hai messo via in questo periodo."
             if gia_registrato else
             "Come si dividerebbe la stima di oggi. Non è ancora una cifra "
             "da spostare: il periodo è aperto e il numero cambia fino al "
             "prossimo stipendio."
             if e_aperto and not proposta else
             "Come si dividerebbe la cifra proposta qui accanto. Il bonifico "
             "è uno solo: la ripartizione la fai tu su Revolut, spostando "
             "queste cifre nei secchielli."}
          </p>
        </div>""" if quote_html else ""}

        {blocco_salvadanai}
      </div>
    </div>

    <div id="toast" class="toast"></div>
    <script>
      const PERIODO = {_json.dumps({"dal": dal, "al": al}, ensure_ascii=False)};

      function vaiA(chiave) {{
        if (!chiave) return;
        location.href = '/risparmi?periodo=' + encodeURIComponent(chiave);
      }}

      function toast(msg, cls) {{
        const t = document.getElementById('toast');
        t.textContent = msg; t.className = 'toast show ' + (cls || '');
        setTimeout(()=>{{ t.className = 'toast ' + (cls || ''); }}, 2600);
      }}
      const QUOTE = {quote_js};

      // L'anteprima si aggiorna mentre scrivi: la domanda vera non e'
      // "quanto metto via" ma "quanto finisce in ciascun secchiello", e
      // vederla dopo aver confermato e' troppo tardi.
      function aggiornaQuote() {{
        const el = document.getElementById('f_imp');
        if (!el) return;
        const v = Number(el.value || 0);
        QUOTE.forEach(q => {{
          const t = document.getElementById('q_' + q.chiave);
          if (t) t.textContent = '€ ' + (v * q.perc).toLocaleString('it-IT',
            {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
        }});
      }}

      function metti(v) {{
        const el = document.getElementById('f_imp');
        if (!el) return;
        el.value = v.toFixed(2);
        aggiornaQuote();
        el.focus();
      }}

      // "Allinea tutto": non registra da solo: porta alla procedura con
      // la cifra dentro, e la conferma resta quella di sempre. Un
      // bonifico da qualche migliaio di euro non deve partire da un
      // click su un banner.
      function allineaTutto(v) {{
        const el = document.getElementById('f_imp');
        if (!el) return;
        metti(v);
        el.closest('.card').scrollIntoView({{behavior: 'smooth', block: 'center'}});
      }}

      // Un bonifico appartiene al periodo che contiene la sua data: se la
      // data cade fuori da quello che stai guardando, e' giusto che sia
      // cosi' ma va detto prima, non scoperto dopo.
      function controllaData() {{
        const d = document.getElementById('f_data');
        const box = document.getElementById('avvisoData');
        if (!d || !box) return;
        const fuori = !(d.value >= PERIODO.dal && d.value <= PERIODO.al);
        box.style.display = fuori ? '' : 'none';
      }}

      async function onEsegui() {{
        const v = Number(document.getElementById('f_imp').value || 0);
        const quando = document.getElementById('f_data').value;
        if (!(v > 0)) {{ toast('Importo non valido', 'err'); return; }}
        // Le virgolette e gli a-capo qui dentro finiscono in JS, non in
        // Python: servono i doppi backslash. Con uno solo Python li
        // consuma, la stringa JS si chiude a meta' frase e va in errore
        // di sintassi TUTTO lo script — compresi i bottoni piu' sotto.
        if (!confirm("Registro un'uscita di € " + v.toLocaleString('it-IT',
            {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) +
            ' dal conto personale verso i salvadanai, con data ' + quando +
            '.\\n\\nIl bonifico vero lo fai tu dalla banca: qui si registra '
            + "che e' successo.")) return;
        const btn = document.getElementById('btnEsegui');
        btn.disabled = true;
        try {{
          const r = await fetch('/spese/api/risparmi/esegui', {{
            method: 'POST', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{importo: v, data: quando}}),
          }});
          const j = await r.json();
          if (!r.ok) {{ toast(j.error || 'Errore', 'err'); btn.disabled = false; return; }}
          toast('Bonifico registrato', 'ok');
          setTimeout(()=>location.reload(), 800);
        }} catch (e) {{
          toast('Errore rete: ' + e.message, 'err'); btn.disabled = false;
        }}
      }}
    </script>'''

    return _render(body, breadcrumb=breadcrumb)


@spese_bp.get("/spese/api/risparmi")
def api_risparmi():
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    return jsonify(D.periodi_risparmio(client))


@spese_bp.post("/spese/api/risparmi/esegui")
def api_risparmi_esegui():
    """
    Il passo 2 della procedura: registra il bonifico ai salvadanai.

    Body: {"importo": 812.40, "data": "2026-08-31"}

    Scrive **un'uscita vera** sul conto personale, categoria "Risparmi",
    passando da `spese/dati.py` come ogni altra scrittura. Non divide il
    movimento in cinque righe: la banca vede un bonifico, e la
    ripartizione fra i secchielli la ricalcola `v_risparmi_mese` dalle
    percentuali di `impostazioni`.

    Non prende il periodo, ed e' voluto: un movimento appartiene al
    periodo che contiene la sua **data**, e non c'e' un secondo posto in
    cui dichiararlo. E' la stessa regola per cui non esiste piu' il
    PATCH qui sotto.
    """
    client = D.sb()
    if client is None:
        return jsonify({"error": "supabase not configured"}), 503
    body = request.get_json(silent=True) or {}
    quando = (body.get("data") or "").strip() or None
    esito = D.registra_bonifico_risparmio(
        client, body.get("importo"), quando,
        descrizione="Bonifico ai salvadanai (Revolut)")
    if esito.get("error"):
        return jsonify(esito), 400
    return jsonify({"ok": True, **esito})


@spese_bp.patch("/spese/api/risparmi")
def api_risparmi_aggiorna():
    """
    Chiuso: scriveva su una colonna che non legge piu' nessuno.

    Fino alla migrazione README §8.11 questo endpoint dichiarava il
    risparmio del periodo su `risparmi_periodo.effettivo_risparmio`, e
    quel numero *sostituiva* il movimento bancario nel calcolo del
    saldo. Da quando il risparmio e' un'uscita vera di `spese`,
    `v_risparmi_mese` calcola l'effettivo dai movimenti e quella colonna
    non entra piu' in nessun conto: continuare ad accettarlo vorrebbe
    dire scrivere in un posto dove nessuno guarda, che e' peggio di un
    errore — sembra funzionare.

    Risponde 409 invece di sparire perche' una scheda rimasta aperta da
    prima del deploy lo chiamerebbe comunque, e deve sapere perche' non
    ha funzionato.
    """
    return jsonify({
        "error": "Il risparmio non si dichiara più: si registra come "
                 "movimento vero. Usa la procedura di fine periodo su "
                 "/spese/risparmi (o POST /spese/api/risparmi/esegui).",
        "sostituito_da": "/spese/api/risparmi/esegui",
    }), 409


def _render(content: str, breadcrumb=None) -> Response:
    return Response(render_page(section="risparmi", eyebrow="Risparmi",
                                title_html='I miei <em>risparmi</em>',
                                content=content, breadcrumb=breadcrumb),
                    mimetype="text/html")
