# Miglioramenti individuati — log funzionale

Non una lista di gusti: ogni voce nasce da un ragionamento su come i dati
si muovono nel sistema — cosa un campo dovrebbe garantire, dove quella
garanzia si rompe, e sotto quali condizioni concrete succede un danno
(saldo sbagliato, riga invisibile, doppio conteggio). Se il ragionamento
non porta a un caso concreto che si rompe, non è una voce da mettere qui.

Aggiornato quando emerge qualcosa mentre si lavora su altro — non è un
esercizio a sé stante fine a sé stesso, è quello che resta di un'analisi
già fatta per un altro motivo, scritto perché non si perda.

Struttura di ogni voce: **Cosa** (il fatto), **Perché si rompe** (il
ragionamento, con un caso concreto), **Impatto** (chi se ne accorge e
come), **Stato**.

---

## Aperti

### [2026-08-12] `fatture/giroconto.py: calcola()` non mostra rivalsa/bollo nella ripartizione
**Cosa**: `calcola()` passa `f["totale"]` a `acc.scomponi()` ma non `cassa_importo`/`bollo_addebitato`, a differenza degli altri 4 punti (dettaglio fattura, home, situazione annuale) sistemati nella stessa sessione.
**Perché si rompe**: se una fattura CON rivalsa/bollo addebitato viene ripartita da qui, la ripartizione risulta comunque corretta nei conti (rivalsa e bollo sono già dentro `totale`), ma l'utente che guarda la schermata di ripartizione non vede la scomposizione "di cui rivalsa" che vede invece aprendo la stessa fattura dal dettaglio — incoerenza di presentazione, non di conto.
**Impatto**: basso finché le fatture non hanno rivalsa (le due attuali non ce l'hanno). Diventa visibile appena la prima fattura con rivalsa viene ripartita da questa schermata.
**Stato**: proposto, non fatto — il risultato di `calcola()` va solo a un endpoint JSON consumato da JS lato client, quindi va anche capito se e come quel JS renderizza `scomposizione` prima di aggiungere i due parametri.

### [2026-08-12] Base cassa/competenza mista nell'aggregato annuale
**Cosa**: in `fatture/fiscale.py: _situazione_data()`, `tot["incasso"]` si aggrega per `data_incasso` (cassa), mentre `tot["bollo"]`, `tot["rivalsa"]`, `tot["commercialista"]` si aggregano per `data` di emissione (competenza). `netto_competenza` li somma insieme.
**Perché si rompe**: una fattura emessa a dicembre anno N e incassata a gennaio anno N+1 conta il suo bollo/rivalsa nell'anno N (competenza) ma il suo incasso nell'anno N+1 (cassa) — i due anni "quasi tornano" solo se emissione e incasso cadono sempre nello stesso anno solare. È già documentato e voluto per il forfettario stesso (README §4, "due basi di calcolo diverse, ed è voluto"), ma non è ancora chiaro se sia voluto **anche** per bollo/rivalsa specificamente, o solo per imposta/INPS.
**Impatto**: piccoli scostamenti (pochi euro, l'ordine di grandezza di bollo/rivalsa su una manciata di fatture a cavallo d'anno) nel "Netto di competenza" mostrato in home/situazione a fine/inizio anno.
**Stato**: da capire con l'utente se è un problema reale o un dettaglio trascurabile — non toccato.

### [2026-08-12] `spese_tipo_check` e `b2f_spese_piva_tipo_check` permettono ancora `'giroconto'`
**Cosa**: dopo la migrazione 8.9, il codice non scrive più `tipo='giroconto'` sul conto personale (rimosso da `TIPI` in `spese/dati.py`), ma il vincolo CHECK a livello di database lo permette ancora.
**Perché si rompe**: nessun percorso applicativo può più scriverlo, quindi non è un bug attivo — ma un accesso diretto al database (script esterno, SQL editor) potrebbe rimettere una riga con quel valore, che tornerebbe invisibile a `v_periodi_stipendio`/`v_risparmi_mese` esattamente come le 4 righe storiche appena corrette.
**Impatto**: basso, richiede un bypass dell'app per succedere.
**Stato**: valutare se stringere il vincolo (`ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT ... CHECK (tipo IN ('entrata','uscita'))`) o lasciarlo com'è per non differenziare inutilmente `spese` da `b2f_spese_piva` (che invece usa legittimamente `'giroconto'` come metà P.IVA della ripartizione).

### [2026-08-12] Il conto personale non ha un saldo reale come ancora
**Cosa**: la somma storica di tutte le entrate/uscite in `spese` (tutti gli anni) non corrisponde al saldo reale del conto bancario personale — verificato confrontando con il saldo reale dato dall'utente (scostamento di ~11.000 €, non spiegabile da un singolo evento).
**Perché si rompe**: l'app non ha mai preteso di essere un ledger bancario completo (mesi di spesa in contanti o con altri mezzi non tracciati, normale per un conto personale), quindi la somma storica non è mai stata un saldo affidabile — ma non essendoci nessun'ancora ("il saldo reale era X in data Y"), ogni volta che serve un confronto con la banca va rifatto a mano, com'è successo in questa sessione.
**Impatto**: nessun danno ai calcoli esistenti (che lavorano per periodo, non su un saldo assoluto), ma niente nell'app oggi permette di rispondere da solo a "il saldo dell'app torna con la banca?" senza un'indagine manuale come quella fatta oggi.
**Stato**: proposta non implementata — richiede una decisione dell'utente (un campo "saldo reale" con data, da cui l'app calcola in avanti) prima di costruirla; non è stata costruita perché fuori dallo scope esplicito della richiesta che l'ha fatta emergere.

### Foglio Excel esterno `gestione_spese/excel` — fuori dal repo, solo annotato
**Cosa**: il foglio "Spese API" in quell'Excel (fuori da questo repo, generato da uno strumento esterno) si ferma a 1000 righe con 21 mancanti sparse, segno di un fetch senza `order by` stabile.
**Perché si rompe**: non è un bug di questa codebase — nessun endpoint o vista di questo repo alimenta direttamente quel foglio nel modo che ho potuto verificare.
**Impatto**: chi guarda quell'Excel vede meno righe di quelle reali, ma l'Hub (dopo il fix di paginazione di questa sessione) non ha lo stesso problema.
**Stato**: chiuso per questo repo — richiede intervento sullo strumento esterno che genera quell'Excel, non su questo codice.

---

## Fatti (storico — per non riproporli)

- 2026-08-12: KPI di `/spese/movimenti` troncati a 300 righe → totali sbagliati su periodi ampi. Fix: `totali_periodo()`/`righe_periodo()` senza tetto.
- 2026-08-12: "Dalla P.IVA" sempre a zero (cercava `tipo='giroconto'`, mai scritto dai flussi automatici). Fix: sotto-totale per categoria, non per tipo.
- 2026-08-12: `tipo='giroconto'` ridondante con `categoria='Giroconto P.IVA'`, 4 righe storiche invisibili a `v_risparmi_mese`. Fix: `tipo` solo entrata/uscita, migrazione 8.9.
- 2026-08-12: "Dove vanno le uscite" tautologico (100%, una riga) quando già filtrato per categoria. Fix: scende a sottocategoria.
- 2026-08-12: rivalsa/bollo verificati contro la normativa (Risposta AdE 428/2022) — il calcolo era già corretto, aggiunta solo la trasparenza mancante.

## Scartati (e perché)

- *Escludere rivalsa/bollo dal calcolo dell'imponibile*: richiesta iniziale dell'utente, scartata dopo verifica — la normativa dice il contrario (concorrono al reddito). Vedi README §4.
