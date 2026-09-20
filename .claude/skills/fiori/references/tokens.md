# I token di Horizon, e cosa diventano qui

Valori presi dal tema `sap_horizon` (Morning Horizon, chiaro) e
`sap_horizon_dark` (Evening Horizon, scuro) di
[`SAP/theming-base-content`](https://github.com/SAP/theming-base-content),
Apache-2.0, file `content/Base/baseLib/<tema>/css_variables.css`.

## Indice

- [Colori semantici](#colori-semantici)
- [Superfici e testo](#superfici-e-testo)
- [Tipografia](#tipografia)
- [Raggi, altezze, ombre](#raggi-altezze-ombre)
- [Breakpoint](#breakpoint)
- [Come leggere gli scarti](#come-leggere-gli-scarti)

## Colori semantici

| Token Horizon | Morning (chiaro) | Evening (scuro) | Token qui |
|---|---|---|---|
| `--sapPositiveColor` | `#256f3a` | `#97dd40` | `--pos` — **identici** |
| `--sapNegativeColor` | `#aa0808` | `#fa6161` | `--neg` — **identici** |
| `--sapCriticalColor` | `#e76500` | `#ffdf72` | `--warn-ind` (indicatore) |
| — | `#b04600` | `#ffdf72` | `--warn` (testo, vedi sotto) |
| `--sapNeutralColor` | `#788fa6` | `#a9b4be` | `--ink-3` (`#556b82` / `#8396a8`) |
| `--sapInformativeColor` | `#0070f2` | `#4db1ff` | `--accent` (accento Horizon) |
| `--sapPositiveBackground` | `#f5fae5` | `#11331a` | `--pos-soft` — **identici** |
| `--sapNegativeBackground` | `#ffeaf4` | `#350000` | `--neg-soft` — **identici** |
| `--sapCriticalBackground` | `#fff8d6` | `#382700` | `--warn-soft` — **identici** |
| `--sapNeutralBackground` | `#eff1f2` | `#242e38` | `--surface-3` — **identici** |
| `--sapInformationBackground` | `#e1f4ff` | `#00144a` | `--accent-soft` (Horizon) |

**L'unico scostamento, e il suo perché.** Il critico `#e76500` vale
3,36:1 sul bianco e 3,14:1 sul proprio chip: sotto la soglia 4,5 del
testo piccolo. In Fiori quel valore è l'**indicatore** — icone, barre,
bordi, contesti da 3:1 — e il testo critico usa una tinta più scura. Qui
i due ruoli hanno due token: `--warn-ind` resta `#e76500`, `--warn` è
`#b04600` (5,64:1 su card, 5,28:1 sul chip). È lo stesso ragionamento di
Fiori, reso esplicito.

I fondi semantici sono **tinte piene** e non `rgba`, come in Horizon: un
chip su fondo pieno resta leggibile sopra una card di colore diverso,
mentre un `rgba` cambia resa a seconda di cosa ha sotto.

## Superfici e testo

| Token Horizon | Morning | Evening | Token qui |
|---|---|---|---|
| `--sapBackgroundColor` | `#f5f6f7` | `#12171c` | `--bg` — **identici** |
| `--sapShellColor` | `#fff` | `#1d232a` | `--surface` — **identici** |
| `--sapGroup_ContentBackground` | `#fff` | `#1d232a` | `--surface` |
| `--sapList_Background` | `#fff` | `#1d232a` | `--surface` |
| `--sapTile_Background` | `#fff` | `#1d232a` | `--surface` |
| `--sapPageHeader_Background` | `#fff` | `#1d232a` | `--surface` |
| `--sapTextColor` | `#131e29` | `#f5f6f7` | `--ink` — **identici** |
| `--sapTitleColor` | `#131e29` | `#f5f6f7` | `--ink` |
| `--sapContent_LabelColor` | `#556b82` | `#8396a8` | `--ink-3` — **identici** |
| `--sapContent_ForegroundBorderColor` | `#758ca4` | `#a9b4be` | `--line-strong` |
| `--sapBrandColor` | `#0070f2` | `#0070f2` | — (qui l'accento è scelto dall'utente) |
| `--sapHighlightColor` | `#0064d9` | `#4db1ff` | `--accent-hi` |
| `--sapLinkColor` | `#0064d9` | `#008fff` | `--accent-text` |

**La differenza strutturale che resta**: Horizon ha *un* colore di
marchio, blu SAP. Qui l'accento **Horizon** lo porta (`--accent-fill:
#0070f2`, `--accent-text: #0064d9` chiaro / `#4db1ff` scuro) ed è il
predefinito, ma restano scegliibili indigo, blu, viola e grafite — e per
ciascuno servono **tre** varianti, perché un solo valore non può servire
grafica (≥3:1) e testo piccolo (≥4.5:1). Più rigorosa di Fiori, non un
ritardo: non appiattirla su un colore solo.

Nota verificata: `#0070f2` con testo bianco fa **4,57:1** — passa la
soglia del testo piccolo per un soffio, quindi può fare da riempimento.
Per il testo su card si usa `sapHighlightColor`, che in Horizon è anche
il colore dei link.

## Tipografia

| Token Horizon | Valore | Qui |
|---|---|---|
| `--sapFontFamily` | `"72", "72full", Arial, …` | `--sans` (Inter) |
| `--sapFontSize` | `.875rem` (14px) | 14–14.5px sul corpo |
| `--sapFontSmallSize` | `.75rem` (12px) | `.small` 13px, `.micro` 11.5px |
| `--sapFontLargeSize` | `1rem` (16px) | — |
| `--sapFontHeader1Size` | `3rem` (48px) | — |
| `--sapFontHeader2Size` | `2rem` (32px) | `.h1` = `clamp(23px,5vw,30px)`, con `--display` |
| `--sapFontHeader3Size` | `1.5rem` (24px) | — |
| `--sapFontHeader4Size` | `1.25rem` (20px) | `.h2` 17px |
| `--sapFontHeader5Size` | `1rem` (16px) | `.h3` 15px |
| `--sapFontHeader6Size` | `.875rem` (14px) | `.eyebrow` 11px maiuscoletto |
| `--sapFontHeaderFamily` | `"72-Bold"` | `--display` (Instrument Serif) |
| `--sapContent_MonospaceFontFamily` | `"72Mono"` | `--mono` (di sistema) |

Horizon ha **sei** livelli di intestazione perché serve app enterprise
con gerarchie profonde. Qui ne bastano tre più l'`eyebrow`: la gerarchia
è più corta, e aggiungerne senza un bisogno reale peggiora la coerenza
invece di migliorarla.

## Raggi, altezze, ombre

| Token Horizon | Valore | Qui |
|---|---|---|
| `--sapField_BorderCornerRadius` | `.25rem` (4px) | `--r-field` 4px |
| `--sapButton_BorderCornerRadius` | `.5rem` (8px) | `--r-xs` 8px |
| `--sapElement_BorderCornerRadius` | `.75rem` (12px) | `--r-sm` 12px |
| `--sapTile_BorderCornerRadius` | `1rem` (16px) | `--r-md` 16px |
| `--sapElement_Height` (cozy) | `2.25rem` (36px) | bottoni ~36–40px |
| `--sapElement_Compact_Height` | `1.625rem` (26px) | non usata: qui è tutto cozy |
| `--sapContent_Shadow0` | ombra leggera a due strati | `--e1` |
| `--sapContent_Shadow1` | + bordo a 1px | `--e2` |
| `--sapContent_Shadow2` / `3` | popover, dialoghi | `--e3` |

La scala coincide. `--r-field` è stato aggiunto apposta: in Fiori i campi
sono molto meno arrotondati di tutto il resto, ed è il dettaglio che fa
leggere un form come un form. I **bottoni** sono passati da pillola
(`--r-full`) a rettangolo arrotondato da 8px: è il segno più
riconoscibile di Fiori, e distingue a colpo d'occhio un'azione da un
chip.

## Breakpoint

`sap.ui.Device` definisce due set di intervalli
([openui5/src/sap/ui/Device.js](https://github.com/SAP/openui5/blob/master/src/sap.ui.core/src/sap/ui/Device.js)):

| Set | Soglie | Nomi |
|---|---|---|
| `Std` | 600, 1024 | Phone, Tablet, Desktop |
| `StdExt` | 600, 1024, 1440 | Phone, Tablet, Desktop, LargeDesktop |

Questa app usa **1024px** come unica soglia — sotto: colonna singola +
tab bar; sopra: sidebar + griglia. Coincide con il confine
Tablet/Desktop di Fiori, quindi è già allineata.

A 600px (Phone/Tablet) qui non succede nulla, e per ora va bene: le
griglie sono `auto-fit minmax()`, quindi si riflowano da sole senza
bisogno di una soglia dichiarata. Se un giorno servisse un
comportamento diverso su tablet, **600px è la soglia da usare** — non
640 o 768, per restare sullo stesso sistema.

`verifica_layout.py` controlla da 320px a 430px, cioè il solo Phone.
Se aggiungi un layout che cambia a 600 o a 1440, aggiungi anche le
larghezze corrispondenti a quel controllo.

## Come leggere gli scarti

Dopo la conversione del 20/09/2026 ne restano tre, tutti con una ragione:

- **`--warn` contro `--warn-ind`**: il critico ufficiale non passa la
  soglia del testo piccolo, e Fiori stesso separa i due ruoli;
- **il serif nei titoli**: è l'identità dell'app;
- **i tre livelli di accento**: più rigorosi del singolo `sapBrandColor`.

Quando ne trovi uno nuovo e vuoi chiuderlo, la domanda è: *il valore
ufficiale passa `verifica_contrasti.py`?* Se sì, prendilo. Se no, tieni
il **ruolo** e cambia la tinta — la soglia viene prima del valore, e il
tool legge i colori dal CSS vero, quindi non si può barare.
