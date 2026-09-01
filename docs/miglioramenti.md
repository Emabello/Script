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

### [2026-08-25] La foto delle ore non sa se il mese era finito quando è stata scattata
**Cosa**: `b2f_fatture.ore_snapshot` (§8.13) è il riepilogo del portale al momento della lettura, con `ore_lette_il` a dire quando. Niente dice se a quel momento il **mese era chiuso**: una foto scattata il 20 del mese e una scattata il 5 del mese dopo hanno la stessa forma e si leggono allo stesso modo.
**Perché si rompe**: caso concreto. Fatturi il 28 luglio, precompili dalle ore di luglio, la foto dice 18,50 giornate e la riga della fattura nasce da lì. Il 29 e il 30 timbri altre due giornate. La fattura resta a 18,50 — giusto, è quello che hai fatturato — ma la card "Ore fatturate" continuerà a mostrare 18,50 come se fosse *il mese*, mentre luglio è stato di 20,50. Chi la guarda a settembre non ha modo di accorgersene, e il bottone "Aggiorna dal portale" la porterebbe a 20,50 scollegandola dalla riga fatturata, che nessuno aggiorna.
**Impatto**: nessun numero sbagliato nei conti — la fattura è quella che è, e il saldo non dipende dalle ore. Sbagliata è la **domanda a cui la card sembra rispondere**: sembra dire "questo è il mese", dice "questo era il mese quel giorno". Con lo sfasamento fra i due, il confronto giornate-fatturate / giornate-lavorate (l'unico motivo per cui uno apre quella card) non è affidabile.
**Stato**: aperto. Il minimo è che la card lo dica quando `ore_lette_il` cade dentro il mese fotografato ("mese non ancora chiuso"). Meglio ancora: tenere le giornate fatturate (quelle della riga) accanto a quelle lavorate (quelle della foto) e mostrare la differenza, che è esattamente il numero che uno cerca — quanto ho lavorato senza fatturarlo.

### [2026-08-25] La §8.11 ricategorizza per `(data, importo, tipo)`: due righe su sette non hanno agganciato niente
**Cosa**: il blocco 1 di README §8.11 sposta in categoria "Risparmi" sette movimenti già registrati, identificandoli con `(data, importo, tipo) in (...)`. Lanciato sul database il 25/08/2026, cinque hanno agganciato, due no: `2025-05-02 / 225,00 / uscita` e `2025-05-05 / 67,00 / uscita`. In `spese` quegli importi esistono, ma con un'altra data — 225,00 il **01/05/2025** (descrizione "Massimo Giacalone Saldo Zanzibar", categoria Personale/Bonifici) e 67,00 il **04/05/2025** (Fisso/Hype). La verifica finale dà 21 righe in categoria Risparmi invece delle 23 attese, per 292,00 € di differenza.
**Perché si rompe**: `(data, importo, tipo)` non è un'identità. Non è unica — due movimenti dello stesso importo lo stesso giorno sono indistinguibili, e l'`update` li prenderebbe entrambi — e non è stabile: basta che la data registrata sia la contabile invece della valuta (è la voce del 14/08 su `spese.data`) perché la riga cercata semplicemente non esista. Un `update` che non trova nulla **non fallisce**: la migrazione va a buon fine, e i controlli sul saldo passano lo stesso, perché ricategorizzare non muove il saldo. La differenza resta invisibile finché qualcuno non conta le righe.
**Impatto**: sul saldo del conto zero. Su `v_risparmi_mese` sì: se quei due movimenti sono davvero versamenti verso i salvadanai, nel periodo di paga di maggio 2025 il "Risparmio effettivo" è più basso di 292,00 € e il "Totale Speso" più alto della stessa cifra — quindi anche il risparmio consigliato, che si calcola su quella base, è sbagliato per quel periodo.
**Stato**: aperto, e prima della correzione va deciso *se* quelle due righe sono risparmio: la prima ha una descrizione che sembra un rimborso a una persona ("Saldo Zanzibar"), la seconda è un giroconto verso Hype — e la cronaca della riconciliazione, per il periodo del 01/07/2026, tratta un bonifico HYPE come uscita normale e non come risparmio. Se lo sono, basta una `update` sulle date vere; se non lo sono, va corretta la lista in README §8.11, che oggi promette 23 righe e ne consegna 21.

### [2026-08-21] I tre KPI di `/fatture/storico` seguono il filtro di stato, ma si chiamano come se fossero dell'anno
**Cosa**: in `fatture/storico.py: storico_list()` la query applica il filtro di stato scelto nella toolbar (`q.eq("stato", stato)`), e le tre tessere di riepilogo — "Fatturato {anno}", "Incassato", "Da incassare" — si calcolano su quelle stesse `rows`, non su tutte le fatture dell'anno.
**Perché si rompe**: filtrando "Incassata" restano solo le incassate, quindi `tot_fatturato == tot_incassato` e **"Da incassare" mostra € 0,00 anche se ci sono fatture trasmesse e non pagate**; filtrando "Bozza" le tessere mostrano tutte zero (nessuna bozza è in `STATI_EMESSE`), come se nell'anno non fosse stato fatturato nulla. L'etichetta però continua a dire "Fatturato {anno}", cioè promette un totale d'anno mentre mostra il totale del sottoinsieme filtrato.
**Impatto**: chi apre lo storico già filtrato (o filtra per cercare una fattura e poi guarda in alto) legge un credito residuo sbagliato — proprio il numero per cui si va a controllare lo storico. Nessun errore visibile: i numeri sono coerenti fra loro, solo calcolati su una base diversa da quella annunciata.
**Stato**: non corretto. Due strade: calcolare le tessere su una seconda query senza filtro di stato (restano "dell'anno" come dicono), oppure lasciarle sul filtro e cambiare le etichette perché lo dicano. La prima è più vicina a cosa serve guardando quella pagina.

### [2026-08-14] `spese.data` mescola data contabile e data valuta, e nessuno sa quale sia quale
**Cosa**: 537 righe su 927 nel periodo coperto dagli estratti hanno in banca una riga di importo identico ma con data diversa (fino a qualche giorno). Le due date esistono entrambe sull'estratto — contabile e valuta — e l'import (`spese/importa.py`) prende la contabile, mentre le righe inserite a mano prendono il giorno in cui la spesa è stata fatta. Nella colonna `data` finiscono mescolate, senza niente che dica quale delle due sia.
**Perché si rompe**: due danni concreti. (1) **I periodi di paga**: `v_risparmi_mese` unisce le spese al periodo con `data BETWEEN data_bonifico AND fine_periodo`. Una spesa del 31/03 registrata col 02/04 salta nel periodo successivo — il "Totale Speso" di due periodi consecutivi è sbagliato in direzioni opposte, e il risparmio consigliato con lui. Stessa cosa per `mese`/`anno`, che sono ricavati da `data`: un movimento di fine mese cade nel mese sbagliato dei KPI. (2) **La riconciliazione**: accoppiando su data esatta, questi 537 movimenti appaiono contemporaneamente come "mancanti in `spese`" e "in più rispetto alla banca", gonfiando di dieci volte il disallineamento apparente (555 buchi contro ~18 veri) e nascondendo i pochi problemi veri nel rumore. È esattamente quello che è successo alla prima passata di questo audit.
**Impatto**: sul saldo totale zero (entrano ed escono dallo stesso conto), sui numeri per periodo e per mese sì, e su ogni futuro controllo di coerenza.
**Stato**: aperto. Il minimo è decidere quale data è *la* data (la contabile è quella che la banca usa per il saldo, quindi è lei) e allineare l'import a quella scelta; meglio ancora, tenere anche `data_valuta` in una colonna sua, così il confronto con l'estratto può usare l'una o l'altra invece di indovinare. Fino ad allora, chi riconcilia deve accoppiare con tolleranza sulla data.

### [2026-08-14] L'app sa quanto *vale* l'investimento Revolut, non quanto ci è stato *versato*
**Cosa**: `b2f_revolut.investimenti` è la valorizzazione del portafoglio, scritta a mano (l'estratto consolidato non la contiene). Non esiste in nessuna tabella il capitale versato verso l'investimento. Dal PDF "Trading account statement" 27/05/2025-14/08/2026 quel numero si ricostruisce: **€ 1.871,85 netti in EUR** (35 versamenti per € 2.291,96, meno € 420,11 di prelievi) **e $ 1.420,34 in USD** (27 versamenti, nessun prelievo) — ma è un documento che sta fuori dall'app, e nessuno lo legge.
**Perché si rompe**: `coerenza()` confronta il risparmio dichiarato contro `risparmi + investimenti`, cioè contro un valore di mercato. Un mercato che sale genera uno scarto identico a quello di un versamento non dichiarato, e viceversa: il messaggio non può distinguere "hai risparmiato meno di quanto pensavi" da "il portafoglio è cresciuto". Oggi il testo dice che potrebbe essere l'uno o l'altro — è onesto, ma è anche l'ammissione che il dato per deciderlo non c'è.
**Impatto**: l'unico controllo automatico fra risparmio dichiarato e denaro reale non è mai conclusivo. Con il costo storico registrato lo diventerebbe: scarto sul costo = periodo dimenticato, scarto sul valore = mercato.
**Stato**: aperto. La strada minima è una colonna `investimenti_versato` sullo snapshot, alimentata dall'estratto trading (che il parser oggi non legge: legge solo il consolidato).

### [2026-08-14] `_alias_map()` (import da Google Calendar): due commesse omonime, e vince l'ultima letta
**Cosa**: `xs_server.py::_alias_map()` costruisce un dizionario titolo→(cliente, progetto, task) con chiavi anche molto corte — per i progetti con un solo task registra `p["name"]` da solo e il `code` (la parte prima di " - "). Le chiavi si sovrascrivono in silenzio: `m[chiave] = trip`, l'ultimo che passa vince.
**Perché si rompe**: due clienti diversi con un progetto che si chiama allo stesso modo (o con lo stesso codice iniziale) producono la stessa chiave. Un evento di Google Calendar intitolato con quel nome viene importato sulla commessa di *uno* dei due, scelto dall'ordine in cui il portale elenca i clienti. Da questa sessione l'ordine è alfabetico su tutti e tre i livelli (era il criterio che serviva ai menù): il comportamento non peggiora — era già non governato — ma **cambia**, quindi un import che finora finiva sulla commessa X può ora finire su Y.
**Impatto**: ore imputate al cliente sbagliato, senza nessun avviso. Sui dati attuali non è verificabile dalla repo (il catalogo vive sul portale XS).
**Stato**: aperto. Il rimedio non è l'ordinamento ma la collisione: quando due voci genererebbero la stessa chiave, non registrarla per nessuna delle due (un titolo ambiguo va lasciato da assegnare a mano, invece di essere assegnato a caso).

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

### [2026-08-13] `spese/movimenti.py: _form()` disabilita il campo categoria in base a `collegato`, non al valore della categoria
**Cosa**: l'esclusione di "Giroconto P.IVA" dal menu libero (righe 353-355) funziona; ma quando la categoria è già quella del movimento aperto, resta visibile nel `<select>` e l'intero form (incluso `f_categoria`) viene disabilitato solo se `D.collegato(client, mid)` trova un backlink (`giroconto_personale_id` sulla fattura o sulla riga `b2f_spese_piva`) — non se `categoria == CATEGORIA_GIROCONTO`.
**Perché si rompe**: nei percorsi che l'app usa oggi per scrivere questa categoria (giroconto automatico o manuale) il backlink viene sempre scritto nello stesso passaggio, quindi le due condizioni coincidono in pratica. Ma se il backlink manca per qualsiasi motivo — cancellazione diretta via SQL Editor della fattura/riga collegata bypassando l'endpoint DELETE guardato dall'app, o un futuro bug di rollback — un movimento con categoria "Giroconto P.IVA" ma senza backlink mostra il menu categoria **abilitato**, con "Aggiorna" funzionante: l'utente potrebbe cambiare categoria/tipo/importo liberamente, rompendo il confine di periodo che `v_periodi_stipendio` apre su quella categoria.
**Impatto**: basso, richiede lo stesso tipo di bypass diretto del database già accettato come rischio nella voce aperta su `spese_tipo_check`/`b2f_spese_piva_tipo_check` qui sopra — stessa classe di rischio, non nuova superficie.
**Stato**: non corretto, trovato dall'agente di audit "Verifica finale Spese/Ore/Saldi" e verificato di persona sul codice (righe 353-355, 363, 380 di `spese/movimenti.py`). Da valutare insieme alla voce sul vincolo `spese_tipo_check`: se si stringe quel CHECK, vale la pena condizionare `ro` anche a `cat_corrente == D.CATEGORIA_GIROCONTO`, non solo a `collegato`.

### ~~Foglio Excel esterno~~ → causa trovata e corretta (2026-08-12)
**Cosa**: `C:\Users\ebell\Desktop\LAV-PER\Personale\gestione_spese\excel\Budget.xlsm`, foglio "Spese API": si fermava a 1000 righe con 21 mancanti sparse. Decodificata la query Power Query incorporata (`customXml/item1.xml`, formato DataMashup): chiama `Web.Contents(".../rest/v1/v_spese", [Headers=...])` senza `order=`, senza `limit=`, senza paginazione.
**Perché si rompe**: senza un `order by` esplicito, PostgREST non garantisce quali 1000 righe tornano quando la vista ne ha di più — stesso principio del bug già risolto in `spese/dati.py` questa sessione (`_tutte_le_righe_filtrate`/`righe_periodo`), ma qui è nella query M dell'Excel, non nel codice di questo repo.
**Impatto**: il foglio "Spese API" mostra un sotto-insieme instabile delle righe reali. Il foglio "Situazione mensile" (i calcoli veri) legge invece da `v_risparmi_mese`, che ha ~19 righe — mai a rischio dello stesso bug; verificato che i suoi numeri (es. "Totale Speso" del periodo corrente, € 602,67) tornano identici al calcolo fatto sui dati grezzi.
**Stato**: **corretto** — nuova query M con `order=id.asc` e paginazione reale (`List.Generate` a blocchi da 1000 finché una pagina non torna incompleta), data all'utente pronta da incollare nell'Editor avanzato di Power Query. Non modificato il file .xlsm direttamente (formato binario a più parti, rischio di corromperlo con un file mal fatto a mano).

---

## Fatti (storico — per non riproporli)

### ~~La tenda d'attesa dipendeva da due nomi di endpoint scritti in un altro file~~ → chiusa il 28/08/2026
**Cosa è cambiato**: la schermata d'attesa (`shared/caricamento.py`) vive in cache e serve proprio quando il server non risponde, quindi non poteva reggersi su `xs_server.ALLOW_NO_PIN`, che è un insieme di *nomi di funzione*: bastava rinominare `attesa()` o `ping()` perché il gate ricominciasse a proteggerle, senza che niente lo segnalasse. Due danni concreti, tutti e due invisibili finché l'app resta sveglia: in cache sarebbe finita la shell del PIN al posto della tenda (e a servizio spento quel gate non si può nemmeno aprire — schermo vuoto, nessun risveglio), e il battito avrebbe visto `401` invece del risveglio, restando ad aspettare un'app già in piedi. Ora il service worker mette in cache `/attesa` **solo se dentro c'è davvero la tenda** (`id="tendaMetro"`, che esiste solo lì — il mosaico invece sta in ogni pagina), e il battito considera sveglia qualunque risposta che porti l'header `X-B2F` — `401` compreso, lasciando che sia il gate della pagina vera a chiedere il codice. Il segnale non dipende più da un nome scritto altrove.

### ~~Il campo "Risparmio effettivo" scriveva su una colonna che nessuno legge più~~ → chiuso il 25/08/2026
**Cosa era**: dopo la §8.11 `v_risparmi_mese` calcola il risparmio effettivo **dai movimenti** di categoria "Risparmi", e `saldo_conto()` non guarda più `risparmi_periodo`. Il campo "Risparmio effettivo" della pagina Risparmi, però, continuava a fare `PATCH /spese/api/risparmi` → `risparmi_periodo.effettivo_risparmio`: scriveva un numero in un posto che nessun calcolo legge più.
**Perché era grave**: non dava errore. Registravi 800 €, la pagina diceva "registrato", e al ricaricamento il valore mostrato tornava quello calcolato dai movimenti (zero, se il bonifico non era stato registrato come uscita) — senza che niente dicesse che le due cose non c'entravano più nulla l'una con l'altra. È la stessa forma del bug che è costato 829,78 €: due strade per dire la stessa cosa, e nessuna regola su quale valga.
**Cosa è cambiato**: il campo non c'è più. Al suo posto la **procedura di fine periodo**, che registra l'uscita vera dal conto (categoria Risparmi, data del bonifico) e mostra prima come si divide fra i cinque salvadanai. `PATCH /spese/api/risparmi` risponde 409 con il puntatore alla procedura, invece di sparire: una scheda rimasta aperta da prima del deploy deve sapere perché non ha funzionato.

### ~~`docs/schema_supabase.md` non riflette le migrazioni 8.7-8.9, né `b2f_revolut`~~ → chiusa il 25/08/2026
**Cosa è cambiato**: snapshot riverificato campo per campo contro il database vivo con il connettore MCP di Supabase (non più l'export testuale di §8.5): allineate `v_risparmi_mese` e `v_periodi_stipendio`, aggiunte `b2f_revolut` e `b2f_saldi_verifica` che mancavano, promossa a vincolo la nota su `b2f_fatture_spesa_piva_id_fkey` (§8.6, ora esiste), corretti i due nomi di FK troncati dal vecchio export su `cfg_categoria_sottocategoria`. Colonne, vincoli, indici, funzioni, trigger e RLS di tutte le tabelle coincidono con il database.

### ~~`risparmi_periodo` sostituisce movimenti veri~~ · ~~la dichiarazione è datata all'inizio del periodo~~ → risolte il 25/08/2026
**Cosa è cambiato**: `saldo_conto()` non sottrae più le dichiarazioni. La formula è tornata `apertura + entrate − uscite`, la stessa della banca, e parte dalla **data dell'apertura** invece che dall'inizio dei tempi. I bonifici verso i salvadanai sono diventati normali uscite di `spese`, categoria "Risparmi", con la data vera del bonifico (migrazione README §8.11); `v_risparmi_mese` legge il risparmio effettivo da quei movimenti ed esclude quelle uscite da "Totale Speso", perché mettere da parte non è spendere. `risparmi_periodo` resta il *quanto volevo mettere via* della pagina Risparmi e non tocca più nessun saldo.

Entrambe le voci cadono per la stessa ragione: **sparisce la seconda strada**. Non c'è più un modo di far uscire denaro dal conto che non sia una riga di `spese`, quindi non c'è più niente da tenere allineato a mano, né una data di comodo diversa da quella in cui il denaro si muove.

La migrazione è **a saldo invariato con qualsiasi versione del codice**, e non per caso: le uscite che inserisce (14.912,07 €) sono esattamente pari al risparmio dichiarato che azzera, nello stesso script. Si può quindi lanciare prima o dopo il deploy senza finestre in cui i numeri saltano.

**Applicata al database il 25/08/2026** con il connettore MCP di Supabase, nei due blocchi separati che il SQL Editor aveva unito in un'unica transazione (il primo tentativo era fallito sul blocco 2 e aveva fatto rollback anche del blocco 1). Il blocco 2 — la vista — risultava già in piedi; è stato eseguito il solo blocco 1. Dopo: categoria `Risparmi` creata, `risparmi_periodo` azzerato (era 14.912,07), saldo del conto personale **3.259,04 €**, che è il saldo WeBank al 25/08/2026. Le righe in categoria Risparmi sono però **21 e non 23**: due delle sette ricategorizzazioni non hanno agganciato niente — vedi la voce aperta del 25/08.

### ~~La tessera Revolut non diceva di che giorno era la fotografia~~ → corretto il 25/08/2026
**Cosa era**: su `/saldi` la data dello snapshot compariva solo quando aveva più di 45 giorni. Le altre due tessere sono saldi calcolati a oggi; quella è una fotografia, e senza la data si legge come le altre — così uno scarto di pochi euro contro l'app Revolut sembra un errore dell'app, mentre è il mercato che si è mosso da allora.
**Cosa è cambiato**: la data si dice sempre ("fotografia del …"), e oltre i 45 giorni resta l'avviso più forte. Il commit veniva dal branch `claude/app-audit-dropdown-sort-oigtqr`, rimasto fuori da ogni PR: recuperato con cherry-pick e portato in `main` insieme al resto.

### ~~Non c'è nessun controllo che guardi fuori dall'app~~ → aggiunto il 25/08/2026
**Cosa era**: ogni totale dell'app è coerente per costruzione — torna con i movimenti perché dai movimenti è calcolato — e proprio per questo **nessun controllo interno può accorgersi di un movimento mai registrato**. È la ragione per cui uno scarto di 829,78 € è cresciuto per diciotto mesi in silenzio: non esisteva un solo numero di fonte esterna con cui confrontarsi.
**Cosa è cambiato**: la tabella `b2f_saldi_verifica` (README §8.12) tiene il saldo dichiarato dalla banca, per conto e per data; `/saldi` ricalcola il proprio saldo **a quella data** e mostra il confronto, con la tolleranza di 1 € per gli arrotondamenti. Uno scarto si vede in giorni invece che in anni. Va alimentata a mano, dieci secondi ogni volta che si apre un estratto: è l'unico punto del sistema in cui un numero entra da fuori, e vale la pena che sia un gesto consapevole.

### ~~Il saldo del conto personale non è quello della banca~~ → chiuso il 25/08/2026, scarto **0,00**
**Cosa è cambiato**: riconciliati riga per riga tutti i 1.188 movimenti bancari dal 03/01/2025 al 25/08/2026 (cinque estratti PDF trimestrali più due export .xlsx) contro le righe di `spese`; corrette le 33 differenze trovate. Al 30/06/2026 e al 25/08/2026 il saldo calcolato dall'app e quello dichiarato da WeBank coincidono al centesimo. Sotto, la cronaca completa: serve perché le stesse categorie di errore possono ripresentarsi, e perché il metodo (accoppiamento per importo con tolleranza di ±7 giorni sulla data) è l'unico che funziona su questa tabella.

**Le scritture applicate il 25/08/2026**, tutte reversibili (valori precedenti annotati qui sotto):

| intervento | righe | effetto sul saldo |
|---|---|---|
| inserite le entrate e le uscite presenti in banca e mai registrate | 18 | +1.681,37 |
| eliminate le righe di `spese` che in banca non esistono | 11 | +243,15 |
| corretti due movimenti a un centesimo di distanza (63,10→63,11 il 09/07/2025, 8,29→8,28 il 16/07/2025) | 2 | 0,00 |
| eliminato un doppione da 2,70 (McDonald's importato due volte, con data valuta e con data contabile) | 1 | +2,70 |
| eliminata l'uscita da 600,00 dell'11/06/2026, che era un bonifico Revolut contato anche come risparmio | 1 | +600,00 |
| `impostazioni`: `saldo_iniziale` 2.869,54 → **2.876,61**, `valido_dal` 2000-01-01 → **2025-02-26** (allineato anche sulla seconda riga, per non lasciare due verità) | 2 | +7,07 |
| `risparmi_periodo`: dichiarazioni allineate ai bonifici Revolut realmente partiti (totale da 11.873,26 a 14.912,07) | 17 | −3.038,81 |

Valori precedenti delle dichiarazioni, per poter tornare indietro: 2025-03-31 412,38 · 2025-04-29 603,44 · 2025-05-29 685,00 · 2025-06-23 845,00 · 2025-06-30 770,98 · 2025-08-28 670,00 · 2025-09-27 666,00 · 2025-10-28 645,00 · 2025-11-27 480,00 · 2025-12-17 690,00 · 2025-12-23 302,00 · 2026-01-30 435,00 · 2026-02-26 680,00 · 2026-04-01 760,00 · 2026-04-29 696,46 · 2026-06-01 978,62 · 2026-07-01 782,40.

**Quello che resta storto, e non è un errore di dati**: ai punti intermedi lo scarto non è zero (−18,30 al 30/06/2025, −1.177,00 al 31/12/2025, −20,10 al 31/03/2026). È lo sfasamento documentato nella voce aperta qui sopra: la dichiarazione è datata all'inizio del periodo, il bonifico parte dopo — al 31/12/2025 l'app ha già tolto i 1.170,00 dichiarati il 23/12 mentre in banca sono usciti il 07/01. Si riassorbe da solo, ma finché `saldo_conto()` sottrae le dichiarazioni per `data_bonifico` il saldo resta sbagliato per una parte di ogni mese.

**Conseguenza da tenere d'occhio**: ora `coerenza()` su `/spese/revolut` segnala 1.244,33 di risparmio dichiarato in più rispetto a quello che c'è su Revolut. **Non è un errore nuovo**: il dichiarato ora misura tutto il denaro *versato* verso Revolut (verità bancaria), i salvadanai misurano quello che c'è *oggi* — e da Revolut è anche uscito qualcosa (430,17 rientrati il 27/05/2026, 150,00 il 03/08/2026, più le spese fatte con la carta Revolut). È esattamente il limite descritto nella voce aperta "L'app sa quanto *vale* l'investimento, non quanto ci è stato *versato*".

### [2026-08-14] Il saldo del conto personale mostrato dall'app non è quello della banca: € 3.859,16 contro € 3.354,64
**Cosa**: con gli stessi occhi, lo stesso giorno (14/08/2026): `/saldi` mostra "WeBank Personale € 3.859,16 · 1027 movimenti, al netto dei risparmi"; il conto vero (WeBank CC 1088-00062465) dice "Saldo disponibile 3.354,64 €". **Scarto: € 504,52 in eccesso nell'app.** Gli altri due conti tornano: P.IVA € 1.506,15 identico al saldo WeBank del CC 00180479; Revolut salvadanai € 8.525,63 contro € 8.525,86 sommando i quattro salvadanai a schermo (−0,23, interessi maturati dopo lo snapshot) e investimenti € 5.272,33 contro € 5.293,13 (−20,80, mercato). Cioè: l'unico conto che non torna è quello calcolato in avanti dall'app, non quelli fotografati.
**Perché si rompe**: `spese/dati.py::saldo_conto()` è `saldo_iniziale + entrate − uscite − risparmio_totale()`, una catena in cui ogni anello può spostare il totale senza dare errore — (a) `impostazioni.saldo_iniziale` con `valido_dal` più vecchio è il valore di apertura e non è mai stato verificato contro un estratto (già segnalato nella voce dei "Fatti" del 13/08: "resta da verificare che il *valore* di `saldo_iniziale` in tabella sia quello giusto"); (b) movimenti mai importati (l'import da banca è manuale: ogni riga non caricata è uno scarto permanente); (c) `risparmi_periodo` sottratto una volta di troppo o di meno; (d) righe duplicate dall'import. Le quattro cause danno lo stesso sintomo — un numero plausibile e sbagliato — e si distinguono solo riconciliando riga per riga.
**Cosa si sa dopo gli estratti (14/08, stessa sessione)**: l'utente ha fornito sette estratti conto trimestrali, dal 25/09/2024 al 30/06/2026. Sono stati letti 1.310 movimenti e **i totali ricavati combaciano al centesimo con quelli dichiarati dalla banca in ognuno dei sette** (es. Q2 2026: +9.513,13 / −7.980,20), e 1.624,39 (saldo al 30/09/2024) più la somma delle 1.310 righe fa esattamente 3.492,51, il saldo dichiarato al 30/06/2026. Il lato banca è quindi una base certa, riga per riga: lo scarto sta tutto nel lato app. Restano quattro ipotesi, che la riconciliazione riga-a-riga distingue: `saldo_iniziale` sbagliato, movimenti mai importati, doppioni, risparmio sottratto due volte. **Su quest'ultima**: gli estratti mostrano che i versamenti verso i conti propri (Revolut) sono movimenti bancari veri — 34 uscite per € 13.389,38, meno € 607,58 di rientri, **netto € 12.781,80** nel periodo. Se quelle righe sono state importate in `spese` come uscite, `saldo_conto()` le conta una volta come uscita e una seconda volta dentro `risparmio_totale()`; l'errore però spinge il saldo *verso il basso*, mentre qui è troppo alto — quindi o non sono importate, o convivono due errori di segno opposto e quello dei movimenti mancanti è il più grande.
**Impatto**: il saldo è l'ancora di tutta la pagina Saldi e della home, ed è il numero su cui si decide se si può spendere. Uno scarto di mezzo migliaio di euro in eccesso è nella direzione peggiore.
**La riconciliazione, eseguita (14/08)**: la query è girata sul database vero. Al 30/06/2026 — l'ultima data in cui la banca dichiara un saldo, quindi l'unico confronto pulito — la banca dice 3.492,51 e l'app calcola 2.324,65. Lo scarto di −1.167,86 si scompone **esattamente**, senza residui:

| voce | effetto su (app − banca) |
|---|---|
| ancora: `saldo_iniziale` 2.869,54 contro 2.866,31 reali al 26/02/2025 | +3,23 |
| 12 bonifici verso conti propri non registrati in `spese` | +11.722,38 |
| risparmio dichiarato in `risparmi_periodo` che li sostituisce | −11.090,86 |
| **→ residuo del meccanismo risparmi** | **+631,52** |
| 35 righe della banca mai registrate | −1.380,87 |
| 27 righe di `spese` che in banca non esistono | −421,74 |
| 520 righe registrate con la data spostata di qualche giorno | **0,00** |
| **totale** | **−1.167,86** |

**La riga che vale zero è la scoperta più importante della seconda query**: le 547 righe che sembravano "spese non bancarie" hanno tutte `metodo_pagamento = Webank`, e 537 hanno in banca una riga di importo identico entro 7 giorni. Non sono spese fatte con altri strumenti: sono gli stessi movimenti registrati con la **data valuta** invece della data contabile (o viceversa). Sul saldo non pesano — entrano ed escono dallo stesso conto, solo in un altro giorno — ma rendono inservibile ogni confronto che accoppi su data esatta, e gonfiano di dieci volte l'apparente disallineamento (555 "buchi" contro ~18 veri). Chiunque riconcili questa tabella in futuro deve accoppiare con tolleranza sulla data, o vedrà un disastro che non c'è.

Quindi l'app sbaglia **in tutte e due le direzioni insieme**, e oggi (14/08) il saldo è in eccesso di 504,52 solo perché dal 01/07 in poi ha registrato +1.534,51 mentre la banca faceva −137,87: nei due mesi non coperti dagli estratti mancano ~1.672 € di uscite (luglio 2026: 76 righe per +2.814,36 di netto, agosto: 24 righe per −497,45). Un dato buono: maggio e giugno 2026 combaciano al centesimo, con lo stesso numero di righe — l'import recente funziona, il guasto è nello storico.
**Come si chiude**: delle 35 righe mancanti, 16 sono assenze vere (+1.737,37: accrediti Satispay, rimborsi da amici, spese col bancomat mai registrate) e vanno inserite — script pronto, idempotente, che usa `insert_spesa_first_free_id` come fa l'app; 16 hanno una gemella in `spese` oltre la tolleranza di 7 giorni o a un centesimo di distanza (−63,11 contro −63,10, −8,28 contro −8,29) e non vanno toccate; 3 riguardano Revolut e dipendono dalla decisione sui trasferimenti. Fatto quell'inserimento resta **+569,51**, e anche quello è tutto attribuito: +631,52 di bonifici non coperti dal dichiarato, +612,38 delle due ricariche Revolut fatte **con la carta** (che sfuggono anche alla regola dei bonifici: nessuno le toglie, in nessuno dei due modi), −430,17 del rientro da Revolut del 27/05 mai registrato, −247,45 di 12 righe di `spese` che in banca non esistono (ipotesi da verificare: pagamenti Satispay registrati uno per uno mentre la banca porta solo l'addebito SDD cumulativo — sarebbero contati due volte), +3,23 di ancora.
**Stato**: causa trovata e quantificata; correzione 1 (le 16 righe) preparata e provata, non ancora applicata (tocca dati reali, non codice: va decisa con l'utente). Il pezzo più grosso non è un bug di calcolo ma il meccanismo dei risparmi — voce sotto. La query di riconciliazione è stata verificata prima dell'uso su un PostgreSQL 16 locale con lo schema reale e buchi/doppioni iniettati apposta.

**Aggiornamento 25/08/2026 — il pezzo mancante è stato trovato, e lo scarto torna a zero.** Con l'estratto WeBank del conto personale dal 01/07 al 25/08 (107 righe) e l'accesso diretto al database, la riconciliazione riga per riga accoppia **104 righe su 107** (importo firmato uguale, data entro ±7 giorni su contabile o valuta). Le tre righe di banca non accoppiate e le due di `spese` spiegano lo scarto **per intero, senza residuo**:

| voce | effetto su (app − banca) |
|---|---|
| 09/07/2026, bonifico di € 2.457,48 "favore Emanuele Bellotti" mai registrato in `spese` | +2.457,48 |
| risparmio dichiarato per il periodo 01/07 (`risparmi_periodo`) | −782,40 |
| doppione: lo stesso McDonald's da € 2,70 importato due volte (id 1024 con data valuta 12/08, id 1029 con data contabile 13/08, da due import diversi — `created_at` 12/08 e 14/08); in banca la riga è una sola | −2,70 |
| **scarto luglio-agosto** | **+1.672,38** |
| scarto al 30/06 già scomposto sopra | −1.167,86 |
| **= scarto di oggi, app 3.763,56 contro banca 3.259,04** | **+504,52** |

Due conferme che vengono dallo stesso confronto: (1) **le entrate combaciano al centesimo** — 4.947,09 su entrambi i lati nei due mesi: il guasto è tutto sulle uscite; (2) il **giroconto P.IVA di € 3.491,85** registrato come riga unica del 31/07 in banca è arrivato in **due tranche** (2.000,00 il 05/08 e 1.491,85 il 13/08, "trasferimento da conto *0479"): l'importo è esatto, la data no. Sul saldo di oggi non pesa, ma sposta di due settimane il confine di periodo che `v_periodi_stipendio` apre proprio su quel giroconto, e con lui il "Totale Speso" e il risparmio consigliato di due periodi.

**Cosa manca per chiudere**: sapere dove sono andati i 2.457,48 del 09/07 (Revolut? HYPE? un altro conto?). Da lì dipende la correzione: se erano risparmio, il dichiarato di 782,40 per quel periodo è incompleto e va portato a 2.457,48; se erano una spesa vera, va inserita la riga in `spese` e il dichiarato va azzerato, altrimenti quel denaro viene tolto due volte. I due snapshot Revolut disponibili (13/08 e 25/08) sono entrambi successivi e non permettono di dedurlo. **Attenzione**: sistemare solo luglio-agosto senza sistemare anche le 16 righe mancanti pre-30/06 non fa combaciare il saldo — lo fa passare da +504,52 a −1.167,86, cioè inverte il segno dell'errore.

**Correzione applicata il 25/08/2026** (decisa dall'utente: i 2.457,48 erano andati su Revolut, quindi erano risparmio). Due scritture sul database vero, tramite connettore:

1. `risparmi_periodo`, `data_bonifico = 2026-07-01`: `effettivo_risparmio` da **782,40 → 2.457,48** (l'unico trasferimento verso Revolut in quel periodo; il bonifico di 50,00 del 14/07 è HYPE ed era già registrato come uscita).
2. `spese`: eliminata la riga **id 1029** (2026-08-13, € 2,70, "Mcdonald'S 35 Mil Ano", metodo "Import banca", categoria_link_id `c2827ce1-153b-4844-88a1-d07e22ea4b29`), doppione di `id 1024` (2026-08-12, stesso importo). Verificato prima che non fosse referenziata da `b2f_spese_piva.giroconto_personale_id` né da `b2f_fatture.giroconto_personale_id`.

Il saldo dell'app passa da 3.763,56 a **2.091,18**, e lo scarto contro la banca da +504,52 a **−1.167,86: esattamente, al centesimo, il residuo pre-30/06 già scomposto sopra**. Il contributo di luglio-agosto è ora zero — la conferma più forte che la scomposizione era giusta.

**Attenzione a come si legge il numero adesso**: la pagina Saldi mostra meno di quello che c'è in banca, non più. Non è un peggioramento, è lo stesso errore di prima con l'altro pezzo tolto di mezzo: restano da correggere le 16 righe mancanti pre-30/06 e le altre voci di quella tabella. Fino ad allora il saldo del conto personale resta indicativo.

**Seconda riconciliazione, 25/08/2026 — periodo 27/02/2026 → 30/06/2026 (estratto WeBank, 281 righe).** Accoppiate **275 su 281**. Le sei righe rimaste, più una di `spese`, spiegano tutto:

| riga di banca | in `spese`? | effetto |
|---|---|---|
| 13/03 −737,00 "favore emanuele bellotti **notprovide**" | no | bonifico a Revolut |
| 02/04 −2.040,00 idem | no | bonifico a Revolut |
| 27/05 −430,17 idem, e **+430,17 rientrato lo stesso giorno** ("BON.DA EMANUELE BELLOTTI RISPARMI", rif. `PY05Q…` = Revolut) | nessuna delle due | netto zero |
| 11/06 −600,00 idem | **sì**, id 899 | bonifico a Revolut, ma registrato come uscita |
| 30/03 due pagamenti da −4,50 | registrati come **una** riga da 9,00 (id 727) | netto zero |

**La discriminante è nella causale**, e vale su tutto lo storico: i bonifici verso Revolut sono `vostra disposizione … favore emanuele bellotti notprovide` (minuscolo, importi grossi, canale diverso); i `VS.DISP. RIF. … FAVORE EMANUELE BELLOTTI . NR. BONIFICO SEPA` (maiuscolo, 50,00 ogni mese) sono il giroconto ricorrente su **HYPE**, e quelli sono sempre registrati come uscite. Nel periodo 27/02 → 25/08 i bonifici Revolut sono esattamente cinque: 737,00 · 2.040,00 · 430,17 (tornato indietro) · 600,00 · 2.457,48. Nessuna ricarica Revolut con carta.

**Correzioni applicate** (stessa regola scelta dall'utente: quello che va su Revolut è risparmio, si dichiara e non si registra come uscita):

| periodo | prima | dopo | perché |
|---|---|---|---|
| 2026-02-26 | 680,00 | **737,00** | bonifico del 13/03 |
| 2026-04-01 | 760,00 | **2.040,00** | bonifico del 02/04 |
| 2026-04-29 | 696,46 | **0** | l'unico bonifico del periodo è rientrato lo stesso giorno |
| 2026-06-01 | 978,62 | **600,00** | bonifico dell'11/06 |
| `spese` id 899 | 600,00 uscita 11/06 (`categoria_link_id` `dfc2a0e0-8fff-4c12-a923-99304a0790f8`, metodo Webank) | **eliminata** | era lo stesso bonifico contato una seconda volta come uscita |

**Risultato: lo scarto è ora costante a −829,78 sia al 30/06 sia al 25/08.** Un residuo che non cambia più fra due date lontane due mesi significa che **da fine febbraio 2026 in poi app e banca si muovono in perfetto passo**: tutto l'errore rimasto è anteriore al 27/02/2026. Previsione verificabile: il saldo WeBank al 26/02/2026 deve essere **3.245,67** (l'app dice 2.415,89). Per chiudere serve l'estratto **27/02/2025 → 26/02/2026**, l'unico anno mai riconciliato riga per riga.

**Storico bancario completo ricostruito, 25/08/2026.** Cinque estratti trimestrali PDF (Q1 2025 → Q1 2026) più i due export .xlsx: **1.188 movimenti dal 03/01/2025 al 25/08/2026**, uniti in un unico file. Ogni PDF si autoverifica (saldo iniziale + entrate − uscite = saldo finale dichiarato, al centesimo) e la catena ricostruita centra **tutti e sette** i saldi dichiarati dalla banca: 3.978,51 (31/03/25) · 4.416,27 (30/06/25) · 4.358,50 (30/09/25) · 4.372,17 (31/12/25) · 1.959,58 (31/03/26) · 3.492,51 (30/06/26) · 3.259,04 (25/08/26). Il lato banca è quindi una base certa su tutto il periodo, non più solo fino al 30/06/2026. Nota per chi riparserà i PDF: nelle righe di **entrata** l'importo è incollato alla descrizione (`1.944,00BON.DA SILERON S.R.L.`) e non è un token numerico a sé — un parser ingenuo estrae tutte le uscite e **zero** entrate, e i totali sembrano comunque plausibili.

**Dove sta il residuo di −829,78**, con i numeri:

| voce | importo |
|---|---|
| **l'ancora**: `impostazioni.saldo_iniziale` = 2.869,54 contro il saldo reale al 26/02/2025 (giorno prima della prima riga di `spese`) = **2.876,61** | **−7,07** |
| l'anno 27/02/2025 → 26/02/2026, mai riconciliato riga per riga | −822,71 |

Sul secondo pezzo, quello che si vede già dal solo lato banca: nell'anno sono usciti verso Revolut **9.673,21** in 17 bonifici con causale `NOTPROVIDE`, contro **8.712,78** dichiarati in `risparmi_periodo` — **960,43 mai dichiarati**. Da solo questo renderebbe l'app *più alta* della banca di 960,43; siccome invece è *più bassa* di 822,71, convivono ~1.783 € di errori di segno opposto — cioè bonifici Revolut registrati **anche** come uscite in `spese` (lo stesso doppio conteggio già trovato sul bonifico di giugno 2026) e/o entrate mai registrate. Per separarli servono le righe di `spese` di quell'anno: il connettore Supabase si è disconnesso a metà lavoro e la query non è stata eseguita.

**Riconciliazione finale, 25/08/2026 — l'anno 27/02/2025 → 26/02/2026.** 668 righe di banca contro 651 di `spese`: **accoppiate 638**. Lo scarto di −829,78 si scompone **al centesimo, senza residuo**:

| voce | effetto su (app − banca) |
|---|---|
| l'ancora: `saldo_iniziale` 2.869,54 contro 2.876,61 reali al 26/02/2025 | −7,07 |
| 8 bonifici Revolut (`NOTPROVIDE`) mai registrati | +8.465,21 |
| 2 ricariche Revolut **con carta** mai registrate (20/05 e 11/06/2025, `REVOLUT**4658* DUBLIN IE`) | +612,38 |
| 5 entrate mai registrate: 1.638,81 e 216,60 di accrediti Satispay, 15+15+23 di rimborsi da amici | −1.908,41 |
| 14 uscite mai registrate (fra cui 126,87 e 1,07 in Giappone, un bonifico continuativo da 50) | +298,43 |
| 13 righe di `spese` che in banca non esistono (quasi tutte senza descrizione, caricate il 30/12/2025; due sono la stessa spesa a un centesimo di distanza: 63,10 contro 63,11 e 8,29 contro 8,28) | −314,54 |
| risparmi dichiarati nel periodo | −7.975,78 |
| **totale** | **−829,78** |

**La scoperta che spiega il meccanismo**: confrontando periodo per periodo il dichiarato con il bonifico Revolut realmente partito, **le dichiarazioni sono sistematicamente sfasate di un periodo**. Dichiarato 685 per il periodo che chiude il 22/06, e 685,00 partiti il 24/06; dichiarato 845 per il periodo del 23/06, e 845,00 partiti il 30/06; dichiarato 770,98 per il 30/06, e 770,98 partiti il 30/07. Non è un caso: si dichiara alla chiusura del periodo e si bonifica all'apertura del successivo. Il totale però non torna lo stesso — **nell'anno sono usciti verso Revolut 9.077,59 mai registrati in `spese`, contro 7.975,78 dichiarati: 1.101,81 non dichiarati da nessuna parte**. (Altri 1.202,00 di bonifici Revolut, del marzo-maggio 2025, sono invece registrati come normali uscite: quelli il saldo li toglie correttamente una volta sola.)

**Cosa serve per chiudere**, con l'effetto di ciascun pezzo sul saldo:

| intervento | righe | effetto |
|---|---|---|
| ancora: `impostazioni.saldo_iniziale` → 2.876,61, `valido_dal` → 2025-02-26 | 1 | +7,07 |
| inserire le entrate mancanti | 5 | +1.908,41 |
| inserire le uscite mancanti | 14 | −298,43 |
| eliminare (o correggere di un centesimo) le righe che in banca non esistono | 13 | +314,54 |
| portare il dichiarato totale a 9.077,59 | ~4 periodi | −1.101,81 |
| **saldo app = saldo banca** | | **+829,78** |

Nessuno dei pezzi da solo chiude: applicarne una parte sposta il saldo mostrato senza avvicinarlo al vero. Le 13 righe senza descrizione sono l'unico punto che richiede il giudizio dell'utente (spese in contanti mai passate dal conto, oppure doppioni).


---

### ~~Due righe in `impostazioni`, e solo la più vecchia conta per il saldo~~ → corretto il 25/08/2026
**Cosa è cambiato**: `saldo_iniziale` portato al valore reale verificato sull'estratto (2.876,61 al 26/02/2025, giorno prima della prima riga di `spese`) e `valido_dal` da 2000-01-01 a 2025-02-26, che è la data a cui quel numero si riferisce davvero; allineata anche la seconda riga, così non restano due `saldo_iniziale` diversi in tabella. Resta da fare la parte di codice: `saldo_conto()` somma ancora tutto quello che trova invece di partire dalla data dell'apertura, quindi importare movimenti anteriori al 26/02/2025 li conterebbe due volte.

### [2026-08-14] Due righe in `impostazioni`, e solo la più vecchia conta per il saldo
**Cosa**: `impostazioni` ha due righe — `valido_dal` 2000-01-01 (percentuale 0,25) e 2026-02-25 (percentuale 0,35) — con lo **stesso** `saldo_iniziale` 2.869,54. `saldo_iniziale()` legge la riga con `valido_dal` più vecchio, ed è corretto così (è l'apertura). Ma il valore 2.869,54 è il saldo reale al **26/02/2025** (2.866,31 in banca, 3,23 di scarto), non al 2000-01-01: la data è un'etichetta che mente, e `spese` infatti comincia il 27/02/2025.
**Perché si rompe**: due modi concreti. (1) Chi guarda la tabella non ha modo di sapere a che data si riferisce quell'importo — se un domani si importassero i movimenti 2024 (gli estratti ci sono), verrebbero sommati sopra un'apertura che li contiene già, e il saldo salterebbe di ~1.240 € senza nessun errore. (2) Aggiornare `saldo_iniziale` sulla riga **nuova** — la cosa naturale da fare, visto che è quella "valida oggi" — non cambia niente: l'app legge solo la più vecchia, e la modifica sparisce in silenzio.
**Impatto**: nessun danno oggi; una trappola sicura al primo intervento sui dati storici o alla prima correzione dell'apertura.
**Stato**: aperto. Minimo sindacale: portare `valido_dal` della prima riga a 2025-02-26 (è quello che il numero significa davvero) e mettere il valore esatto, 2.866,31. Meglio: che `saldo_conto()` parta da quella data invece di sommare tutto ciò che trova, così una riga più vecchia dell'apertura non può falsare il saldo.

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
- 2026-08-13 (trovato dall'agente di audit "Verifica finale Fatture"): il fix dell'aliquota 15% post-agevolazione (`_aliquota_imposta_per_anno()`) correggeva solo `param["aliquota_imposta"]` per l'anno di oggi (`_get_parametri()`) e per il riepilogo mensile dentro `_situazione_data()`, ma non per gli altri tre consumatori dello stesso `param`: la card "Da accantonare" (sia l'aggregato annuale in `_situazione_data()` sia quella per singola fattura in `storico.py: fattura_dettaglio()`) e — più grave — `giroconto.py: api_giroconto_esegui()`, che scrive davvero lo spostamento sul database. Riprodotto con `anno_fine_regime_agevolato=2027` (già selezionabile oggi dal menu, non serve aspettare il 2031): la card mostrava un accantonamento sottostimato di centinaia di euro rispetto al 15% dovuto, e un giroconto eseguito in quelle condizioni avrebbe spostato sul personale più soldi di quanti dovessero restare accantonati per le tasse. Fix: in tutti e tre i punti, `param["aliquota_imposta"]` viene ora riscritta con `_aliquota_imposta_per_anno(param, anno_fattura_o_visualizzato)` prima di `acc.scomponi()`. Verificato con harness: card e riepilogo mensile ora concordi (€ 3.039,27 in entrambi, non più € 2.494,30 vs € 743,14/mese), giroconto eseguito su fattura test 2031 sposta l'importo corretto.
- 2026-08-13: tessere KPI di `/spese/revolut`, `/saldi` e della card saldi in home arrotondavano all'euro (`eur(x, 0)`) mentre il resto delle stesse pagine (dettaglio salvadanai, righe "come si formano questi saldi") mostrava 2 decimali — incoerente proprio dove l'utente sta riconciliando cifre esatte. Fix: tutte le tessere di saldo/conto ora usano `eur()` col default a 2 decimali.
- 2026-08-13: `coerenza()` confrontava il risparmio dichiarato (`D.risparmio_totale()`) solo contro `rev["risparmi"]` (i salvadanai), escludendo `rev["investimenti"]`. Sui dati reali dell'utente: dichiarato € 11.873,26, salvadanai € 8.525,63 → scarto € 3.347,63 segnalato come "risparmiato più di quanto ci sia". Letto l'estratto conto Revolut reale (che non contiene mai la valorizzazione del portafoglio, solo dividendi/vendite/PnL — confermato leggendo `consolidated-statement-v2_2024-09-10_2026-08-13...xlsx`): nel periodo risultano € 4.444,28 netti versati verso l'investimento, ordine di grandezza compatibile con lo scarto — cioè una parte del risparmio dichiarato non è sparita, è stata investita. Chiesto all'utente come trattarlo (includere gli investimenti nel confronto pur sapendo che le plusvalenze possono generare uno scarto nella direzione opposta, ammorbidire solo il messaggio, o tracciare il costo storico a parte): scelto includere gli investimenti. Fix: `coerenza()` ora confronta il dichiarato contro `risparmi + investimenti`; `_riquadro_coerenza()` spiega in entrambe le direzioni che lo scarto può derivare da una plus/minusvalenza di mercato, non solo da un periodo dimenticato.

- 2026-08-14: i menù a tendina che elencano dati erano ordinati in tre modi diversi — le colonne `ordine` del database (categorie/sottocategorie del conto personale), l'ordine in cui erano state scritte a mano (categorie P.IVA, tipi cliente, metodi di pagamento), l'ordine di arrivo dal portale (progetti e task delle ore). Fix: `shared/ordina.py` (accenti appiattiti, maiuscole ignorate: con `sorted()` crudo "Caffè" finiva dopo "Spesa") applicato alla sorgente di ogni elenco, così tutti i menù che ne discendono ereditano l'ordine; restano nella sequenza naturale mesi, anni, stati della fattura e scenari di accantonamento, dove l'ordine è informazione. Verificato con `tools/verifica_menu.py` (nuovo): apre 21 pagine, estrae 25 menù fra `<select>`, `<datalist>` ed elenchi che arrivano via API, e controlla l'ordine di ognuno.
- 2026-08-14: l'harness `tools/preview.py` non copriva l'area Spese — l'elenco dei moduli in cui rimpiazzare `get_client`/`is_configured` era scritto a mano e non conteneva `spese/dati.py`, che è il passaggio obbligato di tutta l'area: `/spese/movimenti`, `/spese/importa`, `/spese/risparmi` e `/spese/revolut` rispondevano "Supabase non configurato" invece di mostrare i dati finti, quindi ogni verifica su quelle pagine passava senza guardare niente. Fix: si scorrono i moduli già importati dei pacchetti dell'app invece di elencarli; aggiunto al finto database l'albero `cfg_categorie`/`cfg_sottocategorie`/`cfg_categoria_sottocategoria` con le righe collegate già annidate come le restituisce PostgREST. Tutte le 48 rotte GET rispondono 200 con dati veri in pagina.

## Scartati (e perché)

- *Escludere rivalsa/bollo dal calcolo dell'imponibile*: richiesta iniziale dell'utente, scartata dopo verifica — la normativa dice il contrario (concorrono al reddito). Vedi README §4.
