from flask import Blueprint

spese_bp = Blueprint("spese", __name__)

from . import views  # noqa: E402,F401  registra le rotte
