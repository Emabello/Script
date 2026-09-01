# B2F Hub

Gestionale personale per una partita IVA in regime forfettario, con tre aree:
le **ore** lavorate, le **fatture** (con la parte fiscale) e le **spese**
personali. Gira su Flask, tiene i dati su Supabase, sta online su Render.

Il filo che tiene insieme tutto è il denaro: le ore diventano una fattura, la
fattura incassata finisce sul conto P.IVA, una parte va accantonata per il
fisco, il resto si sposta sul conto personale e quello che avanza a fine mese
finisce nei salvadanai su Revolut. L'app segue questo percorso per intero, e
in ogni passaggio il denaro esce da un conto ed entra in un altro — mai
sparisce, mai si duplica.

---

## Indice

1. [Come è fatta](#1-come-è-fatta)
2. [Le tre aree](#2-le-tre-aree)
3. [Il modello dei dati](#3-il-modello-dei-dati)
4. [La logica fiscale](#4-la-logica-fiscale)
5. [Accantonamento e ripartizione](#5-accantonamento-e-ripartizione)
6. [Il ciclo di vita della fattura](#6-il-ciclo-di-vita-della-fattura)
7. [Le trappole del database](#7-le-trappole-del-database)
8. [Migrazioni da eseguire](#8-migrazioni-da-eseguire)
9. [Sicurezza](#9-sicurezza)
10. [Configurazione e deploy](#10-configurazione-e-deploy)
11. [Sviluppo](#11-sviluppo)

---

## 1. Come è fatta

```
app.py                 entry point: monta i blueprint sulla app di xs_server
xs_server.py           timesheet (l'app originale), ora servito su /ore
xs_client.py           client del portale ore esterno

fatture/               area fatturazione e fisco
  views.py               landing
  clienti.py             anagrafica clienti
  editor.py              compilazione e modifica del facsimile
  storico.py             elenco e dettaglio fattura, cambi di stato
  fiscale.py             situazione fiscale, movimenti P.IVA, parametri, export Excel
  accantonamento.py      quanto mettere da parte di un incasso
  giroconto.py           ripartizione dell'incasso fra i due conti
  emittente.py           dati che compaiono in testa ai documenti
  costanti.py            stati, categorie, scorporo della rivalsa

spese/                 area conto personale
  views.py               dashboard
  dati.py                accesso ai dati (l'unico posto che scrive su `spese`)
  movimenti.py           elenco, form, API dei movimenti
  risparmi.py            periodi di stipendio e risparmio
  revolut.py             il terzo conto: liquidita', risparmi, investimenti
  importa.py             import dei movimenti da estratto conto bancario

shared/                pezzi comuni
  design.py              design system: token, CSS, icone
  theme.py               scheletro di pagina, navigazione, tema chiaro/scuro
  caricamento.py         la tenda mosaico: schermata d'attesa e service worker
  fmt.py                 formattatori italiani (euro, percentuali, date)
  pdfgen.py              generazione del facsimile PDF (jsPDF nel browser)
  supabase_client.py     client Supabase
  webauthn.py            sblocco biometrico

tools/                 utilità di sviluppo (non servono in produzione)
static/                font e jsPDF ospitati dall'app
```

Le pagine sono HTML generato da Python: niente framework frontend, niente
build. Il JavaScript è quello che serve nella pagina, scritto inline.

**Per sapere cosa c'è dentro un singolo file** — rotte, funzioni pubbliche,
trappole — c'è [`docs/MAPPA.md`](docs/MAPPA.md): una scheda per file, con
un indice "ti serve X → guarda Y". Questo README spiega il *perché* del
dominio, la mappa spiega il *dove*.

---

## 2. Le tre aree

### Home — `/`

In cima ci sono **i tre conti, ad oggi**, più il totale. È un numero che
nessun'altra pagina dava — `/spese` mostrava il saldo del mese e
`/fatture/spese-piva` quello dell'anno filtrato, e nessuno dei due è
"quanto ho in banca".

| Conto | Come si calcola | Chi lo calcola |
|---|---|---|
| P.IVA | entrate − uscite − giroconti al personale, su tutti i movimenti fino a oggi | `fatture/fiscale.py::saldo_piva` |
| Personale | apertura (`impostazioni`, riga con `valido_dal` più vecchia) + entrate − uscite, **sui soli movimenti successivi alla data dell'apertura** | `spese/dati.py::saldo_conto` |
| Revolut | l'ultimo snapshot registrato: liquidità + risparmi + investimenti | `spese/revolut.py::saldo_revolut` |

**Il denaro non si crea né sparisce fra un conto e l'altro**, e i saldi lo
rispettano: il giroconto è un'uscita dal conto P.IVA e un'entrata sul
personale; il risparmio è un'uscita dal personale e un'entrata su Revolut.
In entrambi i casi il totale non cambia.

Sotto ai numeri, un "come si formano questi saldi" apre la scomposizione —
un saldo di cui non si vede la formazione non è verificabile.

P.IVA e personale si calcolano dai movimenti, con letture **paginate**:
PostgREST tronca ogni richiesta a un tetto (~1000 righe) e `spese` ne ha
già di più, e una select secca darebbe un saldo più basso del vero senza
nessun errore visibile. Revolut invece è uno snapshot dall'estratto conto,
con la sua data.

Il resto della home: incassato del mese, quanto accantonare, saldo del mese
del conto personale, fatture dell'anno, prossime scadenze, ultime fatture e
ultimi movimenti.

### Ore — `/ore`

Il timesheet originale (`xs_server.py`), che parla con un portale esterno
tramite `xs_client.py`. È rimasto com'era: la hub gli inietta soltanto
l'intestazione — più il ponte verso le fatture, che è nuovo e sta in
[§ 6.1](#61--il-mese-di-ore-e-la-fattura-che-lo-racconta).

### Fatture — `/fatture`

| Rotta | Cosa fa |
|---|---|
| `/fatture` | landing con i contatori |
| `/fatture/nuova` | compila un nuovo documento |
| `/fatture/<id>` | dettaglio: righe, stato, ripartizione, azioni |
| `/fatture/<id>/modifica` | modifica, solo finché è in bozza |
| `/fatture/storico` | elenco per anno e stato |
| `/fatture/clienti` | anagrafica |
| `/fatture/situazione` | situazione fiscale dell'anno |
| `/fatture/spese-piva` | movimenti del conto P.IVA: saldo del conto oggi, movimento netto dell'anno, rivalsa incassata |
| `/fatture/parametri` | aliquote, coefficiente, accantonamento |
| `/fatture/emittente` | dati dell'intestazione |

**Il documento prodotto non è la fattura elettronica.** È il *facsimile* che
va allo studio, che poi predispone e trasmette l'XML allo SDI. Per questo il
PDF si intitola FACSIMILE e lo dichiara in calce.

### Spese — `/spese`

| Rotta | Cosa fa |
|---|---|
| `/spese` | dashboard: saldo del conto oggi, saldo del mese, ultimi movimenti, quanto è arrivato dalla P.IVA |
| `/spese/movimenti` | elenco con filtri per anno, mese, tipo, categoria, testo |
| `/spese/movimenti/nuovo` | nuovo movimento |
| `/spese/movimenti/<id>` | modifica |
| `/spese/risparmi` | periodi di stipendio, risparmio consigliato ed effettivo, e quanto c'è davvero in ogni salvadanaio |
| `/spese/revolut` | saldi Revolut: liquidità, risparmi, investimenti |
| `/spese/importa` | import dei movimenti da estratto conto bancario |

API JSON: `/spese/api/movimenti` (GET, POST, PATCH, DELETE),
`/spese/api/categorie`, `/spese/api/risparmi` (GET, PATCH).

### Revolut — `/spese/revolut`

Il terzo conto: liquidità, risparmi e investimenti. Non è una sezione a
parte per capriccio — **è dove finisce il risparmio**, e senza di lei
quel denaro usciva da un conto senza entrare in nessuno.

I numeri arrivano dall'**estratto conto consolidato** che Revolut esporta
in .xlsx (Menu → Estratti conto → Consolidato). Si carica, l'app legge i
saldi di chiusura e li mostra, e si salva — niente viene scritto prima
della conferma. Due cose l'estratto non le contiene e vanno scritte a mano:

- **il valore del portafoglio investimenti.** L'estratto dà dividendi,
  vendite e PnL del periodo, nessuna valorizzazione delle posizioni.
- **la ripartizione dei salvadanai.** Dal 15 aprile 2026 vivono dentro un
  unico "Deposito senza vincoli" e l'estratto ne dà solo il totale.

È uno **snapshot con una data**, non un saldo dal vivo: l'app mostra
sempre a quando risale, e da 45 giorni in su lo segnala.

API JSON: `/spese/api/revolut` (GET, POST), `/spese/api/revolut/leggi`
(POST multipart, legge e basta).

#### Il risparmio è un movimento come gli altri

Un bonifico verso i salvadanai è un'uscita dal conto: una riga di `spese`
con categoria **Risparmi** e la data vera del bonifico. Niente di
speciale, ed è il punto.

Fino ad agosto 2026 non era così: quel denaro usciva dal saldo tramite
`risparmi_periodo`, un numero digitato a mano al posto del movimento
bancario. Le due strade convivevano — alcuni bonifici erano registrati
come uscite, altri solo dichiarati, qualcuno **tutti e due**, qualcuno
**nessuno dei due** — e niente diceva quale valesse per quale. In
diciotto mesi lo scarto contro l'estratto era arrivato a **829,78 €**, in
due direzioni opposte che si mascheravano a vicenda: nessun errore
visibile, nessuna riga rossa, solo un numero plausibile e sbagliato.

La regola che chiude il buco per costruzione:

> **Il saldo di un conto si calcola solo dai movimenti di quel conto.**
> Ogni euro che esce lascia una riga. Nessuna eccezione, nessun termine
> correttivo, nessuna dichiarazione a mano.

`risparmi_periodo` resta quello che è davvero — il *quanto volevo mettere
via* di ogni periodo, che la pagina Risparmi confronta con quanto è
uscito davvero — e non tocca più nessun saldo. `v_risparmi_mese` legge il
risparmio effettivo dai movimenti (uscite categoria Risparmi meno i
rientri), ed esclude quelle uscite da "Totale Speso": mettere da parte
non è spendere.

Vedi [§ 8.11](#811--i-risparmi-diventano-movimenti-veri-necessaria).

#### I salvadanai sono già le categorie dell'app

| Salvadanaio Revolut | Quota in `impostazioni` |
|---|---|
| Emergenze | `perc_fondo_emergenze` |
| Fondo casa (dentro il deposito: "Casa") | `perc_fondo_casa` |
| Vacanze | `perc_viaggi` |
| Regali | `perc_regali` |
| Altro | `perc_altro` |

Da qui il confronto che prima non esisteva: la pagina Risparmi calcola
quanto *dovrebbe* esserci in ogni secchiello (somma delle quote di tutti i
periodi), Revolut sa quanto c'è. E sul totale, `/spese/revolut` confronta
il risparmio dichiarato con il saldo reale dei salvadanai: sono due misure
indipendenti della stessa cosa, e se divergono uno dei due numeri è
sbagliato — non c'è nessun altro punto in cui la cosa verrebbe fuori.

---

## 3. Il modello dei dati

### Tabelle dell'app

| Tabella | Contenuto |
|---|---|
| `b2f_emittente` | riga unica: i tuoi dati, più nome e mail dello studio |
| `b2f_clienti` | anagrafica clienti |
| `b2f_fatture` | i documenti, con stato, date dei passaggi, ripartizione e il mese di ore che raccontano — [§ 8.13](#813--la-fattura-si-ricorda-di-quali-ore-è-fatta-necessaria) |
| `b2f_spese_piva` | movimenti del conto P.IVA |
| `b2f_parametri_fiscali` | riga unica: aliquote, parametri di accantonamento e tariffa giornaliera — [§ 8.14](#814--la-tariffa-giornaliera-è-un-parametro-non-una-costante-necessaria) |
| `b2f_revolut` | saldi Revolut, uno snapshot per data — [§ 8.10](#810--tabella-dei-saldi-revolut) |
| `b2f_webauthn_credentials` | credenziali dello sblocco biometrico |

### Tabelle del conto personale (preesistenti all'app)

| Tabella | Contenuto |
|---|---|
| `spese` | i movimenti personali |
| `cfg_categorie` · `cfg_sottocategorie` | le voci |
| `cfg_categoria_sottocategoria` | gli accoppiamenti ammessi fra le due |
| `impostazioni` | saldo iniziale, percentuale di risparmio, quote di destinazione |
| `risparmi_periodo` | **non più una fonte per nessun calcolo**: dopo la [§ 8.11](#811--i-risparmi-diventano-movimenti-veri-necessaria) il risparmio è un'uscita di `spese`, categoria *Risparmi* |

### Viste

| Vista | Cosa calcola |
|---|---|
| `v_spese` | i movimenti personali con i nomi di categoria e sottocategoria |
| `v_periodi_stipendio` | i periodi, delimitati dalle entrate di categoria *Stipendio* |
| `v_risparmi_mese` | per ogni periodo: entrate, uscite, resto, risparmio consigliato |
| `v_situazione_annuale` | riepilogo fiscale mensile |

### Funzioni

- `b2f_next_progressivo(anno)` — il prossimo numero di fattura dell'anno.
- `insert_spesa_first_free_id(...)` — inserisce un movimento personale
  assegnando il **primo id libero** sotto advisory lock. È il modo con cui
  quella tabella ha sempre numerato le righe, e l'app lo rispetta.

---

## 4. La logica fiscale

Regime forfettario, per cassa: le imposte maturano **quando incassi**, non
quando emetti.

Su un incasso lordo `L`:

```
Imponibile   I = L × coeff_ateco             (0,67)
INPS         C = I × aliquota_inps           (26,07 %)
Imposta      T = (I − C) × aliquota_imposta  (5 %)
```

**L'imposta si calcola su `I − C`, non su `I`**: i contributi previdenziali
sono deducibili. Vale ovunque — dashboard, export Excel, `v_situazione_annuale`.

Con i parametri di default, in percentuale sul lordo:

| Voce | Quota |
|---|---|
| INPS | 17,47 % |
| Imposta | 2,48 % |
| **Dovuto** | **19,94 %** |

### Scadenze

- **30 giugno** — saldo imposta + saldo INPS + commercialista + bollo
- **30 novembre** — acconto imposta (100 % del saldo) + acconto INPS (80 %)

L'acconto all'80 % col metodo storico vale **solo** per l'INPS. Quello
dell'imposta sostitutiva è pari al 100 % del saldo.

### Rivalsa INPS

La rivalsa del 4 % si **scorpora** dal corrispettivo concordato, non si
aggiunge sopra:

```
Corrispettivo concordato  5.000,00   ← quello che il cliente paga
  di cui compenso         4.807,69   = 5.000 / 1,04
  di cui rivalsa INPS 4 %   192,31   = 5.000 − compenso
```

Il totale non cambia: è il compenso a ridursi. Nell'accantonamento la rivalsa
non sposta nulla, perché nel forfettario l'imponibile è il corrispettivo
intero: è una suddivisione che serve alla fattura elettronica.

**Verificato il 2026-08-12** contro la normativa aggiornata (non è scontato:
è diverso dal contributo integrativo delle Casse professionali, che invece
*è* escluso): la rivalsa INPS facoltativa (art. 1 co. 212 L. 662/1996)
concorre per intero al reddito imponibile forfettario, alla base di
imposta sostitutiva e INPS, e al limite degli € 85.000. Non va mai
sottratta prima di calcolare percentuali o scaglioni — dove succede oggi
(`fatture/accantonamento.py`, `fatture/fiscale.py`) è corretto così.
Fonti: [Fiscozen](https://www.fiscozen.it/guide/rivalsa-inps-regime-forfettario-reddito/),
[Fiscomania](https://fiscomania.com/rivalsa-inps/).

Resta comunque **mostrata a parte** ovunque compaia: non cambia il calcolo,
ma senza quella riga la sua quota resta invisibile dentro un unico numero.

| Dove | Cosa si vede |
|---|---|
| Dettaglio fattura, riepilogo | chip `Rivalsa INPS € …` accanto allo stato, e le righe "di cui compenso" / "di cui rivalsa INPS 4 %" |
| Dettaglio fattura, accantonamento | riga "di cui rivalsa INPS" in "Come esce questo numero" |
| Dettaglio fattura, ripartizione | "di cui rivalsa INPS — resta sul conto P.IVA", sia prima di ripartire sia dopo |
| Movimenti P.IVA | card *Rivalsa INPS incassata*: quanta parte del saldo è rivalsa, e perché non va accantonata due volte |
| Home | riga "di cui rivalsa INPS" nella scomposizione del saldo P.IVA |
| Movimento del giroconto | l'importo è scritto nelle note della riga |
| Excel della situazione | colonna "di cui Rivalsa INPS" |

**E resta sul conto P.IVA.** Non è un tuo ricavo: è il contributo
previdenziale che il cliente ti gira perché tu lo versi. I quattro scenari
di accantonamento la coprono tutti abbondantemente — l'INPS
sull'accantonamento vale il 17,47 % del lordo, la rivalsa il 3,85 % — ma la
ripartizione ha comunque un **pavimento esplicito alla rivalsa**
(`fatture/giroconto.py::calcola`): un importo scritto a mano che ci
scendesse sotto viene alzato, altrimenti si sposterebbe sul conto personale
denaro già destinato all'INPS. Accantonarla una seconda volta, invece,
sarebbe accantonare due volte lo stesso denaro.

### Bollo

Dovuto sopra i 77,47 €, importo 2,00 €. Può essere addebitato al cliente
oppure restare a carico dell'emittente.

**Se addebitato al cliente**, i 2 € smettono di essere un semplice
rimborso: la Risposta a interpello Agenzia delle Entrate n. 428/2022 ha
chiarito che assumono natura di compenso e concorrono al reddito, alla
base INPS e al limite di € 85.000 — esattamente come la rivalsa. Se
resta a carico dell'emittente (come nelle due fatture emesse finora),
non genera alcun reddito: è solo una spesa registrata su Spese P.IVA
(categoria "Bollo pagato").

---

## 5. Accantonamento e ripartizione

### Il problema

Quando incassi, i soldi arrivano tutti sul conto P.IVA ma non sono tutti tuoi.
Il conto matematico (19,94 %) però non è una buona guida, per due motivi:

1. **Gli acconti.** Il saldo dell'anno N si paga a giugno N+1, ma nello stesso
   anno si versano anche gli acconti per N+1. A regime si scomputano, ma
   nell'anno in cui le due cose cadono insieme il fabbisogno è
   `1,8 C + 2 T = 36,39 %` del lordo.
2. **I costi fissi.** Commercialista, PEC, bolli, commissioni: non sono tasse,
   ma escono dagli stessi soldi.

### I quattro scenari

| Scenario | Formula | Quota | Su 5.000 € |
|---|---|---|---|
| Minimo | `C + T` | 19,9 % | € 997,17 |
| Consigliato | `minimo × (1+margine) + costi` | 21,9 % | € 1.096,89 |
| Prudente | `dovuto + metà acconti + costi + margine` | 30,2 % | € 1.508,15 |
| Sicuro | `1,8C + 2T + costi` | 36,4 % | € 1.819,69 |

*Prudente* esiste perché fra Consigliato e Sicuro c'era un salto troppo grande:
copre il dovuto più metà degli acconti, così al fabbisogno dell'anno-picco ci
si arriva in due anni invece che in uno.

Margine di sicurezza, costi fissi annui e fatturato atteso si cambiano in
`/fatture/parametri`.

### La ripartizione

Sul dettaglio di una fattura **incassata** compare *Ripartizione dell'incasso*.
Si sceglie uno scenario e l'app scrive **due movimenti collegati**:

```
incasso lordo sul conto P.IVA        5.000,00
  − accantonamento (scenario)        1.508,15   resta sul conto P.IVA
  = giroconto al personale           3.491,85   si sposta
```

| Dove | Riga scritta |
|---|---|
| `b2f_spese_piva` | `tipo=giroconto`, categoria `giroconto_personale` → esce dal conto P.IVA |
| `spese` | `tipo=entrata`, categoria *Giroconto P.IVA* → arriva sul conto personale |

Sulla fattura restano scenario, quota accantonata, quota spostata, data e gli
id dei due movimenti.

**Le garanzie:**

- la quota accantonata non scende mai sotto la **rivalsa INPS** della
  fattura (vedi [§ 4](#rivalsa-inps));
- si può fare solo a incasso avvenuto, e una volta sola;
- se il secondo inserimento fallisce il primo viene tolto (niente spostamenti
  monchi);
- il movimento personale nato da un giroconto non si può cancellare da
  `/spese`: va annullata la ripartizione dalla fattura, così spariscono
  entrambe le righe;
- una fattura già ripartita non può uscire dallo stato *incassata* senza prima
  annullare la ripartizione.

Il giroconto **non è una spesa deducibile né un ricavo**: è denaro che cambia
conto. Per questo sul lato P.IVA usa `tipo=giroconto`, che i calcoli fiscali
ignorano, e viene sottratto dal saldo dei movimenti P.IVA.

### Il giroconto manuale

Non tutti gli spostamenti nascono da una fattura incassata: da
`/fatture/spese-piva/nuova` si può registrare un giroconto anche a mano,
scegliendo `tipo=giroconto`. Succede la stessa cosa della ripartizione, solo
innescata da qui invece che dall'incasso: l'app scrive anche la riga gemella
su `spese` (`tipo=entrata`, categoria *Giroconto P.IVA*), collegata tramite
`b2f_spese_piva.giroconto_personale_id` — vedi [§ 8.4](#84--collegamento-dei-giroconti-manuali).

Le stesse garanzie della ripartizione automatica valgono qui: se il secondo
inserimento fallisce il primo viene tolto; il movimento su `spese` non si
cancella da `/spese`, va eliminato il movimento P.IVA che lo ha generato,
così spariscono entrambe le righe; da `/fatture/spese-piva` tipo e importo di
un giroconto (manuale o da fattura) non si possono più cambiare una volta
registrato, per non disallineare i due conti — va eliminato e rifatto.

### La procedura di fine periodo

Il giroconto porta il denaro **sul** conto personale. La domanda subito
dopo è quanta parte di quel denaro non deve restarci: è il risparmio, e
`/spese/risparmi` la trasforma in una procedura di due passi, nell'ordine
in cui il denaro si muove davvero.

1. **L'incasso è arrivato sul personale?** Se ci sono fatture già
   incassate il cui denaro sta ancora sul conto P.IVA, la procedura le
   elenca con il link e chiede di ripartirle prima. Non è un vincolo, è
   un ordine di grandezza: la quota si applica a quel che resta sul conto
   personale, e finché l'incasso non è arrivato lì quel numero è più
   basso del vero.
2. **Quanto ne metti via.** Il consigliato è la percentuale di
   `impostazioni` applicata a quel che resta nel periodo — lo stesso
   numero della colonna *Risparmio consigliato* di `v_risparmi_mese`. Si
   può correggere, e mentre lo si scrive l'anteprima mostra quanto
   finisce in ciascuno dei cinque salvadanai. Alla conferma l'app
   registra **un'uscita vera** dal conto personale, categoria *Risparmi*,
   con la data del bonifico.

Il bonifico lo fai tu dalla banca: l'app registra che è successo, non
sposta denaro. Sembra una sfumatura e non lo è — è la differenza fra un
saldo che segue la banca e uno che la anticipa.

**Un movimento solo, non cinque.** La banca vede un bonifico; la
ripartizione fra i secchielli è un calcolo, e `v_risparmi_mese` lo rifà
per ogni periodo dalle percentuali di `impostazioni`. Cinque righe
darebbero cinque movimenti che sull'estratto non esistono, e la
riconciliazione riga per riga tornerebbe a non tornare.

**Perché non c'è più il campo "Risparmio effettivo".** C'era, e scriveva
un numero su `risparmi_periodo` **al posto** del movimento bancario: è la
seconda strada che la [§ 8.11](#811--i-risparmi-diventano-movimenti-veri-necessaria)
ha chiuso dopo che era costata 829,78 € di scarto in diciotto mesi. Da
allora `v_risparmi_mese` calcola l'effettivo dai movimenti e quella
colonna non entra in nessun conto: continuare ad accettarla vorrebbe dire
scrivere dove nessuno guarda, che è peggio di un errore — sembra
funzionare. `PATCH /spese/api/risparmi` risponde 409 e dice dove andare.

**L'avviso in home** compare solo quando c'è davvero qualcosa da fare: un
periodo aperto, un consigliato sopra zero e nessuna uscita verso i
salvadanai dentro quel periodo. Porta la cifra, non un "ricordati di
risparmiare": un avviso senza il numero costringe ad aprire la pagina per
sapere se vale la pena aprirla, e in un mese non lo legge più nessuno.

---

## 6. Il ciclo di vita della fattura

```
bozza → inviata_studio → trasmessa_sdi → incassata
                                              ↘ annullata
```

| Stato | Significato |
|---|---|
| `bozza` | in lavorazione, solo tua. Modificabile ed eliminabile |
| `inviata_studio` | il facsimile è dallo studio. Da qui **niente più modifiche** |
| `trasmessa_sdi` | lo studio ha trasmesso la fattura elettronica |
| `incassata` | il denaro è arrivato: fa scattare l'accantonamento |
| `annullata` | fuori dal giro, non concorre ai calcoli |

Concorrono al fatturato solo `inviata_studio`, `trasmessa_sdi` e `incassata`.

Oltre la bozza il documento non è più modificabile: correggerlo qui lo farebbe
divergere dalla fattura vera senza che nessuno se ne accorga. Tornando indietro
lungo il percorso, le date dei passi non più raggiunti vengono ripulite, ma
quelle dei passi già attraversati restano: correggere un errore non deve
falsificare la cronologia.

### 6.1 — Il mese di ore e la fattura che lo racconta

Le ore stanno sul portale XS, le fatture su Supabase, e per un anno
l'unico ponte fra i due è stato ricopiare "20 giornate" a mano. Ora il
ponte è doppio, e va nei due versi.

**Dal timesheet alla fattura.** Nel riepilogo del mese (`/ore`, bottone
"Riepilogo mese") c'è il blocco *Fattura*: dice quante giornate da 8 ore
fanno i minuti del mese e apre l'editor già compilato — **una riga sola**,
giornate × `tariffa_giornaliera`. Se quel mese è già stato fatturato lo
dice prima, col link alla fattura che esiste: due fatture sullo stesso
periodo non danno nessun errore, si scoprono a fine anno e una va
cancellata a mano.

Una riga sola e non una per cliente, ed è una scelta: la fattura la emetti
a **un** cliente — quello che ti paga — mentre i clienti finali del lavoro
sono informazione tua. Una riga per ciascuno finirebbe stampata sul PDF
che il cliente legge.

**Dalla fattura al timesheet.** In fondo al dettaglio della fattura c'è la
card *Ore fatturate*: giornate, ore, giorni lavorati, la ripartizione per
cliente, e il link che apre `/ore` direttamente sul riepilogo di quel mese.

Quello che la fattura si porta dietro è una **foto**, non una lettura dal
vivo (`ore_snapshot`, [§ 8.13](#813--la-fattura-si-ricorda-di-quali-ore-è-fatta-necessaria)),
per due motivi che vale la pena tenere a mente prima di "ottimizzare"
sostituendola con una query:

- il portale si legge **un giorno alla volta**: un mese sono una trentina
  di richieste HTTP, troppe per aprire una pagina — per questo la lettura
  sta sempre dietro a un bottone;
- fra due anni quel mese sul portale potrebbe non esserci più. La fattura
  invece resta, e deve continuare a saper dire di cosa era fatta.

La foto porta la data in cui è stata scattata, e un bottone la rilegge.
Una foto senza data si legge come un dato dal vivo: è lo stesso errore che
la tessera Revolut ha già fatto una volta.

**La giornata è 8 ore**, e si conta sul totale dei minuti del mese, non
sui giorni in cui hai timbrato: due mezze giornate sono una giornata da
fatturare. È la stessa definizione che il riepilogo del timesheet mostra
come "giorni pieni da 8h" — se cambia lì, cambia in `shared/ore.py`.

---

## 7. Le trappole del database

Cose che non si vedono dallo schema ma fanno danni silenziosi.

### `spese.mese` e `spese.anno` sono NOT NULL senza default

Sono ridondanti rispetto a `data`, ma le viste ci si appoggiano. Vanno ricavati
dalla data a ogni scrittura, o l'insert fallisce. Se ne occupa `spese/dati.py`:
**è l'unico posto che scrive su quella tabella**, apposta.

### La categoria non è un testo

`spese.categoria_link_id` rimanda a `cfg_categoria_sottocategoria`, che tiene le
coppie valide. Una categoria senza sottocategoria ha comunque la sua riga, con
`sottocategoria_id` a NULL.

### Un movimento senza categoria sparisce dal budget

`v_risparmi_mese` somma le altre entrate con:

```sql
tipo = 'entrata' and categoria not in ('Stipendio', 'Giroconto P.IVA')
```

Su una riga **senza categoria** quel confronto non è falso: è `NULL`. Il
movimento non entra né fra le entrate contate né fra le escluse — sparisce. Il
denaro risulterebbe sul conto ma il *Risparmio consigliato* verrebbe calcolato
su una base più bassa del vero, senza alcun errore visibile.

Per questo il giroconto usa una categoria dedicata, **e non `Stipendio`**:
`v_periodi_stipendio` usa proprio quelle entrate (categoria `Stipendio` o
`Giroconto P.IVA`) per delimitare i periodi, e marcarlo diversamente
aprirebbe un periodo fasullo sfasando tutto lo storico.

### Il tipo dà la direzione, non il segno

Gli importi sono sempre positivi. La direzione la dà `tipo` (`entrata` o
`uscita`, nient'altro — vedi sotto). Due convenzioni sovrapposte si
annullerebbero a vicenda.

### "È un trasferimento" si dice solo con la categoria, non con `tipo`

`spese.tipo` accettava anche `giroconto`, indipendente dalla categoria — e
la categoria ha già "Giroconto P.IVA" per lo stesso concetto. Le due
segnalazioni si erano disallineate: righe con `tipo=giroconto` (bonifici da
terzi, non collegati alla P.IVA) restavano invisibili a
`v_periodi_stipendio`/`v_risparmi_mese`, che guardano solo `tipo=entrata`
(vedi [migrazione 8.9](#89--spesetipo-non-ha-più-giroconto)). Il form non
offre più questa scelta: `tipo` è solo `entrata`/`uscita`, e "che tipo di
entrata è" (P.IVA, stipendio, bonifico da qualcuno) lo dice sempre e solo
la categoria — come per ogni altro movimento.

### Una query che torna 1000 righe non ha finito

PostgREST tronca ogni risposta a un tetto (di solito 1000 righe) e non lo
segnala: la richiesta ha successo, i dati sono meno. `spese` ne ha già di
più. Un totale calcolato su una select secca esce **più basso del vero**,
senza errore, senza nulla che lo faccia notare — è il tipo di bug che si
scopre solo confrontando due numeri che dovrebbero combaciare.

Per questo tutto ciò che somma un periodo lungo pagina con `.range()`
finché un blocco non torna incompleto: `spese/dati.py::righe_periodo`,
`spese/dati.py::saldo_conto`, `fatture/fiscale.py::saldo_piva`.

Lo stesso vale per il tetto applicativo: `spese/dati.py::movimenti()`
tronca a 300 apposta, perché serve una lista da mostrare. **Non usarla per
i totali** — la sua docstring lo dice, ed è stato comunque fatto: il saldo
dell'anno su `/spese` contava solo i 300 movimenti più recenti.

### Il giroconto ha segno opposto sui due conti

Sul conto P.IVA è un'uscita, sul personale un'entrata. Il saldo di ciascuna
sezione ne tiene conto separatamente.

---

## 8. Migrazioni da eseguire

Da lanciare nell'**SQL Editor di Supabase**, in quest'ordine. Sono tutte
idempotenti: rilanciarle non fa danni.

**8.1–8.4 sono confermate applicate** — verificato il 2026-08-12
incrociando lo snapshot dello schema ([`docs/schema_supabase.md`](docs/schema_supabase.md))
e un export completo dei dati: categoria "Giroconto P.IVA" presente e
collegata (8.1), vista e RLS allineate (8.2), dati emittente popolati (8.3),
colonna del giroconto manuale presente (8.4). Restano solo come riferimento
storico. **8.7 lanciata e confermata il 2026-08-12.** Da lanciare ancora:
[8.6](#86--foreign-key-mancante-su-spesa_piva_id) (discrezionale),
[8.8](#88--pulizia-di-5-righe-con-dati-inconsistenti) (5 righe da correggere,
consigliata) e
[8.9](#89--spesetipo-non-ha-più-giroconto) (4 righe con `tipo=giroconto`
diventate invisibili ai risparmi, consigliata) e
[8.10](#810--tabella-dei-saldi-revolut) (nuova tabella, **necessaria**
perché `/spese/revolut` possa salvare).

### 8.1 — Categoria del giroconto sul conto personale ✅ già applicata

Senza, il giroconto arriva sul conto ma resta invisibile al budget (vedi
[le trappole](#7-le-trappole-del-database)).

```sql
insert into cfg_categorie (nome)
values ('Giroconto P.IVA')
on conflict (nome) do nothing;

insert into cfg_categoria_sottocategoria (categoria_id, sottocategoria_id)
select c.id, null
  from cfg_categorie c
 where c.nome = 'Giroconto P.IVA'
on conflict do nothing;
```

Verifica — deve tornare una riga:

```sql
select c.nome, l.id as categoria_link_id
  from cfg_categorie c
  join cfg_categoria_sottocategoria l on l.categoria_id = c.id
 where c.nome = 'Giroconto P.IVA' and l.sottocategoria_id is null;
```

### 8.2 — Vista fiscale riallineata e Row Level Security ✅ già applicata

`v_situazione_annuale` era rimasta indietro su due punti: filtrava uno stato
che non esiste più (`emessa`), quindi vedeva le sole incassate, e calcolava
l'imposta senza dedurre l'INPS.

```sql
create or replace view v_situazione_annuale as
with param as (
  select * from b2f_parametri_fiscali where id = 1
),
fatt as (
  select
    extract(year  from data)::int as anno,
    extract(month from data)::int as mese,
    sum(coalesce(totale, 0))                                as fatturato_mese,
    sum(coalesce(bollo, 0)) filter (where bollo_addebitato) as bollo_mese,
    count(*)                                                as n_fatture
  from b2f_fatture
  where stato in ('inviata_studio', 'trasmessa_sdi', 'incassata')
  group by 1, 2
),
inc as (
  select
    extract(year  from data_incasso)::int as anno,
    extract(month from data_incasso)::int as mese,
    sum(coalesce(totale, 0)) as incasso_mese
  from b2f_fatture
  where stato = 'incassata' and data_incasso is not null
  group by 1, 2
),
spese as (
  select
    extract(year  from data)::int as anno,
    extract(month from data)::int as mese,
    sum(importo) filter (
      where categoria = 'commercialista' and tipo = 'uscita'
    ) as commercialista_mese
  from b2f_spese_piva
  group by 1, 2
)
select
  f.anno,
  f.mese,
  f.fatturato_mese,
  round(f.fatturato_mese * p.coeff_ateco, 2) as imponibile_mese,
  coalesce(i.incasso_mese, 0)                as incasso_mese,
  round(f.fatturato_mese * p.coeff_ateco
        * (1 - p.aliquota_inps) * p.aliquota_imposta, 2) as imposta_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps, 2) as inps_saldo_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps
        * p.aliquota_acconto, 2)                              as inps_acconto_mese,
  coalesce(f.bollo_mese, 0)          as bollo_mese,
  coalesce(s.commercialista_mese, 0) as commercialista_mese,
  f.n_fatture
from fatt f
cross join param p
left join inc   i using (anno, mese)
left join spese s using (anno, mese)
order by f.anno, f.mese;
```

Poi la RLS sulle tabelle rimaste scoperte (vedi [Sicurezza](#9-sicurezza)):

```sql
alter table b2f_webauthn_credentials enable row level security;
alter table b2f_spese_piva           enable row level security;
alter table b2f_parametri_fiscali    enable row level security;
```

> **Le tabelle del sistema personale restano fuori di proposito.**
> `spese` e `risparmi_periodo` nascono da un sistema preesistente. Se qualcosa
> oltre a questa app le legge con la chiave anon — un foglio, una dashboard,
> un altro frontend — attivare la RLS lo taglia fuori all'istante. Che qualcosa
> lo faccia è plausibile: le `cfg_*` hanno già una policy *"Allow read using
> (true)"*, che serve proprio a quello.
>
> Solo dopo aver verificato che nient'altro le usi:
> ```sql
> -- alter table spese            enable row level security;
> -- alter table risparmi_periodo enable row level security;
> ```

### 8.3 — Dati dell'emittente ✅ già applicata

Senza, l'intestazione del facsimile esce col solo nome: il PDF legge
`b2f_emittente`, dove P.IVA, codice fiscale, indirizzo, email, PEC e IBAN erano
rimasti NULL dal seed iniziale. Aggiorna **solo i campi ancora vuoti**: quello
che hai già salvato dalla pagina vince.

```sql
update b2f_emittente set
  nome        = coalesce(nullif(nome, ''),        'Emanuele'),
  cognome     = coalesce(nullif(cognome, ''),     'Bellotti'),
  piva        = coalesce(nullif(piva, ''),        '14747480961'),
  cf          = coalesce(nullif(cf, ''),          'BLLMNL01S27F205K'),
  regime_fisc = coalesce(nullif(regime_fisc, ''), 'RF19'),
  indirizzo   = coalesce(nullif(indirizzo, ''),   'VIA GABBRO, 5'),
  cap         = coalesce(nullif(cap, ''),         '20161'),
  comune      = coalesce(nullif(comune, ''),      'Milano'),
  provincia   = coalesce(nullif(provincia, ''),   'MI'),
  nazione     = coalesce(nullif(nazione, ''),     'IT'),
  email       = coalesce(nullif(email, ''),       'ebellotti001@gmail.com'),
  pec         = coalesce(nullif(pec, ''),         'ebellotti@pec.it'),
  iban        = coalesce(nullif(iban, ''),        'IT03G0503401753000000180479')
where id = 1;
```

I dati si cambiano anche da `/fatture/emittente`.

### 8.4 — Collegamento dei giroconti manuali ✅ già applicata

Da `/fatture/spese-piva/nuova` si può registrare un giroconto anche senza
passare da una fattura (un trasferimento libero al conto personale). Senza
questa colonna l'app non ha dove scrivere quale riga di `spese` è nata da
quale movimento P.IVA, e non riuscirebbe a tenerle in sincrono quando una
delle due si elimina.

```sql
alter table b2f_spese_piva
  add column if not exists giroconto_personale_id integer;
```

Verificato presente su Supabase il 2026-08-12 (vedi
[`docs/schema_supabase.md`](docs/schema_supabase.md)) — non serve rilanciarla,
resta qui solo come riferimento.

### 8.5 — Ispezionare lo schema

Quando serve verificare com'è fatto davvero il database (è così che sono
emersi i disallineamenti qui sopra):

```sql
select riga from (
  select 1 as s, table_name || lpad(ordinal_position::text, 4, '0') as k,
         'COL   ' || rpad(table_name || '.' || column_name, 60) ||
         rpad(data_type, 32) || ' null=' || is_nullable ||
         ' ident=' || is_identity || ' def=' || coalesce(column_default, '-') as riga
  from information_schema.columns where table_schema = 'public'
  union all
  select 2, conrelid::regclass::text || conname,
         'VINC  ' || rpad(conrelid::regclass::text, 34) ||
         rpad(conname, 60) || pg_get_constraintdef(oid)
  from pg_constraint where connamespace = 'public'::regnamespace
  union all
  select 3, tablename || indexname, 'IDX   ' || indexdef
  from pg_indexes where schemaname = 'public'
  union all
  select 4, viewname, 'VIEW  ' || viewname || E'\n' ||
         pg_get_viewdef(('public.' || quote_ident(viewname))::regclass, true)
  from pg_views where schemaname = 'public'
  union all
  select 5, p.proname, 'FUNC  ' || p.proname || E'\n' || pg_get_functiondef(p.oid)
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public' and p.prokind = 'f'
  union all
  select 6, c.relname || t.tgname, 'TRIG  ' || pg_get_triggerdef(t.oid)
  from pg_trigger t
  join pg_class c on c.oid = t.tgrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and not t.tgisinternal
  union all
  select 7, c.relname,
         'RLS   ' || rpad(c.relname, 34) ||
         case when c.relrowsecurity then 'ATTIVA' else 'disattivata' end
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r'
  union all
  select 8, tablename || policyname,
         'POL   ' || rpad(tablename, 26) || rpad(policyname, 30) ||
         cmd || ' | using=' || coalesce(qual, '-')
  from pg_policies where schemaname = 'public'
) t order by s, k;
```

### 8.6 — Foreign key mancante su `spesa_piva_id`

`b2f_fatture.giroconto_piva_id` ha una FK verso `b2f_spese_piva(id)` (`on
delete set null`); `spesa_piva_id` — che punta alla stessa tabella, per la
riga "registra incasso" — non ce l'ha mai avuta. Verificato sui dati reali
del 2026-08-12 che non ci sono `spesa_piva_id` orfani, quindi si può
aggiungere senza rischio di far fallire la migrazione:

```sql
alter table b2f_fatture
  add constraint b2f_fatture_spesa_piva_id_fkey
  foreign key (spesa_piva_id) references b2f_spese_piva(id) on delete set null;
```

Senza, l'app se ne occupa comunque da sola via codice (`_stacca_da_fattura`
in `fatture/fiscale.py`), ma senza la FK il database non lo garantisce: è
un rinforzo, non un blocco a qualcosa che oggi si rompe.

### 8.7 — Il giroconto apre un periodo di risparmio, come lo stipendio

Da quando c'è la P.IVA il giroconto dal conto P.IVA è lo stipendio di
fatto: `v_periodi_stipendio` delimitava i periodi solo sulle entrate
categoria "Stipendio", quindi un giroconto restava "altre entrate" dentro
un periodo che non si chiudeva mai. Verificato sui dati reali (simulazione
Python sulle 966 righe di `spese`): oggi il periodo corrente parte dal
01/07/2026 e non si chiude; con la migrazione si spezza correttamente il
07/07/2026, e il giroconto dell'08/07 apre il nuovo periodo.

La migrazione tocca due viste: `v_periodi_stipendio` (il confine include
anche "Giroconto P.IVA") e `v_risparmi_mese` (esclude entrambe le
categorie da "Totale Altre Entrate", altrimenti un giroconto verrebbe
contato due volte; il "Mese" si calcola dalla data di inizio periodo,
non dal prossimo bonifico che per il periodo aperto non esiste ancora;
ed espone finalmente "Risparmio effettivo (€)", calcolato ma mai
selezionato nella vista precedente).

```sql
create or replace view v_periodi_stipendio as
with stipendi as (
  select vs.data as data_bonifico,
         vs.importo as importo_bonifico
    from v_spese vs
   where vs.tipo = 'entrata'
     and vs.categoria in ('Stipendio', 'Giroconto P.IVA')
), ord as (
  select stipendi.data_bonifico,
         stipendi.importo_bonifico,
         lead(stipendi.data_bonifico) over (order by stipendi.data_bonifico) as prossimo_bonifico
    from stipendi
)
select data_bonifico,
       importo_bonifico,
       prossimo_bonifico,
       coalesce((prossimo_bonifico - interval '1 day')::timestamp with time zone,
                current_date::timestamp with time zone) as fine_periodo
  from ord
 order by data_bonifico;


create or replace view v_risparmi_mese as
with per as (
  select ps.data_bonifico,
         ps.importo_bonifico,
         ps.prossimo_bonifico,
         ps.fine_periodo
    from v_periodi_stipendio ps
), agg as (
  select per.data_bonifico,
         per.prossimo_bonifico,
         per.fine_periodo,
         per.importo_bonifico,
         round(coalesce(sum(case when vs.tipo = 'uscita' and vs.categoria = 'Fisso'
                                  then vs.importo else 0 end), 0), 2) as totale_fisso,
         round(coalesce(sum(case when vs.tipo = 'uscita' and vs.categoria = 'Personale'
                                  then vs.importo else 0 end), 0), 2) as totale_personale,
         round(coalesce(sum(case when vs.tipo = 'uscita' and vs.categoria = 'Benzina'
                                  then vs.importo else 0 end), 0), 2) as totale_benzina,
         round(coalesce(sum(case when vs.tipo = 'uscita' and vs.categoria = 'Viaggi'
                                  then vs.importo else 0 end), 0), 2) as totale_viaggi,
         round(coalesce(sum(case when vs.tipo = 'uscita'
                                  then vs.importo else 0 end), 0), 2) as totale_speso,
         -- Esclude sia Stipendio sia Giroconto P.IVA: entrambi aprono il
         -- periodo (vedi v_periodi_stipendio), quindi sono gia' contati
         -- come "importo_bonifico" — contarli anche qui li duplicherebbe.
         round(coalesce(sum(case when vs.tipo = 'entrata'
                                  and vs.categoria not in ('Stipendio', 'Giroconto P.IVA')
                                  then vs.importo else 0 end), 0), 2) as totale_altre_entrate
    from per
    left join v_spese vs on vs.data >= per.data_bonifico and vs.data <= per.fine_periodo
   group by per.data_bonifico, per.prossimo_bonifico, per.fine_periodo, per.importo_bonifico
), eff as (
  select rp.data_bonifico,
         round(coalesce(rp.effettivo_risparmio, 0)::numeric, 2) as effettivo_risparmio
    from risparmi_periodo rp
), calc as (
  select a.data_bonifico, a.prossimo_bonifico, a.fine_periodo, a.importo_bonifico,
         a.totale_fisso, a.totale_personale, a.totale_benzina, a.totale_viaggi,
         a.totale_speso, a.totale_altre_entrate,
         p.saldo_iniziale, p.percentuale_risparmio, p.perc_fondo_emergenze,
         p.perc_viaggi, p.perc_fondo_casa, p.perc_regali, p.perc_altro,
         coalesce(e.effettivo_risparmio, 0) as effettivo_risparmio,
         a.importo_bonifico + a.totale_altre_entrate - a.totale_speso
           - coalesce(e.effettivo_risparmio, 0) as delta,
         sum(a.importo_bonifico + a.totale_altre_entrate - a.totale_speso
             - coalesce(e.effettivo_risparmio, 0))
           over (order by a.data_bonifico rows unbounded preceding) as running_delta
    from agg a
    cross join lateral (
      select i.saldo_iniziale, i.percentuale_risparmio, i.perc_fondo_emergenze,
             i.perc_viaggi, i.perc_fondo_casa, i.perc_regali, i.perc_altro
        from impostazioni i
       where i.valido_dal <= a.data_bonifico
       order by i.valido_dal desc
       limit 1
    ) p
    left join eff e using (data_bonifico)
), bal as (
  select c.data_bonifico, c.prossimo_bonifico, c.fine_periodo, c.importo_bonifico,
         c.totale_fisso, c.totale_personale, c.totale_benzina, c.totale_viaggi,
         c.totale_speso, c.totale_altre_entrate,
         c.saldo_iniziale, c.percentuale_risparmio, c.perc_fondo_emergenze,
         c.perc_viaggi, c.perc_fondo_casa, c.perc_regali, c.perc_altro,
         c.effettivo_risparmio, c.delta, c.running_delta,
         coalesce(lag(c.running_delta) over (order by c.data_bonifico), 0) as running_delta_prev
    from calc c
), outt as (
  select round((bal.saldo_iniziale + bal.running_delta_prev)::numeric, 2) as importo_prima_del_bonifico,
         bal.data_bonifico, bal.prossimo_bonifico, bal.fine_periodo,
         round(bal.importo_bonifico::numeric, 2) as importo_bonifico,
         bal.totale_fisso, bal.totale_personale, bal.totale_benzina, bal.totale_viaggi,
         bal.totale_speso, bal.totale_altre_entrate,
         round(bal.importo_bonifico + bal.totale_altre_entrate - bal.totale_speso, 2) as totale_rimanente_bonifico,
         bal.saldo_iniziale + bal.running_delta_prev + bal.importo_bonifico
           + bal.totale_altre_entrate - bal.totale_speso as base_calcolo,
         bal.effettivo_risparmio, bal.percentuale_risparmio, bal.perc_fondo_emergenze,
         bal.perc_viaggi, bal.perc_fondo_casa, bal.perc_regali, bal.perc_altro
    from bal
), final as (
  select outt.importo_prima_del_bonifico, outt.data_bonifico, outt.prossimo_bonifico,
         outt.fine_periodo, outt.importo_bonifico, outt.totale_fisso, outt.totale_personale,
         outt.totale_benzina, outt.totale_viaggi, outt.totale_speso, outt.totale_altre_entrate,
         outt.totale_rimanente_bonifico, outt.base_calcolo, outt.effettivo_risparmio,
         outt.percentuale_risparmio, outt.perc_fondo_emergenze, outt.perc_viaggi,
         outt.perc_fondo_casa, outt.perc_regali, outt.perc_altro,
         round(case when (outt.base_calcolo * outt.percentuale_risparmio) < 0 then 0
                    else outt.base_calcolo * outt.percentuale_risparmio end::numeric, 2) as risparmio_consigliato
    from outt
)
select importo_prima_del_bonifico as "Importo Prima Del Bonifico",
       importo_prima_del_bonifico as "Importo Prima Del Bonifico (dup)",
       data_bonifico as "Data bonifico",
       prossimo_bonifico as "Data prossimo bonifico",
       case extract(month from data_bonifico)::int
         when 1 then 'gennaio' when 2 then 'febbraio' when 3 then 'marzo'
         when 4 then 'aprile' when 5 then 'maggio' when 6 then 'giugno'
         when 7 then 'luglio' when 8 then 'agosto' when 9 then 'settembre'
         when 10 then 'ottobre' when 11 then 'novembre' when 12 then 'dicembre'
         else null end as "Mese",
       importo_bonifico as "Importo Bonifico",
       totale_fisso as "Totale Fisso",
       totale_personale as "Totale Personale",
       totale_benzina as "Totale Benzina",
       totale_viaggi as "Totale Viaggi",
       totale_speso as "Totale Speso",
       totale_altre_entrate as "Totale Altre Entrate",
       round(totale_rimanente_bonifico, 2) as "Totale Rimanente",
       risparmio_consigliato as "Risparmio consigliato (€)",
       round((base_calcolo - effettivo_risparmio)::numeric, 2) as "Totale Rimanente (finale)",
       round((effettivo_risparmio * perc_fondo_emergenze)::numeric, 2) as "Quota Fondo Emergenze",
       round((effettivo_risparmio * perc_viaggi)::numeric, 2) as "Quota Viaggi",
       round((effettivo_risparmio * perc_fondo_casa)::numeric, 2) as "Quota Fondo Casa",
       round((effettivo_risparmio * perc_regali)::numeric, 2) as "Quota Regali",
       round((effettivo_risparmio * perc_altro)::numeric, 2) as "Quota Altro",
       fine_periodo as "_Fine periodo (debug)",
       -- In fondo e non in mezzo apposta: CREATE OR REPLACE VIEW su Postgres
       -- rifiuta di "rinominare" una colonna esistente spostandone la
       -- posizione — accetta solo colonne aggiunte in coda.
       effettivo_risparmio as "Risparmio effettivo (€)"
  from final
 order by data_bonifico;
```

Nel codice, `spese/risparmi.py` e `spese/dati.py` già leggono il nuovo
campo "Risparmio effettivo (€)"; finché la migrazione non è applicata la
vista continua a non esporlo, l'app lo tratta come sempre-zero (il
comportamento che aveva prima) senza errori.

### 8.8 — Pulizia di 5 righe con dati inconsistenti

Audit completo su tutte le 1021 righe reali di `spese` (export CSV
completo, non l'Excel troncato — vedi nota più sotto). Il collegamento
`categoria_link_id` → `cfg_categoria_sottocategoria` → categoria/
sottocategoria è risultato **integro al 100%** (zero link orfani, zero
righe disattivate ancora referenziate, zero FK rotte): non serve nessuna
migrazione su categorie o sottocategorie, né lato personale né lato
P.IVA. Il giroconto della fattura 2026/001 (righe collegate `b2f_fatture`
id 1 → `b2f_spese_piva` id 1/3 → `spese` id 600) è risultato coerente
punta a punta con gli importi giusti.

Le uniche 5 righe inconsistenti trovate, tutte in `spese`:

| id  | problema                                    | causa                     |
|-----|----------------------------------------------|---------------------------|
| 707 | `anno` = 2027, ma `data` = 2026-03-18         | battitura sull'anno       |
| 708 | `anno` = 2027, ma `data` = 2026-03-18         | battitura sull'anno       |
| 638 | `mese` = 3, ma `data` = 2026-02-09            | battitura sul mese        |
| 269 | `importo` = -29.79 su `tipo = 'uscita'`       | segno invertito           |
| 227 | `importo` = -16.60 su `tipo = 'uscita'`       | segno invertito           |

`mese`/`anno` derivati a mano invece che dalla data, e un'uscita con
importo negativo, rompono esattamente le due convenzioni documentate nel
§7 ("mese/anno derivano dalla data", "importo sempre positivo, il segno
lo dà `tipo`") — e con loro tutte le viste che raggruppano per
mese/anno o sommano gli importi.

La query è generale e idempotente: ricalcola `mese`/`anno` dalla `data`
ovunque non coincidano (non solo per questi 5 id) e rende positivo ogni
importo negativo. Rilanciarla non fa nulla se non trova più righe
sbagliate.

```sql
update spese
   set mese = extract(month from data)::int,
       anno = extract(year from data)::int
 where mese <> extract(month from data)::int
    or anno <> extract(year from data)::int;

update spese
   set importo = abs(importo)
 where tipo = 'uscita'
   and importo < 0;
```

Nota sull'Excel `gestione_spese/excel`: il foglio "Spese API" lì dentro
si ferma a 1000 righe con 21 righe mancanti sparse (non solo le ultime),
segno di un fetch senza `order by` stabile lato strumento esterno che
lo genera — non è una vista o un endpoint di questo repo, quindi non è
qualcosa che questa migrazione o il codice dell'Hub possano correggere;
l'audit sopra è stato fatto sui dati reali via export CSV completo
(1021 righe), non su quell'Excel.

### 8.9 — `spese.tipo` non ha più "Giroconto"

Il form "Nuovo movimento" offriva tre `tipo` (Entrata, Uscita,
Giroconto) **indipendenti dalla categoria** — che ha già una categoria
"Giroconto P.IVA" per lo stesso concetto. Due modi di dire la stessa
cosa, e solo uno collegato a `v_periodi_stipendio`/`v_risparmi_mese`
(controllano `tipo = 'entrata'`): 4 righe reali con `tipo = 'giroconto'`
— bonifici ricevuti da terzi (matrimonio, hotel, vino, vacanza — non
c'entrano con la P.IVA), categoria "Personale › Bonifici` — risultavano
invisibili ai risparmi per periodo, per un totale di € 635.

```sql
update spese
   set tipo = 'entrata'
 where tipo = 'giroconto';
```

Idempotente (dopo la prima esecuzione non trova più righe). La
categoria di quelle righe non cambia: era già corretta ("Personale ›
Bonifici"), il problema era solo `tipo`. Il codice non offre più
"Giroconto" nel form né lo accetta in scrittura (`spese/dati.py`,
`TIPI`); resta gestito in lettura per compatibilità finché questa
migrazione non è lanciata, quindi l'ordine non è critico — ma senza
la migrazione quelle 4 righe restano fuori da `v_risparmi_mese`.

### 8.10 — Tabella dei saldi Revolut

Serve per il terzo conto (vedi [§ 2](#revolut--speserevolut)). Una riga
per snapshot, con la data come chiave: reimportare lo stesso estratto
aggiorna la riga invece di aggiungerne una gemella.

Finché non è applicata, la pagina `/spese/revolut` si apre e legge
l'estratto ma il salvataggio risponde con un errore che rimanda qui;
tutto il resto dell'app funziona come prima.

```sql
create table if not exists b2f_revolut (
  data          date primary key,
  conto         numeric not null default 0,   -- liquidità (conti correnti)
  risparmi      numeric not null default 0,   -- deposito / salvadanai, totale
  investimenti  numeric not null default 0,   -- portafoglio, scritto a mano
  salvadanai    jsonb   not null default '{}'::jsonb,
  fonte         text    not null default 'estratto',
  note          text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

alter table b2f_revolut enable row level security;

drop trigger if exists trg_b2f_revolut_updated on b2f_revolut;
create trigger trg_b2f_revolut_updated before update on b2f_revolut
  for each row execute function b2f_touch_updated_at();
```

RLS attiva senza policy, come le altre `b2f_*`: entra solo l'app, che
usa `service_role` (vedi [Sicurezza](#9-sicurezza)).

`salvadanai` è un oggetto con le cinque chiavi `emergenze`, `casa`,
`vacanze`, `regali`, `altro` — le stesse cinque quote di `impostazioni`.
È facoltativo: senza, resta il totale.

---

### 8.11 — I risparmi diventano movimenti veri (**necessaria**)

È la migrazione che chiude per costruzione il buco costato 829,78 € di
scarto in diciotto mesi. Fino a oggi il denaro che va nei salvadanai
usciva dal saldo in **due modi diversi e incompatibili**: come normale
uscita in `spese`, oppure come numero digitato a mano in
`risparmi_periodo` — e niente diceva quale valesse per quale bonifico.
Alcuni erano tolti una volta, alcuni due, alcuni mai.

Dopo questa migrazione ce n'è **uno solo**: i bonifici verso Revolut
sono righe di `spese` come tutte le altre, categoria "Risparmi", con la
data vera del bonifico. Il saldo del conto torna a essere
`apertura + entrate − uscite`, la stessa formula della banca.

> **Va lanciata appena il codice nuovo va in produzione, o prima.**
> `saldo_conto()` non sottrae più il risparmio dichiarato: finché i
> bonifici non sono righe di `spese`, il saldo mostrato è più alto del
> vero di tutto il dichiarato (14.912,07 € sui dati di agosto 2026). Non
> è un dato corrotto — è la formula nuova applicata a dati vecchi — e si
> sistema lanciando questo script.

**Lanciarla non muove il saldo**, né col codice vecchio né col nuovo, e
non per caso: le uscite che inserisce (14.912,07 €) sono esattamente pari
al risparmio dichiarato che azzera, nello stesso script. Con il codice
vecchio quello che smette di essere sottratto da un lato ricompare come
uscita dall'altro; con il nuovo, riporta il saldo dov'era. In entrambi i
casi si finisce a 3.259,04 € al 25/08/2026.

```sql
-- 1. la categoria
insert into cfg_categorie (nome) values ('Risparmi')
on conflict (nome) do nothing;

insert into cfg_categoria_sottocategoria (categoria_id, sottocategoria_id)
select c.id, null from cfg_categorie c where c.nome = 'Risparmi'
on conflict do nothing;

-- 2. i bonifici verso Revolut che non erano mai stati registrati.
--    Idempotente: il `where not exists` impedisce il doppio inserimento
--    se la migrazione viene rilanciata.
do $$
declare
  link uuid;
  r record;
begin
  select l.id into link
    from cfg_categoria_sottocategoria l
    join cfg_categorie c on c.id = l.categoria_id
   where c.nome = 'Risparmi' and l.sottocategoria_id is null;

  for r in
    select * from (values
      (date '2025-05-20',  412.38, 'uscita',  'Ricarica Revolut con carta'),
      (date '2025-05-30', 2242.25, 'uscita',  'Bonifico a Revolut'),
      (date '2025-06-11',  200.00, 'uscita',  'Ricarica Revolut con carta'),
      (date '2025-06-24',  685.00, 'uscita',  'Bonifico a Revolut'),
      (date '2025-06-30',  845.00, 'uscita',  'Bonifico a Revolut'),
      (date '2025-07-30',  770.98, 'uscita',  'Bonifico a Revolut'),
      (date '2025-08-28',  770.98, 'uscita',  'Bonifico a Revolut'),
      (date '2025-10-01',  670.00, 'uscita',  'Bonifico a Revolut'),
      (date '2025-12-01', 1311.00, 'uscita',  'Bonifico a Revolut'),
      (date '2026-01-07', 1170.00, 'uscita',  'Bonifico a Revolut'),
      (date '2026-03-13',  737.00, 'uscita',  'Bonifico a Revolut'),
      (date '2026-04-02', 2040.00, 'uscita',  'Bonifico a Revolut'),
      (date '2026-05-27',  430.17, 'uscita',  'Bonifico a Revolut'),
      (date '2026-05-27',  430.17, 'entrata', 'Rientro da Revolut'),
      (date '2026-06-11',  600.00, 'uscita',  'Bonifico a Revolut'),
      (date '2026-07-09', 2457.48, 'uscita',  'Bonifico a Revolut')
    ) as v(d, imp, tp, descr)
  loop
    if not exists (select 1 from spese s
                    where s.data = r.d and s.importo = r.imp
                      and s.tipo = r.tp and s.categoria_link_id = link) then
      perform insert_spesa_first_free_id(
        p_anno := extract(year from r.d)::int,
        p_mese := extract(month from r.d)::int,
        p_data := r.d, p_importo := r.imp, p_tipo := r.tp,
        p_metodo_pagamento := 'Estratto WeBank',
        p_categoria_link_id := link, p_descrizione := r.descr);
    end if;
  end loop;

  -- 3. i bonifici Revolut gia' registrati come normali uscite: cambia
  --    solo la categoria, il saldo non si muove. Servono a v_risparmi_mese
  --    per non contarli come spesa.
  update spese set categoria_link_id = link
   where categoria_link_id <> link
     and (data, importo, tipo) in (
       (date '2025-03-07', 500.00, 'uscita'), (date '2025-03-07', 140.00, 'uscita'),
       (date '2025-03-13', 250.00, 'uscita'), (date '2025-04-14',  20.00, 'uscita'),
       (date '2025-05-02', 225.00, 'uscita'), (date '2025-05-05',  67.00, 'uscita'),
       (date '2026-08-03', 150.00, 'entrata'));
end $$;

-- 4. `risparmi_periodo` smette di essere una fonte per il saldo: resta
--    la tabella del "quanto volevo mettere via", che la pagina Risparmi
--    confronta col risparmiato vero. Azzerarlo qui, nello stesso script
--    che ha inserito i movimenti, e' cio' che rende la migrazione a
--    saldo invariato: quello che smette di essere sottratto da un lato
--    ricompare come uscita dall'altro, allo stesso centesimo.
update risparmi_periodo set effettivo_risparmio = 0;
```

Poi la vista, che deve leggere il risparmio effettivo **dai movimenti**
invece che dalla dichiarazione — e togliere quelle uscite da "Totale
Speso", altrimenti il risparmio consigliato verrebbe calcolato su una
base già decurtata di quanto hai messo via:

```sql
-- DROP e non "create or replace": PostgreSQL con REPLACE puo' solo
-- aggiungere colonne in coda, non inserirne una in mezzo — e qui
-- "Risparmio effettivo (€)" va prima di "Totale Rimanente (finale)".
-- Con REPLACE si prende un 42P16 ("cannot change name of view column").
-- Nessuna altra vista dipende da questa, quindi il drop e' sicuro; i
-- GRANT in fondo rimettono i permessi, che il drop porta via con se'.
drop view if exists v_risparmi_mese;

create view v_risparmi_mese as
with per as (
  select ps.data_bonifico, ps.importo_bonifico, ps.prossimo_bonifico, ps.fine_periodo
    from v_periodi_stipendio ps
), agg as (
  select per.data_bonifico, per.prossimo_bonifico, per.fine_periodo, per.importo_bonifico,
         round(coalesce(sum(case when vs.tipo='uscita' and vs.categoria='Fisso'
                                 then vs.importo else 0 end),0),2) as totale_fisso,
         round(coalesce(sum(case when vs.tipo='uscita' and vs.categoria='Personale'
                                 then vs.importo else 0 end),0),2) as totale_personale,
         round(coalesce(sum(case when vs.tipo='uscita' and vs.categoria='Benzina'
                                 then vs.importo else 0 end),0),2) as totale_benzina,
         round(coalesce(sum(case when vs.tipo='uscita' and vs.categoria='Viaggi'
                                 then vs.importo else 0 end),0),2) as totale_viaggi,
         -- "Speso" esclude i Risparmi: mettere da parte non e' spendere
         round(coalesce(sum(case when vs.tipo='uscita'
                                  and coalesce(vs.categoria,'') <> 'Risparmi'
                                 then vs.importo else 0 end),0),2) as totale_speso,
         round(coalesce(sum(case when vs.tipo='entrata'
                                  and vs.categoria not in ('Stipendio','Giroconto P.IVA','Risparmi')
                                 then vs.importo else 0 end),0),2) as totale_altre_entrate,
         -- il risparmio vero: uscite verso i salvadanai meno i rientri
         round(coalesce(sum(case when coalesce(vs.categoria,'') = 'Risparmi'
                                 then case when vs.tipo='uscita' then vs.importo
                                           else -vs.importo end
                                 else 0 end),0),2) as effettivo_risparmio
    from per
    left join v_spese vs on vs.data >= per.data_bonifico and vs.data <= per.fine_periodo
   group by per.data_bonifico, per.prossimo_bonifico, per.fine_periodo, per.importo_bonifico
), calc as (
  select a.*, p.saldo_iniziale, p.percentuale_risparmio, p.perc_fondo_emergenze,
         p.perc_viaggi, p.perc_fondo_casa, p.perc_regali, p.perc_altro,
         sum(a.importo_bonifico + a.totale_altre_entrate - a.totale_speso
             - a.effettivo_risparmio)
           over (order by a.data_bonifico rows unbounded preceding) as running_delta
    from agg a
    cross join lateral (
      select i.saldo_iniziale, i.percentuale_risparmio, i.perc_fondo_emergenze,
             i.perc_viaggi, i.perc_fondo_casa, i.perc_regali, i.perc_altro
        from impostazioni i where i.valido_dal <= a.data_bonifico
       order by i.valido_dal desc limit 1) p
), bal as (
  select c.*, coalesce(lag(c.running_delta) over (order by c.data_bonifico), 0)
              as running_delta_prev
    from calc c
), outt as (
  select bal.*,
         round((bal.saldo_iniziale + bal.running_delta_prev)::numeric, 2)
           as importo_prima_del_bonifico,
         (bal.saldo_iniziale + bal.running_delta_prev + bal.importo_bonifico
          + bal.totale_altre_entrate - bal.totale_speso) as base_calcolo
    from bal
)
select importo_prima_del_bonifico as "Importo Prima Del Bonifico",
       importo_prima_del_bonifico as "Importo Prima Del Bonifico (dup)",
       data_bonifico              as "Data bonifico",
       prossimo_bonifico          as "Data prossimo bonifico",
       to_char(data_bonifico, 'TMmonth') as "Mese",
       round(importo_bonifico::numeric, 2) as "Importo Bonifico",
       totale_fisso     as "Totale Fisso",
       totale_personale as "Totale Personale",
       totale_benzina   as "Totale Benzina",
       totale_viaggi    as "Totale Viaggi",
       totale_speso     as "Totale Speso",
       totale_altre_entrate as "Totale Altre Entrate",
       round(importo_bonifico + totale_altre_entrate - totale_speso, 2)
         as "Totale Rimanente",
       round(greatest(base_calcolo * percentuale_risparmio, 0)::numeric, 2)
         as "Risparmio consigliato (€)",
       effettivo_risparmio as "Risparmio effettivo (€)",
       round((base_calcolo - effettivo_risparmio)::numeric, 2)
         as "Totale Rimanente (finale)",
       round((effettivo_risparmio * perc_fondo_emergenze)::numeric, 2) as "Quota Fondo Emergenze",
       round((effettivo_risparmio * perc_viaggi)::numeric, 2)          as "Quota Viaggi",
       round((effettivo_risparmio * perc_fondo_casa)::numeric, 2)      as "Quota Fondo Casa",
       round((effettivo_risparmio * perc_regali)::numeric, 2)          as "Quota Regali",
       round((effettivo_risparmio * perc_altro)::numeric, 2)           as "Quota Altro",
       fine_periodo as "_Fine periodo (debug)"
  from outt
 order by data_bonifico;

-- Il drop si porta via i permessi: l'app legge con la chiave anon.
grant select on v_risparmi_mese to anon, authenticated;
```

Verifica — il saldo prima e dopo deve essere identico (3.259,04 al
25/08/2026), e il totale dichiarato deve essere zero:

```sql
select (select round(sum(effettivo_risparmio::numeric),2) from risparmi_periodo) as dichiarato_deve_essere_zero,
       (select round(sum(case when tipo='uscita' then importo else -importo end),2)
          from v_spese where categoria='Risparmi') as uscito_verso_i_salvadanai;
```

### 8.12 — Il controllo contro l'estratto (**necessaria**)

La tabella dove si scrive, ogni tanto, il saldo che la banca dichiara.
È l'unico numero di **fonte esterna** in tutto il sistema: tutto il
resto è coerente per costruzione — i totali tornano coi movimenti
perché dai movimenti sono calcolati — e proprio per questo non può
accorgersi di un movimento mai registrato. `/saldi` confronta i due e
lo dice a schermo.

```sql
create table if not exists b2f_saldi_verifica (
  id          bigserial primary key,
  conto       text        not null check (conto in ('personale', 'piva')),
  data        date        not null,
  saldo_banca numeric(12,2) not null,
  note        text,
  created_at  timestamptz not null default now(),
  unique (conto, data)
);

alter table b2f_saldi_verifica enable row level security;

-- I due controlli gia' fatti in questa sessione, con gli estratti veri
insert into b2f_saldi_verifica (conto, data, saldo_banca, note) values
  ('personale', '2026-08-25', 3259.04, 'Estratto WeBank, riconciliazione riga per riga'),
  ('piva',      '2026-08-25', 1506.15, 'Verificato sul saldo WeBank del conto P.IVA')
on conflict (conto, data) do update
  set saldo_banca = excluded.saldo_banca, note = excluded.note;
```

**Ogni volta che apri l'estratto**, aggiungi una riga: sono dieci
secondi, e sono la differenza fra accorgersi di uno scarto in una
settimana o in un anno e mezzo.

### 8.13 — La fattura si ricorda di quali ore è fatta (**necessaria**)

Fino a oggi la fattura e il timesheet non si parlavano: le ore stanno sul
portale XS, la fattura su Supabase, e l'unico ponte era la memoria di chi
scriveva "20 giornate" nella riga. Queste tre colonne sono quel ponte.

`ore_periodo` è il mese di competenza (il primo giorno del mese, così è
una data vera e non una stringa da parsare). `ore_snapshot` è la **foto**
del riepilogo del portale al momento in cui l'hai agganciata: totale
minuti, giornate, giorni lavorati, ripartizione per cliente. È una foto e
non una lettura dal vivo per due motivi — il portale si legge un giorno
alla volta (trenta richieste HTTP per un mese: troppo per aprire una
pagina) e fra due anni quel mese sul portale potrebbe non esserci più,
mentre la fattura resta.

`ore_lette_il` dice **quando** è stata scattata: una foto senza data si
legge come un dato dal vivo, ed è lo stesso errore che la tessera Revolut
ha già fatto una volta.

```sql
alter table b2f_fatture
  add column if not exists ore_periodo  date,
  add column if not exists ore_snapshot jsonb,
  add column if not exists ore_lette_il timestamptz;

comment on column b2f_fatture.ore_periodo  is
  'Mese di competenza delle ore fatturate (primo giorno del mese)';
comment on column b2f_fatture.ore_snapshot is
  'Foto del riepilogo ore del portale XS: minuti, giornate, per cliente';
comment on column b2f_fatture.ore_lette_il is
  'Quando è stata scattata ore_snapshot';
```

### 8.14 — La tariffa giornaliera è un parametro, non una costante (**necessaria**)

Serve alla precompilazione della fattura dal timesheet: giornate ×
tariffa, una riga sola. Sta accanto alle aliquote e non nel codice perché
il giorno che cambia non deve servire un deploy — è un numero
commerciale, non una regola del forfettario.

```sql
alter table b2f_parametri_fiscali
  add column if not exists tariffa_giornaliera numeric(12,2) not null default 250;

comment on column b2f_parametri_fiscali.tariffa_giornaliera is
  'Tariffa per giornata da 8 ore, usata per precompilare la fattura dalle ore';
```

## 9. Sicurezza

**Accesso all'app.** PIN, più sblocco biometrico via WebAuthn. Il gate in
`xs_server.py` protegge sia le pagine HTML sia le rotte `/api/*`,
`/fatture/api/*` e `/spese/api/*`: senza sessione valida, una pagina mostra
solo l'overlay di sblocco, mai il contenuto.

**Accesso al database.** L'app si collega con la chiave `service_role`, che
bypassa la RLS. La chiave `anon`, invece, **non è un segreto**: nasce per stare
nei client. Su una tabella con RLS disattivata permette lettura *e scrittura* a
chiunque la conosca.

La configurazione giusta è quindi **RLS attiva senza policy**: nessuno entra
tranne l'app. Aggiungere policy permissive riaprirebbe l'accesso.

| Tabella | Stato |
|---|---|
| `b2f_fatture`, `b2f_clienti`, `b2f_emittente` | RLS attiva, nessuna policy |
| `b2f_spese_piva`, `b2f_parametri_fiscali`, `b2f_webauthn_credentials` | da attivare — [§ 8.2](#82--vista-fiscale-riallineata-e-row-level-security) |
| `b2f_revolut` | RLS attivata dalla migrazione stessa — [§ 8.10](#810--tabella-dei-saldi-revolut) |
| `spese`, `risparmi_periodo` | lasciate fuori: vedi l'avvertenza in § 8.2 |

Dietro il proxy di Render serve `ProxyFix`, altrimenti l'origin calcolato per
WebAuthn resta `http://` e la verifica fallisce.

---

## 10. Configurazione e deploy

### Variabili d'ambiente

| Variabile | A cosa serve |
|---|---|
| `SUPABASE_URL` | URL del progetto |
| `SUPABASE_KEY` | chiave `service_role` |
| `APP_PIN` | PIN di sblocco |
| `SECRET_KEY` | firma dei cookie di sessione (generata da Render) |
| `XS_USER` · `XS_PASS` | credenziali del portale ore |
| `RENDER` | impostata da Render: attiva i cookie `Secure` |

### Deploy

`render.yaml` descrive il servizio. Build `pip install -r requirements.txt`,
avvio `gunicorn -w 1 app:app`.

**Un solo worker è voluto:** la sessione sta in memoria.

### La tenda d'attesa (il risveglio di Render)

Il piano gratuito manda il container in letargo dopo un quarto d'ora
senza richieste. La prima richiesta dopo il letargo paga il risveglio —
una ventina di secondi buoni — e in quella finestra a rispondere è il
proxy di Render, con la **sua** schermata di caricamento: marchio loro,
log del loro deploy, invito a costruire su Render. Era l'unica schermata
dell'app che non era dell'app.

Non si può sostituirla dal server (quando risponde Render il nostro
processo non c'è ancora), ma si può rispondere **prima** di Render:

1. Ogni risposta dell'app porta l'header **`X-B2F: hub`** (`app.py`,
   `_firma_risposta`). È l'unico modo onesto di distinguere "ha risposto
   l'app" da "ha risposto qualcun altro al posto suo": si riconosce il
   nostro, non l'HTML altrui — quello cambia quando vogliono loro.
2. Il **service worker** (`/sw.js`, generato da
   `shared/caricamento.py`) intercetta le navigazioni. Se la risposta non
   ha quell'header — interstiziale di Render, 502, rete assente — serve
   dalla cache **`/attesa`**, la nostra tenda.
3. La tenda bussa a **`/ping`** ogni due secondi. Quando risponde
   davvero l'app, ricarica la pagina: il mosaico resta giù, e si alza da
   dentro l'app un attimo dopo. Un movimento solo, non due schermate.

Cosa serve saperne:

- **Vale dalla seconda visita.** Il worker si installa mentre l'app è
  viva; la primissima apertura su un dispositivo nuovo vede ancora Render.
- **`/attesa` e `/ping` restano fuori dal PIN** (`ALLOW_NO_PIN`): la tenda
  non mostra dati, e deve poter essere messa in cache anche a sessione
  bloccata. Se un giorno si rinominano quelle funzioni, il gate ricomincia
  a proteggerle e in cache finisce la schermata del PIN al posto della
  tenda.
- **La cache si chiama con l'impronta della tenda** (`_versione()`):
  cambiando il disegno cambia `/sw.js`, il browser reinstalla il worker e
  la vecchia cache viene buttata. Nessun ricordo da svuotare a mano.
- **Funziona anche offline**: senza rete la tenda compare lo stesso, e
  quando la rete torna entra da sola.

### In locale

```bash
pip install -r requirements.txt
export SUPABASE_URL=... SUPABASE_KEY=... APP_PIN=0000 SECRET_KEY=dev
python app.py          # http://localhost:5000
```

Senza le variabili di Supabase l'app parte lo stesso: le pagine mostrano un
avviso e le API rispondono 503, invece di andare in errore.

**Serve Python 3.12**: il codice usa f-string annidate con lo stesso tipo di
virgolette (PEP 701), che su 3.11 non compilano.

---

## 11. Sviluppo

### Convenzioni

- Le pagine sono f-string in Python. Dentro una f-string le graffe si
  raddoppiano: quello che deve restare graffa letterale (CSS, JavaScript) va
  scritto `{{` e `}}`.
- I formattatori stanno in `shared/fmt.py`. Non riscriverli.
- Gli stili stanno in `shared/design.py`. Le pagine usano le classi, non
  colori inline.
- Le guardie stanno negli endpoint, non solo nell'interfaccia: nascondere un
  pulsante non impedisce a nessuno di chiamare l'API.
- I commenti spiegano **perché**, non cosa.
- **I menù a tendina che elencano dati vanno in ordine alfabetico per la
  descrizione mostrata** — categorie, sottocategorie, clienti, metodi di
  pagamento, tipi di movimento, commesse. L'ordinamento passa da
  `shared/ordina.py` (accenti appiattiti, maiuscole ignorate), non da
  `sorted()` e non dalle colonne `ordine` del database. Fanno eccezione i
  menù in cui l'ordine *è* informazione — mesi, anni, stati della fattura,
  scenari di accantonamento — che restano nella loro sequenza naturale.
  `tools/verifica_menu.py` controlla la regola su tutte le pagine.

### Utilità in `tools/`

| Strumento | Cosa fa |
|---|---|
| `preview.py` | monta l'app con un finto client Supabase e dati realistici, per guardare le schermate senza toccare il database |
| `verifica_layout.py` | cerca overflow orizzontali, che sui browser mobili mandano in shrink-to-fit l'intera pagina |
| `verifica_contrasti.py` | controlla i contrasti WCAG su tutte le combinazioni di tema |
| `verifica_facsimile.py` | controlli sul PDF generato |
| `verifica_menu.py` | apre tutte le pagine e controlla che ogni tendina di dati sia alfabetica per descrizione (le eccezioni volute sono elencate nel file) |

### Analisi funzionale continua

[CLAUDE.md](CLAUDE.md) e [docs/miglioramenti.md](docs/miglioramenti.md):
mentre si lavora su qualunque parte del progetto, i punti dove un
invariante potrebbe rompersi (non idee stilistiche: casi concreti — "se
succede X, questo campo mente") si annotano nel secondo file invece di
perdersi in una conversazione. Le voci risolte si spostano in "Fatti",
quelle rifiutate in "Scartati", così non si ridiscutono da zero.
