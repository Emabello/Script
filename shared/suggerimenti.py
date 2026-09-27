"""
shared/suggerimenti.py — La categoria proposta, imparata dallo storico.

L'IDEA
------
Ogni movimento gia' categorizzato e' un esempio. Quando ne arriva uno
nuovo — da un estratto o scritto a mano — si cercano quelli che gli
somigliano per **descrizione** e **importo**, e si propone la categoria
che hanno avuto piu' spesso.

Non c'e' una tabella di regole a parte, apposta. Una tabella di regole e'
una seconda copia della verita' («McDonald's = Caffè»), e questo progetto
sa come vanno a finire le seconde copie: divergono, e quella che nessuno
guarda e' sempre la piu' vecchia. Qui la memoria **sono i movimenti
stessi**: correggi la categoria di una riga, e dal movimento dopo il
suggerimento lo sa gia'. Niente da tenere allineato, niente da migrare.

LA DESCRIZIONE
--------------
Le banche scrivono lo stesso esercente in modi diversi, e l'import li ha
ripuliti in modi diversi negli anni:

    pagamento con carta - carta *2058-mcdonald's 35  milano  mi  ita
    Mcdonald'S 35 Mil Ano
    Mcdonald'S Milano

Si confrontano quindi le sole **lettere**, senza spazi (gli spazi in piu'
nel mezzo di «Mil Ano» sono un difetto dell'estratto, non un'informazione),
tolti i pezzi che non dicono niente dell'esercente — «pagamento con
carta», il numero di carta, l'ora, «ita». La somiglianza e' quella dei
trigrammi di lettere (coefficiente di Dice): regge i nomi spezzati, i
suffissi di citta' e gli errori di battitura.

L'IMPORTO
---------
Allo stesso bancone del McDonald's di via 35 lo storico dice: Caffè a
1,10, 2,20, 3,30 — e Cibo a 14,80 e 16,59. La descrizione da sola non
basta a scegliere; l'importo si'. Un esempio pesa di piu' quando il suo
importo e' **lo stesso**, poi quando e' un **multiplo** (due caffe', tre
caffe': 2,20 e 3,30 sono 2 e 3 volte 1,10), e sempre meno man mano che
si allontana. Cosi' 4,40 al McDonald's diventa «Caffè» e 18,00 «Cibo».

LA FIDUCIA
----------
Ogni proposta porta quanto e' sicura (la quota del peso andata alla
categoria scelta) e su quanti esempi si regge. Sotto una soglia la
proposta si mostra ma non si preseleziona: un suggerimento sbagliato
accettato senza guardare e' peggio di nessun suggerimento.
"""
import math
import re
import unicodedata
from datetime import date

# I pezzi di descrizione che non dicono niente dell'esercente: il modo di
# pagamento, la carta, l'ora, il paese. Si tolgono prima del confronto.
_RUMORE = re.compile(
    r"pagamento con carta|spesa pagobancomat|pagobancomat|carta\s*\*?\s*\d+|"
    r"\b\d{1,2}[:.]\d{2}\b|-da contab\w*|\bdigit\b|\bcontactless\b|"
    r"\b(ita|it a|italia|ity)\s*$",
    re.I)

# Sotto questa fiducia la proposta si mostra ma non si applica da sola.
FIDUCIA_MINIMA = 0.6
# Sotto questa somiglianza due descrizioni non sono lo stesso esercente.
SOMIGLIANZA_MINIMA = 0.45
# Quanti esempi vicini votano. Pochi: il punto e' che votino i piu'
# simili, non tutti quelli dello stesso esercente.
VICINI = 7


def chiave(descrizione: str | None) -> str:
    """Le sole lettere della descrizione, minuscole, senza accenti e rumore."""
    s = _RUMORE.sub(" ", str(descrizione or "").lower())
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s)


# Parole che compaiono in descrizioni di esercenti diversissimi e non
# dicono niente di chi e': forme societarie, preposizioni, «bonifico».
_VUOTE = frozenset("""di da del della dei a al alla per con e il la lo le gli
    snc srl spa sas sa srls s r l bonifico favore sdd sepa pagamento carta""".split())


def parole(descrizione: str | None) -> frozenset:
    """Le parole significative della descrizione, senza rumore."""
    s = _RUMORE.sub(" ", str(descrizione or "").lower())
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return frozenset(w for w in re.findall(r"[a-z]{3,}", s) if w not in _VUOTE)


def trigrammi(k: str) -> frozenset:
    if not k:
        return frozenset()
    k = f"  {k} "
    return frozenset(k[i:i + 3] for i in range(len(k) - 2))


def somiglianza(a: frozenset, b: frozenset) -> float:
    """Coefficiente di Dice fra due insiemi di trigrammi, fra 0 e 1."""
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def affinita_importo(nuovo: float, visto: float) -> tuple[float, str | None]:
    """
    Quanto un importo gia' visto parla per quello nuovo, fra 0,15 e 1, e
    perche'. Stesso importo: 1. Multiplo (2..8 volte, o la meta' o un
    terzo): 0,85. Altrimenti decresce col rapporto: il doppio non-multiplo
    vale gia' poco, dieci volte tanto quasi niente.
    """
    if nuovo <= 0 or visto <= 0:
        return 0.3, None
    if abs(nuovo - visto) < 0.005:
        return 1.0, "stesso importo"
    for grande, piccolo, dice in ((nuovo, visto, "multiplo"), (visto, nuovo, "sottomultiplo")):
        n = grande / piccolo
        k = round(n)
        if 2 <= k <= 8 and abs(grande - k * piccolo) < 0.015:
            return 0.85, f"{dice} di € {piccolo:.2f}".replace(".", ",")
    rapporto = abs(math.log(nuovo / visto))
    return max(0.15, 0.7 * math.exp(-1.6 * rapporto)), None


class Storico:
    """
    Gli esempi gia' categorizzati, indicizzati per il confronto.

    `righe`: dict con `descrizione`, `importo`, `tipo`, `data` e
    `etichetta` — l'identita' della categoria (il `categoria_link_id` per
    i conti che usano l'albero `cfg_*`, la chiave per la P.IVA) — piu'
    `nome`, quello da mostrare. Le righe senza descrizione o senza
    etichetta non insegnano niente e si scartano.

    Gli esempi si raggruppano per descrizione ripulita: in un anno lo
    stesso bar compare cento volte, e confrontarlo cento volte con ogni
    riga nuova e' lavoro buttato. Si confronta una volta per esercente.
    """

    def __init__(self, righe: list[dict], oggi: date | None = None):
        self.oggi = oggi or date.today()
        self.nomi: dict = {}
        self._parole: dict[str, frozenset] = {}
        gruppi: dict[str, list] = {}
        for r in righe:
            etichetta = r.get("etichetta")
            k = chiave(r.get("descrizione"))
            if not etichetta or len(k) < 3:
                continue
            try:
                imp = abs(float(r.get("importo") or 0))
            except (TypeError, ValueError):
                continue
            self.nomi[etichetta] = r.get("nome") or str(etichetta)
            self._parole.setdefault(k, parole(r.get("descrizione")))
            gruppi.setdefault(k, []).append(
                (r.get("tipo"), imp, etichetta, str(r.get("data") or "")[:10],
                 r.get("descrizione") or ""))
        self.gruppi = [(k, trigrammi(k), self._parole[k], esempi)
                       for k, esempi in gruppi.items()]
        self._cache: dict = {}

    def __len__(self):
        return sum(len(e) for _k, _t, _p, e in self.gruppi)

    def _peso_tempo(self, quando: str) -> float:
        """Un esempio recente pesa un po' di piu': le abitudini cambiano."""
        try:
            giorni = (self.oggi - date.fromisoformat(quando)).days
        except ValueError:
            return 1.0
        return 1.3 if giorni <= 180 else 1.0

    def _vicini(self, k: str, p: frozenset = frozenset()):
        """
        I gruppi di esempi con una descrizione abbastanza simile. Due
        misure, vince la piu' alta: i trigrammi reggono i nomi spezzati
        («Mil Ano»), le parole reggono l'ordine diverso («Aruba PEC
        rinnovo» e «Rinnovo PEC Aruba»).
        """
        if k in self._cache:
            return self._cache[k]
        t = trigrammi(k)
        out = []
        for kg, tg, pg, esempi in self.gruppi:
            s = 1.0 if kg == k else somiglianza(t, tg)
            if p and pg and s < 1.0:
                s = max(s, 0.95 * len(p & pg) / len(p | pg))
            if s >= SOMIGLIANZA_MINIMA:
                out.append((s, esempi))
        self._cache[k] = out
        return out

    def suggerisci(self, descrizione: str | None, importo, tipo: str | None,
                   ammesse: set | None = None) -> dict | None:
        """
        La categoria proposta per un movimento, o None se lo storico non
        ha niente di abbastanza simile.

        Ritorna {etichetta, nome, fiducia (0..1), esempi, motivo,
        alternative: [(nome, quota)]}. `ammesse` limita le categorie
        proponibili (ogni conto ne esclude qualcuna).
        """
        k = chiave(descrizione)
        if len(k) < 3:
            return None
        try:
            imp = abs(float(importo or 0))
        except (TypeError, ValueError):
            imp = 0.0

        # I VICINI PIU' PROSSIMI, non la maggioranza. Allo stesso bancone
        # ci sono trenta caffe' e sei pranzi: a maggioranza, un pranzo da
        # 15 € diventerebbe un caffe'. Si prendono invece gli esempi piu'
        # vicini insieme per esercente E per importo, e votano solo loro:
        # a 15 € i vicini sono i pranzi da 14,80 e 16,59, a 1,10 i caffe'.
        # Un multiplo esatto (due caffe' = 2,20) conta come vicino.
        candidati = []
        for s, esempi in self._vicini(k, parole(descrizione)):
            for tipo_e, imp_e, etichetta, quando, desc in esempi:
                if tipo and tipo_e and tipo_e != tipo:
                    continue
                if ammesse is not None and etichetta not in ammesse:
                    continue
                a, perche = affinita_importo(imp, imp_e)
                distanza_imp = (0.0 if a >= 1.0 else 0.12 if a >= 0.85
                                else abs(math.log(max(imp, 0.01) / max(imp_e, 0.01))))
                d = 2.5 * (1 - s) + distanza_imp
                candidati.append((d, etichetta, perche, s, desc, quando))
        candidati.sort(key=lambda x: x[0])
        vicini = candidati[:VICINI]

        pesi: dict = {}
        esempi_per: dict = {}
        motivi: dict = {}
        simile: dict = {}
        for d, etichetta, perche, s, desc, quando in vicini:
            w = self._peso_tempo(quando) / (0.15 + d)
            pesi[etichetta] = pesi.get(etichetta, 0.0) + w
            esempi_per[etichetta] = esempi_per.get(etichetta, 0) + 1
            if perche and (etichetta not in motivi or perche == "stesso importo"):
                motivi[etichetta] = perche
            if s > simile.get(etichetta, (0, ""))[0]:
                simile[etichetta] = (s, desc)
        if not pesi:
            return None
        totale = sum(pesi.values())
        classifica = sorted(pesi.items(), key=lambda x: -x[1])
        migliore, peso = classifica[0]
        n = esempi_per[migliore]
        fiducia = peso / totale
        # Un esempio solo e' un indizio, non una regola: la fiducia si
        # ammorbidisce finche' gli esempi sono pochi.
        fiducia *= min(1.0, 0.55 + 0.15 * n)
        simili_tot = len(candidati)
        pezzi = [f'{n} dei {min(VICINI, simili_tot)} movimenti più vicini'
                 if simili_tot > 1 else '1 movimento simile']
        if simile.get(migliore, (0, ""))[1]:
            pezzi[0] += f' («{simile[migliore][1][:32].strip()}»)'
        if motivi.get(migliore):
            pezzi.append(motivi[migliore])
        return {
            "etichetta": migliore,
            "nome": self.nomi.get(migliore, str(migliore)),
            "fiducia": round(fiducia, 2),
            "sicura": fiducia >= FIDUCIA_MINIMA,
            "esempi": n,
            "motivo": " · ".join(pezzi),
            "alternative": [(self.nomi.get(e, str(e)), round(p / totale, 2))
                            for e, p in classifica[1:3]],
        }


# ---------------------------------------------------------------------------
# Gli storici dei conti
# ---------------------------------------------------------------------------

def _tutte(client, tabella: str, select: str) -> list[dict]:
    out, offset, passo = [], 0, 1000
    while True:
        try:
            r = (client.table(tabella).select(select).order("data", desc=True)
                 .range(offset, offset + passo - 1).execute())
            pagina = getattr(r, "data", None) or []
        except Exception:
            return out
        out.extend(pagina)
        if len(pagina) < passo:
            return out
        offset += passo


def storico_personale(client) -> Storico:
    """
    Conto personale e Revolut **insieme**: usano lo stesso albero di
    categorie, e il bar sotto casa e' lo stesso qualunque carta si usi.
    Una cena categorizzata su WeBank insegna anche a Revolut, e viceversa.
    """
    from spese import dati as D
    nomi = {v["link_id"]: v["categoria"] + (f' › {v["sottocategoria"]}'
                                            if v["sottocategoria"] else "")
            for v in D.voci_categoria(client)}
    righe = []
    for r in _tutte(client, "v_spese", "data,tipo,importo,descrizione,categoria_link_id"):
        link = r.get("categoria_link_id")
        if link in nomi:
            righe.append({**r, "etichetta": link, "nome": nomi[link]})
    for r in _tutte(client, "b2f_revolut_movimenti",
                    "data,tipo,importo,descrizione,categoria_link_id"):
        link = r.get("categoria_link_id")
        if link in nomi:
            righe.append({**r, "etichetta": link, "nome": nomi[link]})
    return Storico(righe)


def storico_piva(client) -> Storico:
    """Il conto P.IVA ha le sue categorie (chiavi di `fatture/costanti.py`)."""
    from fatture.costanti import CATEGORIE_SPESE_PIVA
    nomi = dict(CATEGORIE_SPESE_PIVA)
    righe = []
    for r in _tutte(client, "b2f_spese_piva", "data,tipo,importo,descrizione,categoria"):
        k = r.get("categoria")
        if k in nomi:
            # Il «giroconto» della P.IVA e' un'uscita: dal conto escono.
            tipo = "uscita" if r.get("tipo") == "giroconto" else r.get("tipo")
            righe.append({**r, "tipo": tipo, "etichetta": k, "nome": nomi[k]})
    return Storico(righe)


# ---------------------------------------------------------------------------
# Lo storico tenuto pronto per i form
# ---------------------------------------------------------------------------
# Un form chiede una proposta a ogni lettera (con un piccolo ritardo): ricostruire
# lo storico ogni volta vorrebbe dire rileggere un migliaio di righe per
# ogni tasto. Si tiene pronto per un minuto — il tempo di scrivere un
# movimento —, e un movimento appena salvato entra al giro dopo.
_PRONTI: dict = {}
DURATA_CACHE = 60


def storico_pronto(client, conto: str) -> Storico:
    import time
    adesso = time.monotonic()
    chiave_cache = "piva" if conto == "piva" else "personale"
    pronto = _PRONTI.get(chiave_cache)
    if pronto and adesso - pronto[0] < DURATA_CACHE:
        return pronto[1]
    s = storico_piva(client) if chiave_cache == "piva" else storico_personale(client)
    _PRONTI[chiave_cache] = (adesso, s)
    return s
