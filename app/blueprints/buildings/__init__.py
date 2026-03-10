# Path: app/blueprints/equipment/__init__.py
from flask import Blueprint

equipment_bp = Blueprint('equipment', __name__, template_folder='templates')

from . import routes