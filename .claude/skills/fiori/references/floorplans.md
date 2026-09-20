# I floorplan, e che forma dànno alle pagine di B2F

In Fiori il layout non si inventa: ogni pagina è uno di pochi **page
type** noti, e il tipo decide dove vanno titolo, azioni, filtri e
contenuto. Tutti poggiano sulla **dynamic page**.

## La dynamic page

Tre aree, in quest'ordine:

1. **Header title** — sempre visibile. Dice *dove sei* e porta le azioni
   globali della pagina.
2. **Header content** — opzionale e *collassabile*: si stringe mentre
   scorri, così informazioni ricche e filtri non rubano schermo per
   sempre.
3. **Content**, e in fondo una **footer toolbar** opzionale per le azioni
   che chiudono (salva, annulla).

Qui lo fa già `shared/theme.py::render_page()`: `topbar` (titolo +
eyebrow + azioni) → `crumb` → `content` → `fab`. Il FAB gioca il ruolo
della footer toolbar per l'azione principale.

**La regola che si dimentica**: l'azione principale sta nell'header o nel
footer, **mai** in mezzo al contenuto. Se una pagina ha un bottone
importante perso fra due card, è nel posto sbagliato.

## Overview page

*A cosa serve*: dare in un colpo d'occhio lo stato delle cose e far
saltare dove serve agire. Non è una pagina da leggere riga per riga: è
una da scorrere in tre secondi.

*Com'è fatta*: card indipendenti, ognuna con un titolo e **una** domanda
a cui risponde. Chi la guarda non deve montare i pezzi da solo.

*Qui*: la home `/`, e le landing `/conti`, `/fatture`,
`/impostazioni`.

*Cosa sbagliare non conviene*: mettere in una card un numero senza il
suo contesto. «€ 2.934,59» da solo non dice niente; «€ 2.934,59 · da
mettere via · 25% di € 11.738» si legge senza aprire nulla.

## List report

*A cosa serve*: trovare e confrontare oggetti dello stesso tipo.

*Com'è fatta*: filtri in alto (nell'header collassabile), poi l'elenco.
In Fiori i KPI di riepilogo stanno **sopra** i filtri e descrivono
l'insieme filtrato — e devono dichiararlo, altrimenti chi legge crede
che parlino di tutto.

*Qui*: `/conti/webank/personale`, `/conti/webank/piva`,
`/fatture/storico`, `/fatture/clienti`.

*La trappola documentata*: su `/fatture/storico` i tre KPI seguono il
filtro di stato ma si chiamano «Fatturato {anno}». Filtrando «Incassata»
mostrano zero. È la voce aperta del 21/08/2026 nel log: o i KPI si
calcolano sull'anno intero, o le etichette dicono che seguono il filtro.
Delle due, mai nessuna.

*Il dettaglio che aiuta*: su `/conti/webank/personale` i KPI sono
cliccabili e aprono il «come viene calcolato» con le righe che li
compongono. È molto Fiori come idea — un numero deve poter essere
smontato — e va imitato quando un numero è una somma non ovvia.

## Object page

*A cosa serve*: tutto quello che riguarda **un** oggetto, in una pagina
sola.

*Com'è fatta*: header con l'identità dell'oggetto e il suo stato, poi il
contenuto in sezioni. Display ed edit sono due modi della stessa pagina,
non due pagine diverse.

*Qui*: `/fatture/<id>`, `/conti/webank/piva/<id>`,
`/conti/webank/personale/<id>`, `/fatture/clienti/<id>`.

*Le due cose che rendono buona una object page*:

- **lo stato si vede subito**, nell'header, come chip — non sepolto in
  una riga a metà pagina;
- **quello che non si può fare dice perché**. `fatture/costanti.py::
  motivo_blocco()` è il modello: non «non puoi modificare» ma «è già
  incassata: cambiarne gli importi la farebbe divergere dal denaro
  entrato — riportala a *Inviata a Nadia* e torna modificabile».

## Analytical page

*A cosa serve*: capire un andamento e decidere, non consultare righe.

*Com'è fatta*: i numeri che decidono in cima, la scomposizione che li
genera sotto, e — la parte che fa la differenza — la possibilità di
vedere **da dove esce** ogni numero.

*Qui*: `/risparmi`, `/fatture/situazione`.

*Il modello da seguire*: la cascata della pagina Risparmi. Saldo di
partenza, entrate, ogni uscita categoria per categoria rientrata sotto
il suo totale, base del calcolo, quota, saldo finale — e la somma torna
a vista. Quando le categorie note non coprono il totale, una riga
residua chiude sempre la differenza.

## Scegliere il floorplan

La domanda non è «come la disegno» ma **di che tipo è**:

| Se la pagina serve a… | è una… |
|---|---|
| vedere lo stato di più cose e saltare dove serve | overview |
| trovare o confrontare oggetti dello stesso tipo | list report |
| lavorare su **un** oggetto | object page |
| capire un andamento e decidere | analytical |

Se non riesci a sceglierne uno, quasi sempre la pagina sta rispondendo a
due domande diverse — ed è il segnale che sono due pagine. È il principio
*simple* (1-1-3), e in questa app è già successo: «Spese» rispondeva a
quattro domande insieme, e scioglierla ha risolto più problemi di
qualunque intervento grafico.

## Stati vuoti

Fiori li tratta come parte del design, non come un caso limite. Ogni
pagina di questa app ha il suo, e `tools/verifica_rotte.py` li verifica
su sette scenari di tabelle vuote.

Uno stato vuoto buono dice tre cose: **cosa manca**, **perché** e **come
rimediare**, con il link per farlo. `/risparmi` senza periodi:
«I periodi nascono dalle entrate di categoria "Stipendio" o "Giroconto
P.IVA": registrane una e questa pagina si popola.»
