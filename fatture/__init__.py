from flask import Blueprint

fatture_bp = Blueprint("fatture", __name__)

# views.py importa clienti/storico/editor/fiscale (che registrano le loro
# rotte sul blueprint quando importati) e definisce la rotta principale /.
from . import views  # noqa: E402,F401
from . import fiscale  # noqa: E402,F401
