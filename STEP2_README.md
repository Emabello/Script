# Step 2 — Tabelle Supabase + health endpoint

## Cosa contiene questo pacchetto

- `migration_step2.sql`  — script SQL per creare 3 tabelle su Supabase
- `app.py`               — SOSTITUISCE `Script/app.py`
- `views_fatture.py`     — SOSTITUISCE `Script/fatture/views.py` (rinominalo!)
- `views_spese.py`       — SOSTITUISCE `Script/spese/views.py`   (rinominalo!)

## Ordine operazioni

### 1. Lancia lo script SQL su Supabase

- Apri il tuo progetto Supabase (quello che ha già la tabella `spese`)
- Sidebar → **SQL Editor** → *New query*
- Incolla tutto il contenuto di `migration_step2.sql`
- Bottone **RUN** in basso a destra
- Devi vedere `Success. No rows returned.` per ogni CREATE, e un
  `INSERT 0 1` per l'emittente (o `INSERT 0 0` se rilanci: idempotente)

Verifica dalla sidebar → **Table Editor** che siano comparse:
- `b2f_emittente` (1 riga con nome/cognome tuoi)
- `b2f_clienti`   (vuota)
- `b2f_fatture`   (vuota)

### 2. Personalizza l'emittente (opzionale ma consigliato ORA)

Sempre nell'SQL Editor, aggiorna la riga emittente con i tuoi dati
veri (PIVA, indirizzo, IBAN, ecc.):

```sql
update b2f_emittente set
  piva = 'IT________________',
  cf   = 'BLLMNL__________',
  denominazione = 'Emanuele Bellotti',
  indirizzo = 'Via ...',
  cap = '20___',
  comune = 'Milano',
  provincia = 'MI',
  email = 'ebellotti01@gmail.com',
  pec = '...@pec.it',
  iban = 'IT__A________________',
  cassa_prev = 'Gestione Separata INPS'
where id = 1;
```

Se preferisci farlo dopo dal Table Editor cliccando la riga, va bene lo stesso.

### 3. Prendi la Supabase URL e la anon key

- Sidebar → **Project Settings** → **API**
- Copia:
  - `Project URL`  → sarà `SUPABASE_URL` su Render
  - `Project API keys → anon public` → sarà `SUPABASE_KEY` su Render

### 4. Sostituisci i 3 file nel repo locale

Da PowerShell dentro `C:\Users\ebell\Desktop\Lavoro\TS\Script\`:

```powershell
# Copia il nuovo app.py
Copy-Item "$HOME\Downloads\b2f-hub-step2\app.py" -Destination . -Force

# Copia i due views (rinominandoli al percorso finale)
Copy-Item "$HOME\Downloads\b2f-hub-step2\views_fatture.py" `
          -Destination .\fatture\views.py -Force
Copy-Item "$HOME\Downloads\b2f-hub-step2\views_spese.py" `
          -Destination .\spese\views.py -Force
```

(sostituisci `$HOME\Downloads\b2f-hub-step2` col path in cui hai
estratto lo zip di questo step)

### 5. Test in locale (opzionale)

Se vuoi provare in locale, crea temporaneamente un `.env` accanto ad
`app.py`:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJ...la anon key...
```

Poi:

```powershell
$env:SUPABASE_URL = "https://xxxx.supabase.co"
$env:SUPABASE_KEY = "eyJ..."
python app.py
```

Apri `http://127.0.0.1:5000/spese` e `http://127.0.0.1:5000/fatture`
— dovresti vedere:
- Fatture: nome emittente + tabellina con `b2f_emittente=1`, `b2f_clienti=0`, `b2f_fatture=0`
- Spese: conteggio righe della tua `spese` esistente + ultime 5

Endpoint diagnostico:  `http://127.0.0.1:5000/health` → JSON con tutti gli stati.

### 6. Push + configura Render

```powershell
git add .
git commit -m "step 2: tabelle b2f su Supabase + health endpoint"
git push
```

Su Render → **Environment** aggiungi (o aggiorna, se le hai messe vuote):

```
SUPABASE_URL = https://xxxx.supabase.co
SUPABASE_KEY = eyJ...anon key...
```

Salva → Render riavvia il servizio → aspetta ~1 minuto → apri
`https://tuo-servizio.onrender.com/health`

Se vedi tutti i `"ok": true` sulle 4 tabelle, siamo pronti per lo **Step 3**
(anagrafica clienti — form nuova, elenco, edit, delete soft).
