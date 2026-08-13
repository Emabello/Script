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

### [2026-08-12] `docs/schema_supabase.md` non riflette le migrazioni 8.7-8.9, e ora nemmeno `b2f_revolut`
**Cosa**: lo snapshot mostra ancora `v_periodi_stipendio` con `WHERE ... categoria = 'Stipendio'` (senza "Giroconto P.IVA") e nessuna colonna "Risparmio effettivo (€)" in `v_risparmi_mese` — la definizione PRE-8.7. `git log` conferma: l'ultimo aggiornamento dello snapshot è il commit `662a0d0` (12/08), mentre le migrazioni 8.7-8.9 e la nuova tabella `b2f_revolut` (introdotta da una sessione parallela) sono tutte successive e nessuna tocca `docs/schema_supabase.md`.
**Perché si rompe**: è esattamente il gap che la convenzione dello snapshot (CLAUDE.md) doveva evitare — ora aggravato: due sessioni diverse hanno modificato lo schema reale senza che nessuna delle due rigenerasse la foto.
**Impatto**: dalla sola repo non è più verificabile con certezza lo stato reale del database. Serve un nuovo export (query di ispezione, README §8.5) per chiudere il dubbio.
**Stato**: non corretto — richiede un nuovo export dall'utente, non generabile dalla sola repo.

### [2026-08-13] `v_periodi_stipendio` non deterministica con due bonifici nello stesso giorno — ora più rilevante
**Cosa**: il confine di periodo usa `lead(data_bonifico) over (order by data_bonifico)`. Con due righe che condividono la stessa `data_bonifico`, l'ordinamento fra pari-merito non è garantito da SQL: per una delle due, `lead()` può tornare la data della riga gemella, dando `fine_periodo = data_bonifico − 1 giorno` — precedente all'inizio del periodo stesso.
**Perché si rompe**: `v_risparmi_mese` unisce le spese al periodo con `data BETWEEN data_bonifico AND fine_periodo`; con l'intervallo invertito quella condizione non è mai vera — il periodo appare nello storico con l'importo del bonifico ma zero spese/entrate, spezzando un unico periodo di paga in due righe.
**Impatto**: non riproducibile sui dati attuali (un solo giroconto finora), ma concreto non appena due incassi vengono ripartiti lo stesso giorno. **Ora più rilevante**: `spese/dati.py: saldo_conto()` (nuovo, sessione parallela) calcola il saldo reale del conto personale sottraendo `risparmio_totale()`, che dipende da `risparmi_periodo`/`v_risparmi_mese` — un periodo duplicato o spezzato da questo bug si propagherebbe silenziosamente al saldo mostrato in home.
**Stato**: ragionamento sulla query, non riproducibile con l'harness attuale (client Supabase finto, non un vero motore SQL con window function) — da tenere presente, priorità salita da bassa a media.

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
- 2026-08-13: uscire da "incassata" senza controllare `spesa_piva_id` (solo `data_giroconto`) → incasso "fantasma" sul libro P.IVA. Fix: `api_fattura_stato()` blocca anche su `spesa_piva_id`.
- 2026-08-13: guardia P.IVA copriva solo la metà "uscita" del giroconto, non l'entrata dopo che un giroconto era già stato eseguito sopra. Fix: `_origine_ripartizione()` protegge anche `spesa_piva_id` quando `giroconto_piva_id` è già valorizzato.
- 2026-08-13: parametri di accantonamento senza validazione, un errore di battitura produceva "restano tuoi" negativo. Fix: `PARAMETRI_LIMITI` + `_valida_parametri()` su `PATCH /fatture/api/parametri`.
- 2026-08-13: gauge limite 85.000€ su fatturato emesso invece di incassato. Fix: `situazione_dashboard()` usa `t["incasso"]`.
- 2026-08-13: `anno_fine_regime_agevolato` memorizzato ma mai letto. Fix: `_aliquota_imposta_per_anno()`, applicata sia a `_get_parametri()` (anno corrente) sia a `_situazione_data()` (anno specifico visualizzato).
- 2026-08-13: categoria "Giroconto P.IVA" selezionabile per qualunque movimento dal form manuale. Fix: esclusa dal menu (`spese/movimenti.py: _form()`) salvo se già quella del movimento aperto.
- 2026-08-13 (sessione parallela, non mia): `giroconto.calcola()` non mostrava rivalsa/bollo — risolto e esteso oltre il previsto: la rivalsa incassata diventa un pavimento esplicito che l'accantonamento non può scendere sotto (`alzato_alla_rivalsa`), propagato al dettaglio fattura e alla nota del movimento.
- 2026-08-13 (sessione parallela, non mia): il conto personale non aveva un saldo reale come ancora — risolto architetturalmente: `impostazioni.saldo_iniziale` (riga più vecchia per `valido_dal`) come ancora, `spese/dati.py: saldo_conto()` e `fatture/fiscale.py: saldo_piva()` calcolano in avanti fino a una data, sottraendo anche `risparmio_totale()` (il denaro "sparito" nei salvadanai). Aggiunto anche un terzo conto, Revolut (`spese/revolut.py`, snapshot per data da estratto conto), con verifica di coerenza fra risparmio dichiarato e reale. Resta da verificare che il *valore* di `saldo_iniziale` in tabella sia quello giusto — la correzione riguarda il *calcolo*, non il dato di partenza.
- 2026-08-13: arrotondamento a 5 minuti perdeva un'ora con minuti 58/59 (`round(m/5)*5 % 60` azzerava il riporto sull'ora). Fix: `xs_server.py: _arrotonda_5(h, m)`, unica funzione condivisa usata sia in `api_add()` sia in `g_import()`, con riporto sull'ora (e wrap a 24) verificato con test diretto su tutti i minuti 56-59.
- 2026-08-13: `g_import()` (import da Google Calendar) non aveva protezione duplicati, a differenza di `g_export()`. Fix: stesso criterio `seen` di `g_export()` "a specchio" — voci XS già presenti nei giorni coinvolti lette con `get_day_entries()`, confrontate su (titolo, data, ora d'inizio) dopo l'arrotondamento a 5 minuti (perché è così che l'orario è scritto e riletto su XS); verificato con test isolato su 4 scenari (duplicato reale, orario diverso, giorno libero, doppio import nello stesso batch).
- 2026-08-13: totale ore giornaliero fragile su parsing testuale "Xh Ym" (`day_payload()` backend + `entryMin()` frontend), un formato imprevisto spariva in un `except: pass` come 0 minuti silenzioso. Fix: non forzabile il formato del portale esterno, quindi la voce che non si riesce a parsare viene marcata (`total_unreadable`) invece di sparire nel conteggio — badge "non letto" sulla voce, conteggio "N non lette" su pill del giorno/settimana e avviso nel riepilogo mese, così il totale mostrato segnala visibilmente di essere incompleto invece di apparire normale ma sottostimato.
- 2026-08-13: import da banca scartava righe silenziosamente (importo con virgola decimale, data fuori formato) senza contatore, nessuna protezione duplicati. Fix: `_numero_bancario()` prova anche la notazione con la virgola prima di arrendersi; `parse_bank_xlsx()` ora conta e motiva le righe scartate (mostrate in un avviso persistente, non un toast che sparisce) e segnala se la colonna "Data Contabile" non è stata trovata; `api_importa_salva()` confronta (data, importo, descrizione) con quanto già in `spese` prima di scrivere, sia contro il database sia all'interno dello stesso file caricato.
- 2026-08-13: nuova voce di menu "Saldi" (5ª, accanto a Home/Ore/Fatture/Spese): pagina dedicata che riusa la card saldi già esistente in home (P.IVA + personale + Revolut, con scomposizione), raggiungibile senza tornare in Home.

## Scartati (e perché)

- *Escludere rivalsa/bollo dal calcolo dell'imponibile*: richiesta iniziale dell'utente, scartata dopo verifica — la normativa dice il contrario (concorrono al reddito). Vedi README §4.
