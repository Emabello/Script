# Mappa del repository

Cosa fa ogni file, uno per uno. Serve a sapere **dove guardare** senza
aprire tutto: il README racconta il dominio (fisco, accantonamento,
migrazioni), qui c'è la corrispondenza file → responsabilità, con le
trappole che quel file nasconde.

Ultimo aggiornamento: 2026-08-12 · 33 file di codice e configurazione.

**Regola d'oro**: se una modifica tocca un numero, il file che lo calcola
è uno solo. Prima di scrivere un calcolo, cercalo qui.

---

## Dove sta cosa — indice rapido

| Ti serve… | File |
|---|---|
| Aggiungere una rotta all'app | `app.py` (hub) · `fatture/*.py` · `spese/*.py` |
| Cambiare un calcolo fiscale | `fatture/fiscale.py` (`_situazione_data`) |
| Cambiare quanto accantonare | `fatture/accantonamento.py` |
| Spostare soldi fra i due conti | `fatture/giroconto.py` |
| Scrivere sul conto personale | `spese/dati.py` — **unico posto** |
| Saldo reale dei conti | `fatture/fiscale.py::saldo_piva` · `spese/dati.py::saldo_conto` · `spese/revolut.py::saldo_revolut` |
| Risparmi, salvadanai, Revolut | `spese/revolut.py` |
| Stati della fattura, rivalsa | `fatture/costanti.py` |
| Colori, spaziature, icone | `shared/design.py` |
| Struttura di pagina, home | `shared/theme.py` |
| Formattare euro/date/% | `shared/fmt.py` — **non riscriverli** |
| Il PDF facsimile | `shared/pdfgen.py` |
| Guardare le schermate senza DB | `tools/preview.py` |

---

## Radice

### `app.py` — 297 righe · entry point

Monta i blueprint sulla app Flask che nasce in `xs_server.py`, e definisce
la **home**.

- Rotte: `GET /` (launchpad), `GET /api/kpi/fatture`, `GET /api/kpi/spese`,
  `GET /health`.
- `_dashboard_data()` raccoglie i dati della home: **saldi dei due conti**,
  incassato del mese, accantonamento, scadenze, ultime fatture, ultimi
  movimenti. Ogni blocco sta in un `try` suo: se una query fallisce la home
  perde un riquadro, non la pagina.
- Applica `ProxyFix` — senza, dietro il proxy di Render l'origin calcolato
  per WebAuthn resta `http://` e la verifica biometrica fallisce.
- Aggiunge gli endpoint WebAuthn a `xs_server.ALLOW_NO_PIN`: `auth/*` è il
  meccanismo con cui ci si sblocca, non può richiedere di essere sbloccati.

> **Trappola**: `_dashboard_data` non deve rifare i conti a mano. I saldi e i
> totali arrivano da `fatture.fiscale.saldo_piva` e `spese.dati` — c'era una
> query locale che ignorava le righe storiche `tipo=giroconto` e dava un
> numero diverso da quello di `/spese` sulla stessa domanda.

### `xs_server.py` — 1.371 righe · il timesheet, e la app Flask

L'app originale delle ore. Crea l'oggetto `app` che tutto il resto estende.

- Rotte ore: `/ore`, `/api/catalog`, `/api/range`, `/api/add`, `/api/delete`.
- Rotte sblocco: `/api/status`, `/api/unlock`.
- PWA: `/manifest.webmanifest`, `/icon-192.png`, `/icon-512.png`,
  `/apple-touch-icon.png`, `/sw.js` (icone in base64 inline).
- Google Calendar: `/oauth/start`, `/oauth/callback`,
  `/api/google/{status,calendars,select_calendar,preview,import,export}`.
  Import: titolo evento → cliente/progetto/task via `_alias_map()`.
- `PAGE` (righe 529-1359) è l'HTML+CSS+JS del calendario settimanale, con
  riepilogo mensile e grafici disegnati a mano in SVG.

> **`_gate()` è il controllo d'accesso di tutta la hub.** `before_request`
> su ogni rotta: le API rispondono `401 {"locked":true}`, le pagine HTML
> ricevono `locked_shell()` — la stessa shell, a corpo vuoto. Solo gli
> endpoint in `ALLOW_NO_PIN` passano. Prima di questo, bastava conoscere
> l'URL per leggere fatture e IBAN senza PIN.

### `xs_client.py` — 404 righe · client del portale ore

Parla con `ts.b2forge.com` in HTTP+scraping (`requests` + BeautifulSoup).

- `XSClient.login/get_catalog/get_day_entries/add_entry/delete_entry`.
- `_relogin()`: la sessione del portale scade e la pagina di login torna
  con 200, quindi si riconosce dal contenuto (`_looks_like_login`) e si
  rifà il login in modo trasparente.
- Ha anche una CLI (`python xs_client.py catalog|day|add`), usata per il
  collaudo. Non serve in produzione.

### `requirements.txt` · `render.yaml` · `Procfile`

Dipendenze e deploy. Avvio `gunicorn -w 1 app:app`: **un solo worker è
voluto**, la sessione sta in memoria del processo (come le challenge
WebAuthn). Con due worker lo sblocco funzionerebbe a intermittenza.

### `README.md` — 1.139 righe · il dominio

Come funziona il forfettario, l'accantonamento, il ciclo della fattura, le
trappole del database, le migrazioni SQL da lanciare, la sicurezza, il
deploy. **È la fonte per il “perché”**; questo file è la fonte per il
“dove”.

### `.gitignore`

`venv/`, `__pycache__/`, `.env`, artefatti locali.

---

## `fatture/` — fatturazione e fisco

### `fatture/__init__.py` — 10 righe

Crea `fatture_bp` e importa i sotto-moduli, che registrano le loro rotte
per effetto collaterale dell'import. L'ordine conta: `views` tira dentro
`clienti/storico/editor`.

### `fatture/costanti.py` — 164 righe · le regole del dominio, senza I/O

Nessuna query, nessun HTML: solo definizioni. È il file da leggere per
primo per capire l'area.

- `STATI` e derivati (`_LABEL`, `_CLASSE`, `_DESCR`), `STATI_PERCORSO`,
  `STATI_EMESSE` (cosa concorre al fatturato), `STATI_MODIFICABILI`
  (`bozza` e basta), `DATE_STATO` (quale data chiedere entrando in uno stato).
- `normalizza_stato()` mappa lo storico `emessa` → `inviata_studio`.
- `motivo_blocco()`: il testo mostrato quando non si può modificare. Dice
  **cosa fare invece**, non solo che è vietato.
- `scorpora_rivalsa()`: la rivalsa 4 % si estrae dal corrispettivo
  (`compenso = lordo / 1,04`), non si aggiunge sopra. La rivalsa è calcolata
  per differenza, così le due voci risommano esattamente al corrispettivo.
- `CATEGORIE_SPESE_PIVA`, `CATEGORIA_GIROCONTO`, `MESI_NOMI`.

### `fatture/views.py` — 145 righe · landing `/fatture`

Elenco delle sezioni con i contatori, card emittente, KPI accantonamento
caricato via `fetch` da `/fatture/api/situazione`.

> Il contatore “Storico” conta **tutte** le fatture dell'anno, bozze e
> annullate comprese (è quello che poi mostra la lista); la home invece
> conta solo `STATI_EMESSE`. Numeri diversi, domande diverse.

### `fatture/clienti.py` — 453 righe · anagrafica

- HTML: `/clienti` (ricerca + filtro tipo + attivi/inattivi),
  `/clienti/nuovo`, `/clienti/<cid>`.
- JSON: `POST /api/clienti`, `PATCH /api/clienti/<cid>`,
  `DELETE /api/clienti/<cid>` (soft delete: `attivo=false`),
  `GET /api/clienti-picker` (usato dall'editor).
- `_payload_clean()` restringe ai campi ammessi: il body non finisce mai
  dritto nella tabella.

> I clienti non si cancellano davvero: una fattura ne conserva lo
> *snapshot*, ma la FK `cliente_id` è `ON DELETE RESTRICT`.

### `fatture/editor.py` — 655 righe · compilazione del facsimile

- `GET /fatture/nuova`, `GET /fatture/<fid>/modifica`.
- La modifica su una fattura non più in bozza **non mostra un editor
  disabilitato**: reindirizza a `/fatture/<fid>?bloccata=1`, dove la
  spiegazione sta accanto allo stato.
- `_EDITOR_HTML` è una stringa raw con segnaposto: `__INIT__` si sostituisce
  **per ultimo** — porta dentro testo libero, e se un'altra sostituzione
  girasse dopo, una descrizione contenente `__PDF_SCRIPT__` verrebbe espansa.
- Tutto ciò che finisce in un blob JSON ha `<` → `<`: una riga con
  `</script>` dentro chiuderebbe il tag.
- `calc()` lato client: scorporo della rivalsa, bollo 2 € sopra 77,47 €,
  totale = imponibile + bollo addebitato. La variante “rivalsa addebitata”
  (corrispettivo + 4 %) è stata rimossa apposta.

### `fatture/storico.py` — 1.240 righe · lista, dettaglio, ciclo di vita

Il file più denso dell'area: qui vive la pagina che si guarda di più.

- HTML: `/storico` (filtri anno/stato + KPI), `/<fid>` (dettaglio).
- JSON: `GET/POST /api/fatture`, `GET /api/fatture/<fid>`,
  `PATCH /api/fatture/<fid>`, `DELETE /api/fatture/<fid>`,
  `PATCH /api/fatture/<fid>/stato`,
  `POST /api/fatture/<fid>/registra-entrata`,
  `GET /api/next_progressivo`.
- Il dettaglio compone: riepilogo con lo **scorporo della rivalsa**, righe,
  card accantonamento, card ripartizione, linea temporale, azioni, e tre
  fogli modali (avanzamento, cambio stato, ripartizione, registra entrata).
- `cliente_label()` — usata anche da `app.py` e `giroconto.py` — ritorna
  **testo grezzo**: chi lo stampa deve passarlo da `_esc()`.

> **Tre guardie che stanno negli endpoint, non nell'interfaccia:**
> 1. `PATCH /api/fatture/<fid>` rifiuta tutto ciò che non è bozza.
> 2. `PATCH .../stato` rifiuta di uscire da `incassata` se la ripartizione
>    è già stata fatta: resterebbero due movimenti sui conti senza un
>    incasso che li giustifichi.
> 3. Tornando indietro nel percorso si ripuliscono solo le date dei passi
>    **non più raggiunti**; quelle dei passi già attraversati restano.
>    Correggere un errore non deve falsificare la cronologia.
>
> `PATCH /api/fatture/<fid>` rifiuta anche di cambiare l'**anno** di una
> bozza già numerata: il numero lo incorpora, e cambiarlo qui lascerebbe un
> numero che mente (con rischio di doppioni). Meglio rifare la bozza.

### `fatture/fiscale.py` — 1.496 righe · calcolo fiscale, conto P.IVA, export

- HTML: `/situazione`, `/spese-piva`, `/spese-piva/nuova`,
  `/spese-piva/<mid>`, `/parametri`.
- JSON: `GET /api/situazione`, `GET /api/export/xlsx`,
  `GET|PATCH /api/parametri`, CRUD `/api/spese-piva[/<mid>]`.
- **`_situazione_data(sb, anno)` è il cuore**: mese per mese calcola
  imponibile, INPS, imposta, acconti, bollo, commercialista, netto di
  competenza, e le due scadenze. Chi ha bisogno di questi numeri lo chiama,
  non li ricalcola. Alias pubblico: `situazione_data()`.
- `saldo_piva(sb, al)` — **saldo reale del conto P.IVA** a una data:
  entrate − uscite − giroconti su tutti i movimenti fino a oggi, più la
  `rivalsa_incassata`. Diverso dal “movimento netto dell'anno” della pagina.
- `_build_workbook()` ricostruisce il foglio Excel di riferimento, con le
  formule vere dentro le celle (non i valori): resta un foglio che si può
  continuare a usare a mano.

> **Cose che sembrano sbagliate e non lo sono:**
> - L'imposta si calcola su `(imponibile − INPS)`: i contributi sono
>   deducibili.
> - L'acconto all'80 % vale **solo** per l'INPS; quello dell'imposta è il
>   100 % del saldo.
> - La situazione lavora sul **fatturato emesso** (parità con l'Excel),
>   l'accantonamento sull'**incassato** (base corretta del forfettario). La
>   pagina lo dichiara in un `<details>` apposta.
> - `rivalsa` è sommata a parte solo per trasparenza: è già dentro
>   `fatturato`/`totale`, non è un valore da aggiungere.

Le letture del conto P.IVA sono **paginate**: PostgREST tronca ogni
richiesta a un tetto (~1000 righe), e un saldo troncato sarebbe sbagliato
senza dare errore.

### `fatture/accantonamento.py` — 384 righe · quanto mettere da parte

Nessuna query: prende i parametri, restituisce numeri e HTML.

- `aliquote(param)`: le quote **sul lordo incassato** (INPS 17,47 %,
  imposta 2,48 %, dovuto 19,94 %, picco di cassa 36,39 %).
- `scomponi(lordo, param, …)`: la scomposizione completa più i quattro
  scenari — `minimo`, `consigliato`, `prudente`, `sicuro`.
- `card_html(s, …)`: la card con selettore di scenario, barra a segmenti e
  il `<details>` “Come esce questo numero”, dove compaiono le righe
  “di cui rivalsa INPS” e “di cui bollo addebitato”.
- `rivalsa` e `bollo_addebitato` **non entrano in nessun calcolo**: sono
  già dentro il lordo (concorrono al reddito — per il bollo vedi la
  Risposta AdE 428/2022). Servono solo a mostrarne la quota.

> L'ultimo segmento della barra (“Costi e margine”) è calcolato come
> `importi[scenario] − INPS − imposta`, non come `costi + margine`: per
> `prudente`/`sicuro` comprende anche la quota acconti, ed è esattamente
> così che lo ricalcola il JS quando si cambia scenario.

### `fatture/giroconto.py` — 352 righe · dall'incasso ai due conti

- `POST /api/fatture/<fid>/giroconto` esegue la ripartizione,
  `DELETE` la annulla.
- Scrive **due righe collegate**, e ne aggiunge una terza se serve:
  1. l'incasso lordo su `b2f_spese_piva` (`tipo=entrata`), *solo se non
     c'era già*: senza, il conto P.IVA finirebbe sotto della cifra spostata;
  2. l'uscita `tipo=giroconto` dal conto P.IVA;
  3. l'entrata sul conto personale, **via `spese/dati.py`** — mai a mano.
- `tipo=entrata` e non `giroconto` sul lato personale: `v_risparmi_mese`
  conta le entrate, e un movimento marcato altrimenti resterebbe fuori dal
  budget.
- **La quota accantonata non scende mai sotto la rivalsa INPS** della
  fattura: quella parte del corrispettivo è contributo previdenziale, non
  un tuo ricavo. Gli scenari la coprono tutti; un importo scritto a mano
  potrebbe scenderci sotto, e viene alzato (`alzato_alla_rivalsa: true`).
- Rollback esplicito a ogni passo: se il secondo inserimento fallisce si
  toglie il primo. Un giroconto monco svuoterebbe un conto verso il nulla.

### `fatture/emittente.py` — 220 righe · dati dell'intestazione

`GET /emittente`, `GET|PATCH /api/emittente` sulla riga unica
`b2f_emittente` (upsert su `id=1`). Sono i dati che compaiono in testa al
PDF: senza, l'intestazione esce col solo nome.

---

## `spese/` — il conto personale

### `spese/__init__.py` — 5 righe

Crea `spese_bp`; `views` importa gli altri.

### `spese/dati.py` — 649 righe · **l'unico posto che scrive su `spese`**

Livello dati del conto personale. Il resto dell'area (e `fatture/giroconto.py`)
passa da qui.

- Categorie: `voci_categoria`, `albero_categorie`, `link_categoria`.
- Movimenti: `movimenti()` (lista, **troncata a `limite`**),
  `righe_periodo()` (paginata, mai troncata), `totali_periodo()`,
  `movimento()`, `crea()`, `aggiorna()`, `elimina()`, `collegato()`.
- Saldi: `saldo_iniziale()` (dalla riga `impostazioni` con `valido_dal`
  più vecchia: è l'apertura, non l'ultima versione delle percentuali),
  `risparmio_totale()` (somma di `risparmi_periodo.effettivo_risparmio`) e
  `saldo_conto()` — apertura + movimenti − risparmio, paginato.
- Totali: `totali()`, `per_categoria()`.
- Risparmi: `periodi_risparmio()` (traduce i nomi con spazi e maiuscole
  della vista in chiavi normali), `risparmio_effettivo()`, `impostazioni()`.

> **Le tre regole della tabella `spese`**, e sono tutte trappole silenziose:
> 1. `mese` e `anno` sono NOT NULL senza default: vanno ricavati dalla data
>    a ogni scrittura, o l'insert fallisce.
> 2. La categoria non è un testo: è `categoria_link_id` →
>    `cfg_categoria_sottocategoria` (le coppie ammesse).
> 3. Gli id si assegnano col **primo libero** sotto lock, via la funzione
>    `insert_spesa_first_free_id` del database.
>
> **`movimenti()` non va usata per i totali di un periodo.** Tronca a 300, e
> su un anno pieno il saldo esce più basso del vero senza nessun errore:
> per i totali c'è `righe_periodo()`.
>
> `TIPI` non contiene più `giroconto` (migrazione README §8.9); `TIPI_SEGNO`
> sì, ma solo in **lettura**, per le righe storiche non ancora migrate.
>
> **Il risparmio non è una riga di `spese`.** Quello che registri sulla
> pagina Risparmi finisce su `risparmi_periodo` ed *esce* dal conto: è
> così che lo tratta `v_risparmi_mese` (`delta = … − effettivo_risparmio`),
> e così deve trattarlo chiunque calcoli il saldo. Chi somma solo entrate
> e uscite conta due volte tutto ciò che è stato risparmiato.

### `spese/views.py` — 181 righe · dashboard `/spese`

Saldo del conto oggi, saldo del mese, entrate/uscite, movimento netto
dell'anno, ultimi movimenti, quanto è arrivato dalla P.IVA.

> Il link “Vedi i giroconti” filtra per **categoria**, non per tipo: il
> giroconto dalla P.IVA è una riga `tipo=entrata`, e `tipo=giroconto` non
> esiste più — quel filtro dava una lista vuota.

### `spese/movimenti.py` — 648 righe · lista, form, API

- HTML: `/movimenti` (filtri anno, mese, tipo, categoria, sottocategoria,
  metodo, importo min/max, testo), `/movimenti/nuovo`, `/movimenti/<mid>`.
- JSON: `GET|POST /api/movimenti`, `PATCH|DELETE /api/movimenti/<mid>`,
  `GET /api/movimenti/dettaglio`, `GET /api/categorie`.
- I KPI e la ripartizione contano **tutto** il periodo filtrato
  (`righe_periodo`), la lista mostra le prime 300. Una sola query alimenta
  totali e ripartizione, così non possono disallinearsi.
- Ogni numero è cliccabile: apre “come viene calcolato” con l'elenco riga
  per riga e il totale, che **deve combaciare** col numero cliccato — per
  questo il drill-down usa un endpoint senza tetto.
- Con una categoria già filtrata la ripartizione scende di un livello (per
  sottocategoria): rifarla per categoria darebbe sempre “100 %, una riga”.
- La metà di un giroconto non si modifica né si cancella da qui: la guardia
  è nell'endpoint, non solo nel form.

### `spese/risparmi.py` — 326 righe · periodi e risparmio

`GET /risparmi`, `GET /api/risparmi`, `PATCH /api/risparmi`.

I periodi vanno da un bonifico al successivo — categoria *Stipendio* **o**
*Giroconto P.IVA*: da quando c'è la partita IVA il giroconto è lo stipendio
di fatto (migrazione README §8.7). Mostra consigliato, effettivo e la
differenza fra i due, che è l'unica cosa che conta guardare.

Mostra anche **quanto c'è davvero in ogni salvadanaio**: la somma delle
quote di tutti i periodi (il "dovrebbe") accanto ai saldi Revolut (il
"c'è"). Uno scarto non è di per sé un errore — dai salvadanai si preleva —
ma questo è l'unico posto in cui si vede.

> `risparmio_effettivo` a 0 è trattato come “non ancora registrato”: la
> vista fa `coalesce` a zero e non c'è modo di distinguere i due casi.

### `spese/revolut.py` — 769 righe · il terzo conto

Liquidità, risparmi e investimenti su Revolut. Esiste perché **è lì che
finisce il risparmio**: senza, quel denaro usciva dal conto personale
(`v_risparmi_mese` lo sottrae) e non entrava da nessuna parte.

- HTML: `/revolut` — saldi, import dell'estratto, editor dei salvadanai,
  storico degli snapshot.
- JSON: `GET|POST /api/revolut`, `POST /api/revolut/leggi` (multipart:
  legge il file e basta, non scrive).
- `parse_estratto(bytes, nome_file)`: legge l'estratto consolidato di
  Revolut. `saldo_revolut(client, al)`: l'ultimo snapshot a quella data.
  `coerenza(client, rev)`: il confronto fra risparmio dichiarato e saldo
  reale dei salvadanai.
- `SALVADANAI` tiene insieme i cinque secchielli e la quota di
  `impostazioni` che li alimenta. Gli alias servono perché lo stesso
  salvadanaio ha due nomi (“Fondo casa” da conto separato, “Casa” dentro
  il deposito).

> **L'estratto non è un xlsx**: è un CSV infilato in un foglio, tutto in
> colonna A, con virgole e virgolette dentro le celle — e il testo passato
> due volte per la codifica sbagliata (`€` → `â‚¬`). Si ricompone il testo
> e lo si rilegge come CSV; `_demojibake()` disfa la codifica provando
> cp1252 prima di latin-1, perché è lì che sta l'euro.
>
> **Due cose l'estratto non le contiene**, e l'app lo dice invece di
> inventarle: il valore del portafoglio investimenti (ci sono solo i
> redditi del periodo) e la ripartizione dei salvadanai (dal 15 aprile
> 2026 stanno in un unico deposito, di cui si sa solo il totale).
>
> È uno **snapshot con una data**, non un saldo dal vivo. Ogni risposta
> porta `data` e `giorni`: un saldo di tre mesi fa non è sbagliato, è
> vecchio, e chi lo guarda deve poterlo distinguere.

Richiede la tabella `b2f_revolut` — migrazione README §8.10.

### `spese/importa.py` — 435 righe · import da estratto conto

`GET /importa`, `POST /api/importa/carica`, `POST /api/importa/salva`.

Due passi, **niente scritto finché non confermi**: si carica l'xlsx
(openpyxl, colonne Data Contabile / Importo / Causale), si rivedono le
righe assegnando categoria una per una o in blocco, poi si salva solo il
selezionato. `clean_bank_description()` ripulisce le causali bancarie
(pagamenti con carta, bonifici, SDD) con la stessa euristica del vecchio
client desktop.

---

## `shared/` — pezzi comuni

### `shared/design.py` — 871 righe · il design system

- `FONT_FILES` + `_FONT_FACES`: Instrument Serif e Inter, **ospitati
  dall'app** (niente CDN: funziona anche offline).
- `CSS`: token (colori, spazi, raggi, ombre, durate) per tema chiaro/scuro
  × quattro accenti, poi i componenti — card, stat, list, table, chip,
  notice, sheet, toast, meter, bar-split, explain, rail, tabbar, fab.
- `ICONS` + `icon(name)`: SVG inline, nessuna icon font.

> Le pagine usano **le classi**, mai colori inline. I contrasti di ogni
> combinazione sono verificati da `tools/verifica_contrasti.py`.
> `.rows .v` è pensato per un numero su riga singola (`white-space:nowrap`):
> il testo che va a capo sta in `.sub`.

### `shared/theme.py` — 1.019 righe · scheletro di pagina e home

- `page_head(title, prefetch)`: `<head>` completo. Il bootstrap del tema
  gira **prima del primo paint**, altrimenti si vede il lampo bianco.
- `app_shell(...)` / `render_page(...)`: sidebar (≥1024px), topbar, breadcrumb,
  contenuto, tab bar (mobile), pannello Aspetto, gate PIN.
- `render_launchpad(greet_name, dati)`: la home. `_blocco_saldi()` mette in
  cima **i due conti ad oggi**, con la scomposizione in un `<details>`.
- `locked_shell()`: la stessa shell a corpo vuoto, servita da `_gate()` al
  posto di una pagina protetta. Nessun dato nel markup.
- `inject_app_header(page_html, …)`: avvolge il markup del timesheet nella
  shell senza toccarne la logica (sostituisce `<div class="wrap">`).
- `_PIN_GATE`: overlay di sblocco, iniettato in ogni pagina. Intercetta
  anche le `fetch` che rispondono 401 e si riapre.

### `shared/fmt.py` — 74 righe · formattatori italiani

`eur`, `eur_segno`, `pct`, `data_it`, `data_breve`, `mese_anno`.
Erano duplicati in tre file con tre implementazioni diverse. **Non
riscriverli altrove.**

### `shared/pdfgen.py` — 400 righe · il facsimile PDF

`pdf_script(emittente)` ritorna il tag `<script>` che espone
`window.b2fRenderInvoicePDF(payload)`. Il PDF si genera **nel browser**
(jsPDF, ospitata dall'app in `static/vendor/`).

> Il documento **non è la fattura elettronica**: si intitola FACSIMILE, lo
> ripete in calce e dice chi trasmette allo SDI. La rivalsa non compare
> come riga aggiuntiva — è scorporata, aggiungerla in fondo farebbe
> sembrare che il totale cresca — ma nel blocco totali come
> “di cui compenso” / “di cui rivalsa INPS”: sono le due voci che servono
> allo studio per `DettaglioLinee` e `DatiCassaPrevidenziale`.
> Chi lo modifica esegua `tools/verifica_facsimile.py`.

### `shared/supabase_client.py` — 31 righe

`get_client()` (memoizzato) e `is_configured()`. Senza le env vars
ritornano `None`/`False`: le pagine mostrano un avviso e le API rispondono
503, invece di andare in errore.

### `shared/webauthn.py` — 247 righe · sblocco biometrico

Blueprint su `/api/webauthn`: `status`, `register/begin`,
`register/complete`, `auth/begin`, `auth/complete`.

Le challenge stanno in un dict a livello modulo con TTL 5 minuti, non in
sessione: nel cookie firmato rischierebbero di sforare il limite. Funziona
perché l'app è a utente singolo con **un solo worker**.

---

## `tools/` — utilità di sviluppo, non servono in produzione

### `tools/preview.py` — 414 righe

Monta l'app con un **finto client Supabase** (`_FakeClient`, che riproduce
solo la parte di API usata dall'app) e dati realistici di agosto 2026:
emittente, parametri, 4 clienti, 7 fatture nei vari stati, movimenti P.IVA,
movimenti personali con `v_spese` e `impostazioni`.

    python tools/preview.py [porta]     # default 5055

È la base degli altri tre strumenti.

### `tools/verifica_layout.py` — 124 righe

Playwright: cerca overflow orizzontali su 8 pagine × 4 larghezze di
telefono (320/360/390/430). Un overflow manda in shrink-to-fit **l'intera
pagina** sui browser mobili — è quello che fa sembrare l'app non adattiva.
Elenca gli elementi colpevoli, non solo il fatto.

### `tools/verifica_contrasti.py` — 148 righe

Estrae i colori da `shared/design.py` e verifica i contrasti WCAG (4,5:1
testo normale, 3:1 testo grande e bordi) su tutte le combinazioni
tema × accento. Non serve il browser.

### `tools/verifica_facsimile.py` — 125 righe

Genera il PDF con un browser vero e ne rilegge il testo (pypdf),
controllando che ci sia quello che deve (le diciture di legge, lo scorporo,
l'IBAN) e che **non** ci sia quello che non deve (il totale con la rivalsa
addebitata, la jsPDF da CDN).

---

## `static/` e `docs/`

| File | Cosa |
|---|---|
| `static/fonts/*.woff2` | Instrument Serif (normale, corsivo) e Inter |
| `static/vendor/jspdf.umd.min.js` | jsPDF 2.5.1 (MIT), ospitata: il facsimile non può dipendere da un CDN |
| `docs/schema_supabase.md` | Foto dello schema reale — colonne, vincoli, indici, viste, funzioni, trigger, RLS. **Va rigenerata dopo ogni migrazione** con la query del README §8.5 |
| `docs/MAPPA.md` | questo file |

---

## Cose che valgono ovunque

- **Le pagine sono f-string in Python.** Le graffe letterali (CSS, JS) si
  raddoppiano: `{{` e `}}`.
- **Il testo libero va escapato.** Ogni modulo ha il suo `_esc()`; quello
  che finisce dentro un blob JSON in pagina ha anche `<` → `<`.
- **Le guardie stanno negli endpoint**, non solo nell'interfaccia:
  nascondere un pulsante non impedisce di chiamare l'API.
- **I commenti spiegano il perché**, non il cosa.
- **Serve Python 3.12**: `fatture/accantonamento.py` usa f-string annidate
  con lo stesso tipo di virgolette (PEP 701), che su 3.11 non compilano.
