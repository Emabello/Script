# Istruzioni permanenti per Claude Code su questo progetto

B2F Hub — vedi [README.md](README.md) per l'architettura completa. Questo
file contiene solo le convenzioni operative che vanno seguite ad ogni
sessione, non ripetute in chat ogni volta.

## Routine di analisi funzionale — `docs/miglioramenti.md`

Ogni volta che lavori su questo progetto (bug fix, nuova funzionalità,
audit richiesto dall'utente) e nel farlo ragioni su un flusso di dati e
noti un punto dove un invariante potrebbe rompersi — anche se non è il
motivo per cui sei lì — annotalo in
[docs/miglioramenti.md](docs/miglioramenti.md), sezione "Aperti".

**Cosa conta come voce da annotare**: solo scoperte che nascono da un
ragionamento funzionale concreto — "questo campo dovrebbe garantire X,
ma se succede Y quella garanzia si rompe, e il danno concreto è Z" — non
preferenze stilistiche, non refactoring cosmetici, non idee generiche.
Se non riesci a scrivere un caso concreto che si rompe, non è una voce.

**Cosa NON fare**: non trasformarla in un esercizio a sé stante ("adesso
mi fermo e cerco miglioramenti"). Emerge da un lavoro già in corso per
un altro motivo — è la stessa disciplina con cui in questa sessione sono
nate le voci in README §7 "Le trappole del database".

**Quando una voce viene risolta**, spostala da "Aperti" a "Fatti
(storico)" nello stesso file, con una riga sola su cosa e' cambiato.
Se una proposta viene esplicitamente rifiutata dall'utente, spostala in
"Scartati (e perché)" — così non si ripropone da zero la sessione dopo.

## Altre convenzioni stabilite

- **Menù a tendina**: ogni menù che elenca *dati* (categorie,
  sottocategorie, clienti, metodi di pagamento, tipi di movimento,
  clienti/progetti/task delle ore, calendari) si ordina alfabeticamente
  per la descrizione mostrata, usando `shared/ordina.py` — mai `sorted()`
  crudo (sbaglia con gli accenti) e mai le colonne `ordine` del database.
  Restano nella loro sequenza naturale i menù in cui l'ordine è
  informazione: mesi, anni, stati della fattura, scenari di
  accantonamento. Quando aggiungi un menù, lancia
  `python3 tools/verifica_menu.py`: apre tutte le pagine e lo controlla.

- **Schema Supabase**: ogni volta che una migrazione viene applicata,
  aggiorna [docs/schema_supabase.md](docs/schema_supabase.md) con la
  foto aggiornata dello schema (istruzioni di ispezione in README §8.5).
- **Test**: usa `tools/preview.py` (client Supabase finto, dati
  realistici) per verificare le modifiche senza toccare il database
  reale, prima di proporle o committarle.
- **Migrazioni SQL**: vanno in README §8, numerate in sequenza, sempre
  idempotenti (rilanciabili senza danni). Non lanciarle tu: l'utente le
  esegue lui nell'SQL Editor di Supabase.
