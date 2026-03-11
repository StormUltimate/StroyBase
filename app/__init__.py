# app/__init__.py
from flask import Flask, g, request, flash, url_for, redirect
from flask_wtf.csrf import CSRFProtect
from flask_login import current_user, AnonymousUserMixin

from app.extensions import db, login_manager, bcrypt, migrate

# ===================== BLUEPRINTS =====================
from .blueprints.main.routes import main_bp
from .blueprints.project.routes import project_bp
from .blueprints.buildings.routes import bp as buildings_bp
from .blueprints.floors.routes import bp as floors_bp
from .blueprints.auth import bp as auth_bp
from .blueprints.admin import bp as admin_bp
from .blueprints.material_movement.routes import bp as material_movement_bp


class AnonymousUser(AnonymousUserMixin):
    full_name = "Гость"
    role = "anonymous"


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    CSRFProtect(app)

    login_manager.login_view = "auth.login"
    login_manager.anonymous_user = AnonymousUser

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ===================== ГЛОБАЛЬНАЯ ЗАЩИТА =====================
    @app.before_request
    def require_login():
        if request.endpoint is None:
            return
        if request.endpoint.startswith(("auth.", "static")):
            return
        if not current_user.is_authenticated:
            flash(
                "Для работы с объектами, фото, видео и материалами нужно войти в StroyBase",
                "warning",
            )
            return redirect(url_for("auth.login"))

    # ===================== РЕГИСТРАЦИЯ BLUEPRINTS =====================
    app.register_blueprint(main_bp)
    app.register_blueprint(project_bp, url_prefix="/project")
    app.register_blueprint(buildings_bp)
    app.register_blueprint(floors_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp)
    app.register_blueprint(material_movement_bp, url_prefix="/movement")

    # ===================== CONTEXT PROCESSOR =====================
    @app.context_processor
    def inject_globals():
        from app.models import DocType, Project, Building, Floor

        data = {"DocType": DocType}
        if request.view_args:
            if "floor_id" in request.view_args:
                floor = Floor.query.get(request.view_args.get("floor_id"))
                if floor:
                    g.floor = floor
                    g.building = floor.building
                    g.project = floor.building.project
                    data["g_floor"] = floor
                    data["g_building"] = g.building
                    data["g_project"] = g.project
            elif "building_id" in request.view_args:
                building = Building.query.get(request.view_args.get("building_id"))
                if building:
                    g.building = building
                    g.project = building.project
                    data["g_building"] = building
                    data["g_project"] = g.project
            if "project_id" in request.view_args and not data.get("g_project"):
                project = Project.query.get(request.view_args.get("project_id"))
                if project:
                    g.project = project
                    data["g_project"] = project
        # Списки «соседей» для выпадающих списков в breadcrumb и для дерева в сайдбаре
        if data.get("g_project"):
            data["g_projects"] = Project.query.order_by(Project.name).all()
            data["g_buildings"] = (
                Building.query.filter_by(project_id=data["g_project"].id)
                .order_by(Building.name)
                .all()
            )
        if data.get("g_building"):
            data["g_floors"] = (
                Floor.query.filter_by(building_id=data["g_building"].id)
                .order_by(Floor.name)
                .all()
            )
        elif data.get("g_project"):
            data["g_floors"] = []
        # Дерево объектов в боковом меню (проекты со строениями и этажами)
        data["nav_projects"] = (
            Project.query.order_by(Project.name).all()
            if current_user.is_authenticated
            else []
        )
        return data

    from urllib.parse import urlencode

    @app.template_filter("to_query_string")
    def to_query_string(args):
        if not args:
            return ""
        clean = {k: v for k, v in args.items() if v}
        return "?" + urlencode(clean) if clean else ""

    return app
