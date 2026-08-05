# tools — verifica locale

Strumenti per guardare e collaudare l'app senza toccare il database di
produzione. Non fanno parte dell'app: `app.py` non li importa.

## Perché esistono

Il primo redesign sembrava a posto negli screenshot ma sul telefono era
inutilizzabile: una descrizione lunga (`"pagamento con carta - carta
*2058-mcdonald's 35 milano mi ita"`) allargava il documento oltre la
larghezza dello schermo, il browser applicava lo shrink-to-fit e
rimpiccioliva l'intera pagina.

Non si vedeva perché i dati di prova avevano descrizioni corte e perché
guardare uno screenshot non dice se il documento sfora. Da qui questi tre
strumenti: i dati di prova ora hanno le stringhe lunghe di un estratto
conto vero, e l'overflow si misura invece di stimarlo a occhio.

## Preparazione

```bash
python3.12 -m venv .venv
.venv/bin/pip install flask openpyxl webauthn requests beautifulsoup4 playwright
```

Serve Python 3.12+: il codice usa f-string annidate con lo stesso
delimitatore, che su 3.11 non compilano.

## `preview.py` — l'app con dati finti

Monta l'app vera con un finto client Supabase in memoria. Nessuna
credenziale, nessuna rete, nessun rischio per i dati veri.

```bash
.venv/bin/python tools/preview.py 5055      # poi http://127.0.0.1:5055
```

I dati riproducono le forme che rompono il layout: causali bancarie
lunghissime, ragioni sociali lunghe, importi a cinque cifre. **Se aggiungi
dati di prova, aggiungili brutti**: sono quelli che trovano i bug.

## `verifica_layout.py` — nessun overflow orizzontale

Carica ogni pagina a 320, 360, 390 e 430px e confronta `scrollWidth` con
`clientWidth`. Se il documento sfora, elenca gli elementi colpevoli con
larghezza, bordo destro e testo.

```bash
.venv/bin/python tools/verifica_layout.py   # esce 1 se trova overflow
```

Le due cause quasi sempre sono:

1. **Testo in un elemento inline.** `overflow:hidden` e `text-overflow`
   non si applicano agli elementi inline: se il markup usa `<span>`, il
   troncamento non avviene e la stringa si stende per intero. Nel design
   system le classi di testo troncabile dichiarano `display:block` per
   essere indipendenti dal tag.
2. **Tracce di griglia `1fr` senza `minmax(0, …)`.** `1fr` equivale a
   `minmax(auto, 1fr)`, e `auto` non scende sotto il min-content: una
   riga non spezzabile allarga la colonna oltre lo schermo.

## `verifica_facsimile.py` — il PDF che esce dall'app

Genera il facsimile della fattura di prova, ne estrae il testo e controlla
che ci sia quello che deve esserci.

```bash
.venv/bin/python tools/verifica_facsimile.py   # serve anche pypdf
```

E' l'unico artefatto che lascia l'app e finisce in mano a un altro: lo
studio ci costruisce sopra la fattura elettronica. Se cambia per sbaglio
non se ne accorge nessuno finche' non e' troppo tardi.

Controlla in particolare i numeri dello **scorporo**: su 5.000 concordati
il compenso deve essere 4.807,69 e la rivalsa 192,31, totale 5.002 col
bollo. Se ricomparisse 5.200 vorrebbe dire che e' tornato l'addebito, cioe'
un facsimile che non combacia con la fattura vera.

## `verifica_contrasti.py` — soglie WCAG

Legge i token dal CSS reale (non da una copia riscritta a mano) e
controlla ogni coppia colore/sfondo nei due temi e per i quattro accenti:
testi, semantici, testo sui bottoni pieni, testo dei chip sul proprio
fondo tenue.

```bash
.venv/bin/python tools/verifica_contrasti.py
```

Soglie: 4.5:1 per il testo normale, 3:1 per il testo grande e per gli
elementi decorativi.
