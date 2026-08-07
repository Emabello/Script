# B2F Hub

Gestionale personale per una partita IVA in regime forfettario, con tre aree:
le **ore** lavorate, le **fatture** (con la parte fiscale) e le **spese**
personali. Gira su Flask, tiene i dati su Supabase, sta online su Render.

Il filo che tiene insieme tutto è il denaro: le ore diventano una fattura, la
fattura incassata finisce sul conto P.IVA, una parte va accantonata per il
fisco e il resto si sposta sul conto personale. L'app segue questo percorso
per intero.

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

shared/                pezzi comuni
  design.py              design system: token, CSS, icone
  theme.py               scheletro di pagina, navigazione, tema chiaro/scuro
  fmt.py                 formattatori italiani (euro, percentuali, date)
  pdfgen.py              generazione del facsimile PDF (jsPDF nel browser)
  supabase_client.py     client Supabase
  webauthn.py            sblocco biometrico

tools/                 utilità di sviluppo (non servono in produzione)
static/                font e jsPDF ospitati dall'app
```

Le pagine sono HTML generato da Python: niente framework frontend, niente
build. Il JavaScript è quello che serve nella pagina, scritto inline.

---

## 2. Le tre aree

### Ore — `/ore`

Il timesheet originale (`xs_server.py`), che parla con un portale esterno
tramite `xs_client.py`. È rimasto com'era: la hub gli inietta soltanto
l'intestazione.

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
| `/fatture/spese-piva` | movimenti del conto P.IVA |
| `/fatture/parametri` | aliquote, coefficiente, accantonamento |
| `/fatture/emittente` | dati dell'intestazione |

**Il documento prodotto non è la fattura elettronica.** È il *facsimile* che
va allo studio, che poi predispone e trasmette l'XML allo SDI. Per questo il
PDF si intitola FACSIMILE e lo dichiara in calce.

### Spese — `/spese`

| Rotta | Cosa fa |
|---|---|
| `/spese` | dashboard: saldo del mese, ultimi movimenti, quanto è arrivato dalla P.IVA |
| `/spese/movimenti` | elenco con filtri per anno, mese, tipo, categoria, testo |
| `/spese/movimenti/nuovo` | nuovo movimento |
| `/spese/movimenti/<id>` | modifica |
| `/spese/risparmi` | periodi di stipendio, risparmio consigliato ed effettivo |

API JSON: `/spese/api/movimenti` (GET, POST, PATCH, DELETE),
`/spese/api/categorie`, `/spese/api/risparmi` (GET, PATCH).

---

## 3. Il modello dei dati

### Tabelle dell'app

| Tabella | Contenuto |
|---|---|
| `b2f_emittente` | riga unica: i tuoi dati, più nome e mail dello studio |
| `b2f_clienti` | anagrafica clienti |
| `b2f_fatture` | i documenti, con stato, date dei passaggi e ripartizione |
| `b2f_spese_piva` | movimenti del conto P.IVA |
| `b2f_parametri_fiscali` | riga unica: aliquote e parametri di accantonamento |
| `b2f_webauthn_credentials` | credenziali dello sblocco biometrico |

### Tabelle del conto personale (preesistenti all'app)

| Tabella | Contenuto |
|---|---|
| `spese` | i movimenti personali |
| `cfg_categorie` · `cfg_sottocategorie` | le voci |
| `cfg_categoria_sottocategoria` | gli accoppiamenti ammessi fra le due |
| `impostazioni` | saldo iniziale, percentuale di risparmio, quote di destinazione |
| `risparmi_periodo` | quanto hai messo via davvero, per periodo |

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

### Bollo

Dovuto sopra i 77,47 €, importo 2,00 €. Può essere addebitato al cliente
oppure restare a carico dell'emittente.

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
tipo = 'entrata' and categoria <> 'Stipendio'
```

Su una riga **senza categoria** quel confronto non è falso: è `NULL`. Il
movimento non entra né fra le entrate contate né fra le escluse — sparisce. Il
denaro risulterebbe sul conto ma il *Risparmio consigliato* verrebbe calcolato
su una base più bassa del vero, senza alcun errore visibile.

Per questo il giroconto usa una categoria dedicata, **e non `Stipendio`**:
`v_periodi_stipendio` usa proprio quelle entrate per delimitare i periodi, e
marcarlo così aprirebbe un periodo fasullo sfasando tutto lo storico.

### Il tipo dà la direzione, non il segno

Gli importi sono sempre positivi. La direzione la dà `tipo`. Due convenzioni
sovrapposte si annullerebbero a vicenda.

### Il giroconto ha segno opposto sui due conti

Sul conto P.IVA è un'uscita, sul personale un'entrata. Il saldo di ciascuna
sezione ne tiene conto separatamente.

---

## 8. Migrazioni da eseguire

Da lanciare nell'**SQL Editor di Supabase**, in quest'ordine. Sono tutte
idempotenti: rilanciarle non fa danni.

Lo schema fino al ciclo di vita e alla ripartizione è già applicato. Restano
queste tre.

### 8.1 — Categoria del giroconto sul conto personale

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

### 8.2 — Vista fiscale riallineata e Row Level Security

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

### 8.3 — Dati dell'emittente

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

### 8.4 — Ispezionare lo schema

Quando serve verificare com'è fatto davvero il database (è così che sono
emersi i disallineamenti qui sopra):

```sql
select riga from (
  select 1 as s, table_name || lpad(ordinal_position::text, 4, '0') as k,
         'COL   ' || rpad(table_name || '.' || column_name, 46) ||
         rpad(data_type, 26) || ' null=' || is_nullable ||
         ' ident=' || is_identity || ' def=' || coalesce(column_default, '-') as riga
  from information_schema.columns where table_schema = 'public'
  union all
  select 2, conrelid::regclass::text || conname,
         'VINC  ' || rpad(conrelid::regclass::text, 30) ||
         rpad(conname, 44) || pg_get_constraintdef(oid)
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

---

## 9. Sicurezza

**Accesso all'app.** PIN, più sblocco biometrico via WebAuthn. Le rotte `/api/*`,
`/fatture/api/*` e `/spese/api/*` sono protette dal gate in `xs_server.py`.

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

### Utilità in `tools/`

| Strumento | Cosa fa |
|---|---|
| `preview.py` | monta l'app con un finto client Supabase e dati realistici, per guardare le schermate senza toccare il database |
| `verifica_layout.py` | cerca overflow orizzontali, che sui browser mobili mandano in shrink-to-fit l'intera pagina |
| `verifica_contrasti.py` | controlla i contrasti WCAG su tutte le combinazioni di tema |
| `verifica_facsimile.py` | controlli sul PDF generato |
