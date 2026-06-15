# Le mie ore — messa online (Render)

Obiettivo: avere l'app sempre disponibile sul telefono, anche a PC spento e
fuori casa, protetta da un PIN.

I file del progetto sono:
- `xs_client.py` — il motore che parla con XS
- `xs_server.py` — il server web / app
- `requirements.txt`, `render.yaml`, `Procfile` — servono a Render
- questa guida

---

## Passo 1 — Metti il progetto su GitHub (da VS Code)

Render prende il codice da GitHub.

1. Crea un account gratuito su https://github.com (se non ne hai uno).
2. In VS Code apri la cartella del progetto (File > Apri cartella).
3. Apri il pannello "Controllo del codice sorgente" (icona dei rami a sinistra).
4. Clicca **Pubblica su GitHub** (Publish to GitHub).
   - Scegli **repository privato** (importante: così il codice non è pubblico).
   - VS Code carica tutti i file da solo.

Se VS Code ti chiede di installare Git o di fare login a GitHub, segui le
indicazioni a schermo: è un'autorizzazione una tantum.

---

## Passo 2 — Crea il servizio su Render

1. Crea un account gratuito su https://render.com (puoi entrare con GitHub).
2. Nella dashboard: **New +** > **Web Service**.
3. Collega il tuo account GitHub e seleziona il repository appena creato.
4. Render legge il file `render.yaml` e propone già le impostazioni giuste:
   - Runtime: Python
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn -w 1 xs_server:app`
   - Piano: **Free**
   Se non le legge in automatico, impostale a mano con questi valori.

---

## Passo 3 — Imposta le variabili d'ambiente (la "configurazione")

Qui inserisci le credenziali: NON vanno nei file, ma nelle impostazioni di
Render (sezione **Environment** del servizio). Aggiungi:

| Nome        | Valore                                   |
|-------------|------------------------------------------|
| `XS_USER`   | il tuo username di XS                     |
| `XS_PASS`   | la tua password di XS                     |
| `APP_PIN`   | un PIN scelto da te (es. 4-6 cifre)       |
| `SECRET_KEY`| generato in automatico da render.yaml     |

- `XS_USER` / `XS_PASS`: servono al server per loggarsi in XS al posto tuo.
- `APP_PIN`: è il codice che proteggerà l'app. Senza, chiunque apra l'indirizzo
  entrerebbe come te. Con il PIN, chi non lo conosce resta fuori.

Salva. Render farà il primo **deploy** (qualche minuto).

---

## Passo 4 — Ottieni l'indirizzo e provalo

A fine deploy Render ti dà un indirizzo tipo:

    https://le-mie-ore.onrender.com

Aprilo dal browser: ti chiederà il PIN. Inserito quello, vedi l'app.

---

## Passo 5 — Installa l'app sul telefono

Apri quell'indirizzo `https://...onrender.com` dal telefono:

- **iPhone (Safari)**: pulsante Condividi > "Aggiungi a Home".
- **Android (Chrome)**: menu ⋮ > "Installa app".

Avrai l'icona sulla home. Il PIN te lo chiede una volta e poi resta sbloccata
(per circa 6 mesi, salvo logout o cancellazione dati del browser).

---

## Cose da sapere

- **Risveglio lento**: sul piano gratuito l'app si "addormenta" dopo ~15 minuti
  di inattività e al primo accesso ci mette ~30-60 secondi a ripartire. Le volte
  successive è immediata. Con un piano a pagamento (pochi euro/mese) resta sempre
  sveglia.
- **Cambiare credenziali o PIN**: si fa cambiando le variabili d'ambiente su
  Render (poi il servizio si riavvia).
- **Aggiornare l'app**: ogni volta che modifichi i file e fai "push" da VS Code,
  Render ricarica e aggiorna l'app da solo.
- **Sicurezza**: tieni il repository GitHub **privato** e non condividere il PIN.
