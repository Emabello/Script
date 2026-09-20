---
name: fiori
description: Regole di design SAP Fiori (tema Horizon) applicate a B2F Hub, che genera HTML e CSS da f-string Python. Usala ogni volta che tocchi l'aspetto o la struttura di una pagina — nuove pagine, nuove card, KPI, tabelle, liste, form, colori, spaziature, stati semantici (positivo/critico/negativo), tipografia, densità, breakpoint responsive — e anche quando la richiesta non nomina Fiori ma dice "rendi più chiara questa pagina", "sistema la grafica", "come lo mostro", "questa card non si legge", "va bene questo colore". Contiene i token Horizon veri con i loro valori esatti, la mappatura sui token già esistenti in shared/design.py, e i floorplan Fiori associati alle pagine di questa app.
---

# Fiori, applicato a questa app

`app.py` dichiara «Fiori Launchpad style» fin dal primo commit. Questa
skill trasforma quell'aspirazione in regole verificabili.

**Lo stato attuale**: dal 20/09/2026 la palette **è** quella di Horizon
e i menù a tendina sono un Select Fiori, non la tendina di sistema.
`shared/design.py` porta i valori veri di Morning Horizon (chiaro) ed
Evening Horizon (scuro) presi da `SAP/theming-base-content`, la scala dei
raggi di Fiori (campo 4px, bottone 8, elemento 12, tile 16), le sue ombre
e il blu SAP come accento predefinito. I bottoni sono rettangoli
arrotondati, non pillole. Non è più un'ispirazione: è il tema.

**Quello che resta del progetto, e resta apposta**:

- **il serif nei titoli** (`--display`, Instrument Serif). Fiori userebbe
  il carattere 72. È la firma visiva dell'app: non sostituirlo senza
  chiederlo — è un cambio d'identità, non un dettaglio tecnico;
- **i tre livelli di accento** (`--accent`, `--accent-fill`,
  `--accent-text`). Horizon ha un `sapBrandColor` solo; qui ne servono
  tre perché un colore non può fare grafica a 3:1 e testo piccolo a
  4.5:1, e gli accenti sono quattro più quello Horizon;
- **`--warn` contro `--warn-ind`**. Il critico di Horizon (`#e76500`)
  vale 3,36:1 sul bianco: sotto la soglia del testo piccolo. In Fiori
  quel valore è l'*indicatore* (icone, barre, bordi — contesti da 3:1) e
  il testo critico usa una tinta più scura. Qui la distinzione è
  esplicita;
- **la scala delle spaziature** `--sp-1`…`--sp-9`, che Horizon non
  definisce come token.

Quando aggiungi un colore, il punto di partenza è il token Horizon —
ma **la soglia di contrasto viene prima**: `verifica_contrasti.py` legge
i valori dal CSS vero e li misura su entrambi i temi e tutti gli accenti.
Se un valore ufficiale non passa, si tiene il ruolo e si cambia la tinta,
come per il critico.

## I cinque principi, tradotti in questa app

Fiori poggia su cinque principi (*role-based, adaptive, simple, coherent,
delightful*). Tre hanno conseguenze operative qui:

**Coerente** è il più concreto: lo stesso concetto si mostra allo stesso
modo ovunque. Un saldo è sempre una `.stat` con `.val` e `.lbl`; un
elenco di oggetti è sempre una `.list` di `.item`; una scomposizione che
deve quadrare è sempre `.rows.detail` con `.row.tot` a chiudere. Se stai
per inventare una quinta forma per mostrare un numero, prima guarda quale
delle quattro esistenti fa già quel lavoro.

**Semplice** è la regola 1-1-3: un utente, un caso d'uso, non più di tre
schermate. Applicata qui: se una pagina risponde a due domande diverse,
sono due pagine — è il motivo per cui «Spese» è stata sciolta e i conti
sono diventati un ramo solo.

**Adattivo** non è «funziona anche sul telefono»: è che la stessa
gerarchia si rende in due modi. Sul desktop la sidebar mostra l'albero
dei conti; sul telefono la tab bar mostra solo il primo livello e
l'albero si apre dentro `/conti`. Stessa struttura, due rese — mai due
strutture diverse.

## Colori: i ruoli prima dei valori

Fiori non ha «il verde» e «il rosso»: ha **ruoli semantici** con un
significato preciso, e usarli fuori ruolo è l'errore più comune.

| Ruolo Fiori | Significato | Token del progetto |
|---|---|---|
| `sapPositiveColor` | l'esito è **buono e finito** | `--pos` / `--pos-soft` |
| `sapNegativeColor` | qualcosa è **rotto o mancante** | `--neg` / `--neg-soft` |
| `sapCriticalColor` | serve **attenzione**, non è un errore | `--warn` / `--warn-soft` |
| `sapNeutralColor` | stato noto, nessun giudizio | `--ink-3` |
| `sapInformativeColor` | evidenzia, non giudica | `--accent` / `--accent-text` |

Le due regole che fanno la differenza:

**Il rosso costa.** In Fiori il negativo è riservato a ciò su cui si deve
agire. Un numero che è semplicemente sceso non è negativo: è un numero.
In questa app è già successo — la card della ripartizione diceva «Manca
ancora € 2,00» in rosso su una differenza da competenze bancarie, e il
campo si chiamava `manca` invece di `scarto`. Prima di colorare di rosso,
chiediti: **c'è qualcosa da fare?** Se no, è neutro.

**Il colore non è mai l'unica informazione.** Un chip verde deve dire
anche «fatta»; una riga rossa deve avere un testo che spiega. È
accessibilità, ma soprattutto è quello che rende leggibile uno
screenshot in bianco e nero o un occhio daltonico.

I valori esatti di Horizon (chiaro e scuro) e la loro resa nei token del
progetto stanno in `references/tokens.md`. Leggilo quando devi scegliere
un colore nuovo o giustificarne uno esistente.

**Sui gradienti**: Horizon è un tema piatto. I gradienti qui sono
volutamente al limite del percettibile — un velo sul fondo delle card,
un filo di profondità sui bottoni, uno stacco sulla shell — e servono a
separare le superfici senza alzare le ombre. Spingerli è il modo più
rapido di smettere di essere Fiori. Ognuno ha **prima** la sua
dichiarazione a tinta piena: `color-mix()` non è supportato ovunque, e
una dichiarazione non capita viene scartata — senza il fallback
resterebbe testo su niente.

## Tipografia: la scala, non il carattere

Horizon usa il carattere proprietario **72**, con `sapFontSize` a
`.875rem` (14px) come base e sei livelli di intestazione (3rem, 2rem,
1.5rem, 1.25rem, 1rem, .875rem).

Questa app usa **Inter** per il testo e **Instrument Serif** per i
titoli. È l'ultima divergenza rimasta dopo la conversione della palette,
ed è **voluta**: il serif nei titoli è la firma visiva del progetto, e
Fiori non ce l'ha. Non sostituirlo di tua iniziativa.

Quello che si prende è la **disciplina della scala**: pochi livelli
dichiarati, nessuna dimensione inventata sul posto. Se stai per scrivere
`font-size:15px` inline, o il livello esiste già in `design.py` o ne
manca uno — e allora si aggiunge lì, con un nome, non nella pagina.

Il dettaglio Fiori che vale sempre: **line-height 1.5** sul testo
continuo o che va a capo (è anche una raccomandazione WCAG). Su una riga
sola — un numero, un'etichetta — si può stringere.

> Il carattere 72 è distribuito sotto Apache-2.0 nel repo
> `SAP/theming-base-content`. Se un giorno si volesse adottarlo davvero,
> è possibile: ma sarebbe un cambio di identità dell'app, non un
> dettaglio tecnico. Da decidere con l'utente, non da fare di slancio.

## Densità e spaziatura

Fiori ha due densità: **cozy** (`sapElement_Height: 2.25rem` = 36px,
pensata per il dito) e **compact** (`1.625rem` = 26px, per mouse e
tastiera). Questa app è **cozy ovunque**, ed è giusto: si usa dal
telefono. Un bersaglio toccabile non scende sotto ~44px di area utile —
per questo la «i» è un cerchio da 16px con un bersaglio invisibile da
34px.

Le spaziature vengono dalla scala `--sp-1`…`--sp-9`. Non scrivere
`margin:13px`: o c'è già il gradino giusto, o il salto che stai facendo
non è quello che credi.

## I floorplan: che forma ha una pagina

Fiori non lascia inventare il layout: ci sono **page type** noti, e ogni
pagina è uno di quelli. Tutti poggiano sulla **dynamic page** — titolo
fisso in alto con le azioni globali, contenuto scorrevole, barra
inferiore opzionale per le azioni che chiudono. È esattamente quello che
fa `render_page()` con `topbar` + `content` + `fab`.

La mappatura fra i floorplan Fiori e le pagine di questa app — e cosa
implica ciascuno — sta in `references/floorplans.md`. **Leggilo prima di
creare una pagina nuova**: la domanda giusta non è «come la disegno» ma
«di che tipo è», e il tipo decide quasi tutto il resto.

In sintesi:

| Pagina di B2F | Floorplan Fiori |
|---|---|
| `/` | Overview page (launchpad) |
| `/conti`, `/impostazioni`, `/fatture` | Overview / landing con liste di navigazione |
| `/conti/webank/personale`, `/fatture/storico` | List report (filtri + elenco + KPI) |
| `/fatture/<id>`, `/conti/webank/piva/<id>` | Object page |
| `/fatture/nuova`, i form | Object page in modifica |
| `/risparmi`, `/fatture/situazione` | Analytical / overview |

## Le regole che in questa app si rompono più spesso

**Le parti stanno sotto il totale, non accanto.** Una scomposizione si
legge dall'alto: addendi rientrati (`.row.voce`), totale che chiude
(`.row.tot`). Metterli allo stesso livello, tutti col meno, li fa
sembrare sottratti due volte — è successo sia nel dettaglio dei Risparmi
sia nella formazione dei saldi.

**Una cascata deve quadrare a vista.** Se mostri le parti di un totale,
la loro somma deve fare il totale. Quando le categorie note non lo
coprono, serve una riga residua («Non ripartiti», «Altre uscite») che
chiuda sempre la differenza. Un dettaglio che non torna col numero
accanto distrugge la fiducia in entrambi.

**Le spiegazioni vanno dietro la «i», i dati no.** `design.py::info()`
esiste per togliere dalle righe i sottotitoli grigi senza buttare via
quello che dicevano. Ma «incassata il 10/07» o «12,4% delle uscite` sono
**valori**, non commenti: quelli restano visibili. La distinzione è: se è
un numero o una data del dominio, si vede; se è una frase che spiega
perché, va dietro la «i».

**I menu di dati si ordinano, i menu di sequenze no.** Convenzione già
scritta in `CLAUDE.md`: categorie, clienti, metodi di pagamento passano
da `shared/ordina.py`; mesi, anni, stati della fattura, periodi di
stipendio restano nel loro ordine naturale, e vanno dichiarati in
`ECCEZIONI` di `tools/verifica_menu.py` col motivo.

**I menu sono già un componente Fiori: non scrivertene un altro.** Ogni
`<select>` della shell viene innestato da `shared/theme.py::_SELECT_JS`
in un Select in stile Fiori — campo chiuso con icona e valore, pannello
con titolo, riga di aiuto e ricerca sopra le otto voci; foglio dal basso
sotto i 720px, lista ancorata al campo sopra. Quindi:

- **scrivi un `<select>` normale**, con le sue `<option>`: l'innesto è
  automatico e il select vero resta nel DOM a tenere il valore (gli
  `onchange` inline scattano come prima);
- **arricchisci con le `data-*`** invece di inventare markup: sulla
  `<option>` `data-icona` (emoji), `data-titolo`, `data-breve` (il testo
  del campo chiuso, quando quello completo è troppo lungo), `data-sub`,
  `data-nota` + `data-stato` (`pos`/`warn`/`neg`/`accent`), `data-info`
  (il valore a destra); sul `<select>` `data-etichetta` (titolo del
  pannello), `data-icona`, `data-aiuto`;
- **metti nelle `data-*` quello che serve a distinguere le voci**, non
  quello che serve a decorarle. Nel menu dei periodi di paga sono
  estremi e stato: senza, due periodi dello stesso mese si leggono come
  un doppione;
- `data-nativo` rinuncia all'innesto. Usalo solo dove un pannello per
  riga sarebbe peggio della tendina (le tabelle dense dell'import), mai
  per gusto.

**Le emoji di stato sono informazione, non decorazione.** In un elenco
lungo sono il primo appiglio: ✅ fatto, 🟡 fatto ma sotto la soglia,
⚠️ da fare, ⏳ ancora in corso, 🔒 chiuso. Vanno **sempre** accompagnate
dalla parola (l'emoji da sola non è accessibile e non si cerca) e non
devono mai contraddire il numero che hanno accanto — la spunta verde su
un periodo saldato per un quinto era esattamente quel guasto.

**Uno stato vuoto non è una pagina rotta.** Ogni sezione dice cosa manca
e come rimediare, mai un blocco bianco o uno zero senza spiegazione.
`tools/verifica_rotte.py` lo verifica su sette scenari di tabelle vuote.

## Prima di dire che hai finito

```
python3 tools/verifica_contrasti.py   # ogni combinazione sopra soglia WCAG
python3 tools/verifica_layout.py      # nessun overflow da 320px a 430px
python3 tools/verifica_js.py          # nessuno script spento da un apostrofo
python3 tools/verifica_menu.py        # menu ordinati, eccezioni dichiarate
python3 tools/verifica_rotte.py       # rotte, tabelle vuote, payload sbagliati
```

Il contrasto in particolare non è negoziabile ed è il motivo per cui
esistono tre varianti di accento (`--accent`, `--accent-fill`,
`--accent-text`): un colore solo non può fare grafica a 3:1 e testo
piccolo a 4.5:1.
