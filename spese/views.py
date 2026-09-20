"""
spese/views.py — Il blueprint del conto personale e dei risparmi.

Non c'e' piu' una dashboard "/spese": la sezione non esisteva davvero —
si chiamava "Spese" e conteneva il conto personale (dove meta' delle
righe sono entrate), i risparmi, Revolut e l'import. Le sue pagine
vivono ora dove si capisce cosa sono:

    /conti/webank/personale            i movimenti del conto
    /conti/webank/personale/importa    l'import dall'estratto
    /conti/revolut                     Revolut
    /risparmi                          la procedura di fine periodo

L'elenco "Sezioni" che quella dashboard mostrava e' diventato il menu, e
il saldo del conto a oggi — l'unico numero che aveva di suo — sta in
cima alla pagina del conto.

Questo file resta perche' importare i sotto-moduli e' cio' che registra
le loro rotte sul blueprint.
"""
from . import spese_bp  # noqa: F401

# I sotto-moduli registrano le loro rotte sul blueprint quando importati.
from . import movimenti   # noqa: E402,F401
from . import risparmi    # noqa: E402,F401
from . import importa     # noqa: E402,F401
from . import revolut     # noqa: E402,F401
