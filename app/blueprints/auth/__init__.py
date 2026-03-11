# app/blueprints/auth/__init__.py
from flask import Blueprint

bp = Blueprint("auth", __name__, url_prefix="/auth", template_folder="templates")
from . import routes  # noqa: E402, F401
