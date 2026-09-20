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

| Token Horizon | Morning (chiaro) | Evening (scuro) | Qui |
|---|---|---|---|
| `--sapPositiveColor` | `#256f3a` | `#97dd40` | `--pos` (`#0a7954` / chiaro) |
| `--sapNegativeColor` | `#aa0808` | `#fa6161` | `--neg` (`#c82743`) |
| `--sapCriticalColor` | `#e76500` | `#ffdf72` | `--warn` (`#906111`) |
| `--sapNeutralColor` | `#788fa6` | `#a9b4be` | `--ink-3` |
| `--sapInformativeColor` | `#0070f2` | `#4db1ff` | `--accent` |
| `--sapPositiveBackground` | `#f5fae5` | `#11331a` | `--pos-soft` |
| `--sapNegativeBackground` | `#ffeaf4` | `#350000` | `--neg-soft` |
| `--sapCriticalBackground` | `#fff8d6` | `#382700` | `--warn-soft` |
| `--sapNeutralBackground` | `#eff1f2` | `#242e38` | `--surface-3` |
| `--sapInformationBackground` | `#e1f4ff` | `#00144a` | `--accent-soft` |

Nota su Horizon: il fondo del **negativo** in chiaro è rosato-rosa
(`#ffeaf4`), non rosso pallido — è una scelta per tenerlo distinguibile
dal critico arancione senza gridare. Il progetto usa `rgba(--neg, .12)`,
che ottiene lo stesso effetto con un token in meno.

## Superfici e testo

| Token Horizon | Morning | Evening | Qui |
|---|---|---|---|
| `--sapBackgroundColor` | `#f5f6f7` | `#12171c` | `--bg` (`#f6f7f9` / scuro) |
| `--sapShellColor` | `#fff` | `#1d232a` | `--surface` |
| `--sapGroup_ContentBackground` | `#fff` | `#1d232a` | `--surface` |
| `--sapList_Background` | `#fff` | `#1d232a` | `--surface` |
| `--sapTile_Background` | `#fff` | `#1d232a` | `--surface` |
| `--sapPageHeader_Background` | `#fff` | `#1d232a` | `--surface` |
| `--sapTextColor` | `#131e29` | `#f5f6f7` | `--ink` |
| `--sapTitleColor` | `#131e29` | `#f5f6f7` | `--ink` |
| `--sapContent_LabelColor` | `#556b82` | `#8396a8` | `--ink-3` |
| `--sapContent_ForegroundBorderColor` | `#758ca4` | `#a9b4be` | `--line-strong` |
| `--sapBrandColor` | `#0070f2` | `#0070f2` | — (qui l'accento è scelto dall'utente) |
| `--sapHighlightColor` | `#0064d9` | `#4db1ff` | `--accent-hi` |
| `--sapLinkColor` | `#0064d9` | `#008fff` | `--accent-text` |

**La differenza strutturale che conta**: Horizon ha *un* colore di
marchio, blu SAP. Questa app lascia scegliere l'accento (indigo, blue,
violet, graphite…) e per ciascuno tiene **tre** varianti, perché un solo
valore non può servire grafica (≥3:1) e testo piccolo (≥4.5:1). È una
divergenza deliberata e più rigorosa di Fiori, non un ritardo: non
appiattirla su un colore solo.

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
| `--sapField_BorderCornerRadius` | `.25rem` (4px) | campi: `--r-xs` 8px |
| `--sapButton_BorderCornerRadius` | `.5rem` (8px) | `--r-xs` 8px |
| `--sapElement_BorderCornerRadius` | `.75rem` (12px) | `--r-sm` 12px |
| `--sapTile_BorderCornerRadius` | `1rem` (16px) | `--r-md` 16px |
| `--sapElement_Height` (cozy) | `2.25rem` (36px) | bottoni ~36–40px |
| `--sapElement_Compact_Height` | `1.625rem` (26px) | non usata: qui è tutto cozy |
| `--sapContent_Shadow0` | ombra leggera a due strati | `--e1` |
| `--sapContent_Shadow1` | + bordo a 1px | `--e2` |
| `--sapContent_Shadow2` / `3` | popover, dialoghi | `--e3` |

I raggi coincidono quasi ovunque. L'unico scarto vero è sui **campi**:
Horizon li tiene a 4px, qui sono a 8px. Lasciarli com'è — cambiarli
significherebbe toccare ogni form per un dettaglio che nessuno nota.

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

Gli scarti fra le due colonne non sono debito tecnico da sanare. Quasi
tutti hanno una ragione:

- **i colori semantici** qui sono tarati sul contrasto verificato da
  `verifica_contrasti.py` su *entrambi* i temi e su *tutti* gli accenti;
  i valori Horizon sono tarati sul loro, con un accento solo;
- **il serif nei titoli** è l'identità dell'app;
- **i tre livelli di accento** sono più rigorosi del singolo
  `sapBrandColor`.

Quando trovi uno scarto e vuoi chiuderlo, la domanda è: *sto importando
una regola o un numero?* Le regole di Fiori valgono sempre. I numeri
valgono solo se importi anche tutto il resto.
