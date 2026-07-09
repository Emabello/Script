# Step 1 — Refactor scheletro (rischio zero)

Questo pacchetto aggiunge la struttura hub sopra il timesheet
esistente. **Non tocca la logica di `xs_server.py`**: applica solo due
patch chirurgiche (navbar + gate esteso).

## Cosa contiene

```
Script/
├── app.py                       ← NUOVO entry point Flask
├── apply_patch.py               ← script one-shot per xs_server.py
├── Procfile                     ← MODIFICATO: gunicorn app:app
├── render.yaml                  ← MODIFICATO: nome b2f-hub + env Supabase
├── requirements.txt             ← MODIFICATO: aggiunto supabase
├── shared/
│   ├── nav.py                   ← navbar comune
│   └── supabase_client.py       ← client SB con fallback graceful
├── fatture/
│   └── views.py                 ← landing placeholder
└── spese/
    └── views.py                 ← landing placeholder
```

## Cosa NON contiene (resta nel tuo repo)

- `xs_server.py`  — lo modifichi con `apply_patch.py`
- `xs_client.py`  — non si tocca

## Passi

1. **Sovrapponi** i file di questo pacchetto al tuo repo `Script/`.
2. Da terminale, dentro `Script/`:
   ```
   python apply_patch.py --dry-run   # solo per vedere cosa cambia
   python apply_patch.py             # applica (crea xs_server.py.bak)
   ```
3. Prova in locale (senza Supabase/PIN):
   ```
   pip install -r requirements.txt
   python app.py
   ```
   Vai su http://127.0.0.1:5000/ — vedi la navbar sopra il timesheet.
   Vai su /fatture e /spese — vedi le landing placeholder.
4. Commit + push su GitHub.
5. Su Render:
   - Aggiungi le due nuove env vars: `SUPABASE_URL`, `SUPABASE_KEY`
     (per ora puoi lasciarle vuote se non hai ancora il progetto SB —
     la app parte lo stesso, la sezione /spese dirà "non configurato")
   - Rinomina il servizio da `le-mie-ore` a `b2f-hub` (o quello che
     preferisci) — Impostazioni → Name.
   - Il redeploy parte da solo al push.

## Cosa aspettarsi dopo il deploy

- La tua PWA `Le mie ore` installata sul telefono continuerà a
  funzionare all'URL originale finché non rinomini il servizio.
  Dopo il rename dovrai reinstallarla al nuovo URL (una volta sola).
- Il timesheet gira **identico** a prima: stesse rotte, stesse API,
  stesso PIN.
- Le pagine `/fatture` e `/spese` mostrano solo la landing (per ora).

## Rollback in 30 secondi

Se qualcosa va storto:
```
mv xs_server.py.bak xs_server.py
```
e nel Procfile torna a `web: gunicorn -w 1 xs_server:app`.
Sei tornato allo stato di prima.

## Prossimo passo (Step 2)

Creare su Supabase le tabelle `b2f_clienti` e `b2f_fatture` con lo
schema che avevamo definito, e collegare `SUPABASE_URL`/`SUPABASE_KEY`.
