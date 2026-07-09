from flask import Blueprint

fatture_bp = Blueprint("fatture", __name__)

from . import views  # noqa: E402,F401  registra le rotte
