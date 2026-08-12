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

### [2026-08-12] Uscire da "incassata" non controlla `spesa_piva_id`, solo `data_giroconto`
**Cosa**: `fatture/storico.py: api_fattura_stato()` blocca il cambio di stato fuori da "incassata" solo se `data_giroconto` è valorizzato — non controlla `spesa_piva_id` (la riga di incasso su P.IVA creata *prima* di un eventuale giroconto).
**Perché si rompe**: verificato con l'harness — fattura incassata con `spesa_piva_id` impostato ma nessun giroconto ancora fatto, riportata a "trasmessa_sdi": accettato senza avviso. `data_incasso` si ripulisce, ma la riga di entrata su `b2f_spese_piva` resta agganciata e continua a contare nelle entrate P.IVA, mentre `_situazione_data()` (che conta solo fatture con `stato='incassata'`) smette di vederla — i due lati (libro P.IVA e motore fiscale) divergono su un incasso reale.
**Impatto**: chi corregge un passaggio di stato sbagliato (caso esplicitamente previsto dal codice) lascia un incasso "fantasma" invisibile al calcolo delle tasse.
**Stato**: confermato leggendo il codice (`fatture/storico.py` intorno alla riga 950-965), non ancora corretto.

### [2026-08-12] La guardia sulle righe P.IVA collegate copre solo la metà "uscita" del giroconto
**Cosa**: `fatture/fiscale.py: _origine_ripartizione()` protegge solo la riga di uscita del giroconto (`giroconto_piva_id`); la riga di entrata/"fatturato" (`spesa_piva_id`) resta cancellabile liberamente per design — corretto finché non è stato ancora fatto un giroconto sopra, sbagliato dopo.
**Perché si rompe**: verificato con l'harness — fattura incassata, giroconto eseguito, poi la riga "fatturato" cancellata direttamente da Movimenti P.IVA (nessun avviso): la fattura continua a mostrare "ripartizione eseguita" (`data_giroconto`, `giroconto_piva_id`, `giroconto_personale_id` tutti intatti) ma `spesa_piva_id=None` — il bottone "Registra entrata su P.IVA" ricompare su una fattura già ripartita. La riga di uscita del giroconto resta nel libro P.IVA senza più un incasso a giustificarla.
**Impatto**: cancellare per errore la riga "fatturato" dopo un giroconto già fatto rompe silenziosamente la ripartizione; ri-registrare l'incasso crea una seconda riga scollegata dall'originale.
**Stato**: confermato leggendo il codice (`fatture/fiscale.py`, funzione `_origine_ripartizione` e il suo stesso commento), non ancora corretto.

### [2026-08-12] Parametri di accantonamento senza validazione: un errore di battitura produce "restano tuoi" negativo
**Cosa**: `PATCH /fatture/api/parametri` scrive qualunque numero senza controlli di range; `scomponi()` non fa clamp su `importi`/`netti`. Solo `giroconto.calcola()` clampa l'accantonamento reale a `[0, lordo]` — dashboard, dettaglio fattura ed editor mostrano invece il numero grezzo.
**Perché si rompe**: digitare "50" nel campo margine di sicurezza pensando "50%" invece di "0.50" produce, su un incasso di €5.000, un consigliato di oltre €50.000 e "Restano tuoi" negativo di decine di migliaia di euro — visibile ovunque nell'app prima ancora che qualcuno tocchi un euro reale.
**Impatto**: nessun danno ai conti reali (il giroconto resta protetto), ma numeri assurdi/allarmanti mostrati per un semplice errore di digitazione.
**Stato**: da agente, non ancora verificato a mano — priorità bassa rispetto ai primi due.

### [2026-08-12] Il gauge del limite forfettario (85.000€) usa il fatturato emesso, non l'incassato
**Cosa**: il gauge "Limite forfettario" in situazione fiscale aggrega per data di *emissione* (competenza), non di incasso (cassa) — mentre imposta/INPS e il principio dichiarato nel README (§4, "le tasse si pagano per cassa") usano la cassa.
**Perché si rompe**: due fatture emesse ma non ancora incassate a fine anno spostano il gauge di ~9 punti percentuali rispetto al criterio corretto (di cassa) — proprio nella situazione (fine anno, fatture pendenti) dove un professionista vicino alla soglia ha più bisogno che il numero sia giusto.
**Impatto**: l'unico avviso dell'app pensato per "stai per uscire dal regime" può essere disallineato dal criterio legale a cavallo di fine/inizio anno.
**Stato**: da agente, non ancora verificato a mano — da controllare prima di decidere se e come correggere (tocca la logica fiscale, va confermato bene).

### [2026-08-12] `anno_fine_regime_agevolato` è memorizzato ma non cambia mai l'aliquota
**Cosa**: il parametro esiste ed è editabile ("Primo anno con aliquota al 15%", default 2031) ma nessun calcolo lo legge — `aliquota_imposta` resta quella impostata a mano per sempre, anche dopo il quinquennio agevolato.
**Perché si rompe**: nel 2031 (primo anno fuori dall'agevolazione), se nessuno ricorda di editare manualmente l'aliquota al 15%, l'app continuerebbe a calcolare col 5% — accantonamento sottostimato di 10 punti percentuali per un anno intero, scoperto solo alla scadenza di giugno 2032.
**Impatto**: nessuno oggi (2026); prevedibile e concreto fra qualche anno se non si aggiunge un promemoria o un calcolo automatico.
**Stato**: da agente, non ancora verificato a mano — priorità bassa, non urgente.

### [2026-08-12] Categoria "Giroconto P.IVA" selezionabile per qualunque movimento, senza esserlo davvero
**Cosa**: il form "Nuovo movimento" costruisce il menu categorie da `spese/dati.py: albero_categorie()`, che include "Giroconto P.IVA" come una scelta libera fra le altre. `D.collegato()` blocca modifica/cancellazione solo se un'ALTRA tabella punta già a quella riga — non impedisce di *creare* (o modificare, finché non collegata) una riga qualunque con quella categoria.
**Perché si rompe**: `v_periodi_stipendio` apre un nuovo periodo su ogni entrata con categoria in `('Stipendio', 'Giroconto P.IVA')`, e `D.totali()` conta in "Dalla P.IVA" ogni entrata con quella categoria, a prescindere da un vero collegamento. Un rimborso o un regalo categorizzato per errore "Giroconto P.IVA" (il datalist "Metodo di pagamento" suggerisce persino "Giroconto" proprio lì accanto) apre silenziosamente un periodo di risparmio nel punto sbagliato e gonfia il KPI "Dalla P.IVA" — e siccome `collegato()` non trova nessun aggancio reale, il movimento resta modificabile/cancellabile normalmente: niente segnala l'anomalia.
**Impatto**: cronologia dei periodi di risparmio spezzata, KPI "Dalla P.IVA" falsato — nessun controllo lo impedisce o lo segnala. Estende il lavoro già fatto in sessione sulla ridondanza tipo=giroconto: lì ho tolto la via "tipo", qui resta aperta la via "categoria" senza verifica.
**Stato**: confermato dall'agente, non ancora verificato a mano — priorità alta, stesso tipo di bug già corretto oggi.

### [2026-08-12] `docs/schema_supabase.md` non riflette la migrazione 8.7 — verificato di persona
**Cosa**: lo snapshot mostra ancora `v_periodi_stipendio` con `WHERE ... categoria = 'Stipendio'` (senza "Giroconto P.IVA") e nessuna colonna "Risparmio effettivo (€)" in `v_risparmi_mese` — la definizione PRE-8.7. `git log` conferma: l'ultimo aggiornamento dello snapshot è il commit `662a0d0` (12:35 del 12/08), mentre la migrazione 8.7 e la sua "conferma" nel README sono nel commit `e71be3f` (14:47) — successivo, e non tocca `docs/schema_supabase.md`.
**Perché si rompe**: è esattamente il gap che la convenzione dello snapshot (CLAUDE.md, stabilita oggi stesso) doveva evitare. L'utente ha confermato a voce di aver lanciato 8.7 ("ok 8.7 lanciato e fatto senza problemi"), quindi il caso più probabile è che la migrazione sia stata applicata per davvero e sia solo la mia documentazione a essere rimasta indietro — ma dalla sola repo questo non è verificabile con certezza.
**Impatto**: se per assurdo 8.7 non fosse mai stata applicata, tutto il ragionamento fatto oggi su "il giroconto apre un periodo" sarebbe silenziosamente falso in produzione. Va richiesta all'utente una nuova query di ispezione (README §8.5) per chiudere il dubbio.
**Stato**: mio errore di processo, non ancora corretto — devo chiedere all'utente un nuovo export per rigenerare lo snapshot.

### [2026-08-12] `v_periodi_stipendio` non deterministica con due bonifici nello stesso giorno
**Cosa**: il confine di periodo usa `lead(data_bonifico) over (order by data_bonifico)`. Con due righe che condividono la stessa `data_bonifico`, l'ordinamento fra pari-merito non è garantito da SQL: per una delle due, `lead()` può tornare la data della riga gemella, dando `fine_periodo = data_bonifico − 1 giorno` — precedente all'inizio del periodo stesso.
**Perché si rompe**: `v_risparmi_mese` unisce le spese al periodo con `data BETWEEN data_bonifico AND fine_periodo`; con l'intervallo invertito quella condizione non è mai vera — il periodo appare nello storico con l'importo del bonifico ma zero spese/entrate, spezzando un unico periodo di paga in due righe.
**Impatto**: non riproducibile sui dati attuali (un solo giroconto finora), ma concreto non appena due incassi vengono ripartiti lo stesso giorno, o si verifica la voce precedente su questa lista (categoria "Giroconto P.IVA" mal assegnata lo stesso giorno di un giroconto vero).
**Stato**: ragionamento sulla query, non riproducibile con l'harness attuale (client Supabase finto, non un vero motore SQL con window function) — da tenere presente, non urgente finché non capita un doppio incasso nello stesso giorno.

### [2026-08-12] Import da banca scarta righe silenziosamente su formati inattesi, nessuna protezione duplicati
**Cosa**: `spese/importa.py: parse_bank_xlsx()` — un importo in formato testo con virgola decimale (`"1.234,56"`) o una data fuori formato `%d/%m/%Y` fa fallire il parsing; la riga finisce in un `except (TypeError, ValueError): continue` silenzioso, senza contatore "N righe scartate". La colonna data, a differenza di importo/descrizione, non ha nessuna validazione sull'intestazione: se non trova "data contabile" ripiega silenziosamente sulla colonna 0. Né qui né in `api_importa_salva()` c'è controllo duplicati fra righe o fra importazioni successive.
**Perché si rompe**: l'utente vede solo "N movimenti caricati", nessun modo di sapere se righe sono state scartate o se ricaricare un estratto conto che si sovrappone al precedente (comune, le banche includono qualche giorno di margine) ha duplicato movimenti.
**Impatto**: saldo e KPI di `/spese/movimenti` alterati silenziosamente, per difetto o per eccesso.
**Stato**: confermato dall'agente con test diretto (`float("1.234,56")` → `ValueError`), non ancora corretto.

### [2026-08-12] Arrotondamento a 5 minuti perde un'ora quando i minuti sono 58 o 59 — verificato di persona
**Cosa**: `xs_server.py` (in `api_add()` e `g_import()`, stessa riga duplicata in entrambi): `sm = round(sm / 5) * 5 % 60`. Con `sm=58`: `round(58/5)=12`, `12*5=60`, `60%60=0` — l'ora non viene mai incrementata per il riporto.
**Perché si rompe**: verificato in Python — minuti 58 e 59 arrotondano a 0 su entrambi gli estremi di ogni voce, senza toccare l'ora. Il form manuale ha uno step che scoraggia (non impedisce sempre) input fuori griglia, ma `g_import()` (import da Google Calendar) prende orari reali mai vincolati a multipli di 5: un evento "14:58–16:32" diventa "14:00–16:30" — quasi un'ora in più, silenziosamente, con risposta "ok" dall'endpoint.
**Impatto**: ~3,3% dei valori minuto possibili (58, 59) su ogni estremo di ogni voce, esposto soprattutto dall'import calendario dove non c'è alcun vincolo di griglia sull'input originale.
**Stato**: confermato con verifica diretta in Python, non ancora corretto.

### [2026-08-12] Totale ore giornaliero fragile su parsing testuale "Xh Ym", scarta silenziosamente formati diversi
**Cosa**: `xs_server.py: day_payload()` (backend) e `entryMin()` (frontend JS) — stessa logica duplicata due volte — assumono che il campo `total` (estratto per scraping dall'HTML del portale esterno XS) sia sempre nel formato "Xh Ym". Qualunque stringa diversa (vuota, "-", "45m", timbratura ancora aperta) fa fallire il parsing, catturato da un `except Exception: pass` che riporta silenziosamente 0 minuti — la voce resta visibile in lista ma non contribuisce a nessun totale.
**Perché si rompe**: `total` non è un dato strutturato garantito, è testo scrapato da un portale esterno che questa app non controlla.
**Impatto**: totali di giorno/settimana/mese e ripartizione per cliente sottostimati nello stesso modo su entrambi i lati (backend e frontend coerenti nell'errore, quindi nessun numero discordante fa da campanello d'allarme).
**Stato**: confermato dall'agente con test diretto, non ancora corretto.

### [2026-08-12] Import da Google Calendar non ha protezione duplicati, a differenza dell'export
**Cosa**: `g_export()` costruisce un set `seen` di eventi già esportati per non ricrearli. `g_import()` (direzione opposta) non ha l'equivalente: scrive ogni evento ricevuto senza controllare se una voce equivalente esiste già per quel giorno.
**Perché si rompe**: ripetere l'import per lo stesso intervallo (aggiungere eventi al calendario e rilanciare l'import, o cliccare "Importa" due volte) duplica tutte le voci già importate.
**Impatto**: ore duplicate silenziosamente sommate ai totali, rilevabili solo controllando a mano le singole voci.
**Stato**: confermato dall'agente, non ancora corretto.

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

### ~~Foglio Excel esterno~~ → causa trovata e corretta (2026-08-12)
**Cosa**: `C:\Users\ebell\Desktop\LAV-PER\Personale\gestione_spese\excel\Budget.xlsm`, foglio "Spese API": si fermava a 1000 righe con 21 mancanti sparse. Decodificata la query Power Query incorporata (`customXml/item1.xml`, formato DataMashup): chiama `Web.Contents(".../rest/v1/v_spese", [Headers=...])` senza `order=`, senza `limit=`, senza paginazione.
**Perché si rompe**: senza un `order by` esplicito, PostgREST non garantisce quali 1000 righe tornano quando la vista ne ha di più — stesso principio del bug già risolto in `spese/dati.py` questa sessione (`_tutte_le_righe_filtrate`/`righe_periodo`), ma qui è nella query M dell'Excel, non nel codice di questo repo.
**Impatto**: il foglio "Spese API" mostra un sotto-insieme instabile delle righe reali. Il foglio "Situazione mensile" (i calcoli veri) legge invece da `v_risparmi_mese`, che ha ~19 righe — mai a rischio dello stesso bug; verificato che i suoi numeri (es. "Totale Speso" del periodo corrente, € 602,67) tornano identici al calcolo fatto sui dati grezzi.
**Stato**: **corretto** — nuova query M con `order=id.asc` e paginazione reale (`List.Generate` a blocchi da 1000 finché una pagina non torna incompleta), data all'utente pronta da incollare nell'Editor avanzato di Power Query. Non modificato il file .xlsm direttamente (formato binario a più parti, rischio di corromperlo con un file mal fatto a mano).

---

## Fatti (storico — per non riproporli)

- 2026-08-12: KPI di `/spese/movimenti` troncati a 300 righe → totali sbagliati su periodi ampi. Fix: `totali_periodo()`/`righe_periodo()` senza tetto.
- 2026-08-12: "Dalla P.IVA" sempre a zero (cercava `tipo='giroconto'`, mai scritto dai flussi automatici). Fix: sotto-totale per categoria, non per tipo.
- 2026-08-12: `tipo='giroconto'` ridondante con `categoria='Giroconto P.IVA'`, 4 righe storiche invisibili a `v_risparmi_mese`. Fix: `tipo` solo entrata/uscita, migrazione 8.9.
- 2026-08-12: "Dove vanno le uscite" tautologico (100%, una riga) quando già filtrato per categoria. Fix: scende a sottocategoria.
- 2026-08-12: rivalsa/bollo verificati contro la normativa (Risposta AdE 428/2022) — il calcolo era già corretto, aggiunta solo la trasparenza mancante.

## Scartati (e perché)

- *Escludere rivalsa/bollo dal calcolo dell'imponibile*: richiesta iniziale dell'utente, scartata dopo verifica — la normativa dice il contrario (concorrono al reddito). Vedi README §4.
