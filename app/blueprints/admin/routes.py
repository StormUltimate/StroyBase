# app/blueprints/admin/routes.py
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from functools import wraps
from sqlalchemy import text
from app.extensions import db
from app.models import (
    User,
    Building,
    Floor,
    Document,
    MaterialMovement,
    BuildingParticipant,
)
from .forms import UserForm
from . import bp


def _update_schedule_works_building_id(building_id, new_building_id):
    """Обновить building_id в schedule_works через raw SQL (в БД может отсутствовать столбец project_id)."""
    try:
        if new_building_id is None:
            db.session.execute(
                text(
                    "UPDATE schedule_works SET building_id = NULL WHERE building_id = :bid"
                ),
                {"bid": building_id},
            )
        else:
            db.session.execute(
                text(
                    "UPDATE schedule_works SET building_id = :new_id WHERE building_id = :old_id"
                ),
                {"new_id": new_building_id, "old_id": building_id},
            )
    except Exception as e:
        current_app.logger.warning(
            "schedule_works update skipped (table/column may differ): %s", e
        )


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            flash("Доступ только для администратора", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)

    return decorated


@bp.route("/users")
@admin_required
def user_list():
    users = User.query.order_by(User.full_name).all()
    return render_template(
        "admin/users/list.html", users=users, title="Управление пользователями"
    )


@bp.route("/users/add", methods=["GET", "POST"])
@admin_required
def user_add():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(login=form.login.data).first():
            flash("Логин уже существует", "danger")
        else:
            user = User(
                login=form.login.data,
                full_name=form.full_name.data,
                role=form.role.data or "viewer",
                is_active=form.is_active.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"Пользователь {user.login} создан!", "success")
            return redirect(url_for("admin.user_list"))
    return render_template(
        "admin/users/form.html", form=form, title="Новый пользователь"
    )


@bp.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        if User.query.filter(User.login == form.login.data, User.id != user_id).first():
            flash("Логин уже занят", "danger")
        else:
            user.login = form.login.data
            user.full_name = form.full_name.data
            user.role = form.role.data or "viewer"
            user.is_active = form.is_active.data
            if form.password.data:
                user.set_password(form.password.data)
            db.session.commit()
            flash("Пользователь обновлён", "success")
            return redirect(url_for("admin.user_list"))
    return render_template(
        "admin/users/form.html", form=form, title=f"Редактирование {user.login}"
    )


@bp.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Нельзя удалить себя", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Пользователь удалён", "success")
    return redirect(url_for("admin.user_list"))


# ---------- Корпуса: список и ручное удаление / переназначение ----------


@bp.route("/buildings")
@admin_required
def buildings_list():
    """Список всех корпусов: проект, название, этажей, движений, дата, примечание. Сортировка по project_id, name."""
    buildings = Building.query.order_by(Building.project_id, Building.name).all()
    rows = []
    for b in buildings:
        floors_count = Floor.query.filter(Floor.building_id == b.id).count()
        movements_count = MaterialMovement.query.filter(
            MaterialMovement.building_id == b.id
        ).count()
        same_project = [
            x for x in buildings if x.project_id == b.project_id and x.id != b.id
        ]
        rows.append(
            {
                "building": b,
                "project": b.project,
                "floors_count": floors_count,
                "movements_count": movements_count,
                "same_project_buildings": same_project,
                "same_project_ids": [x.id for x in same_project],
                "same_project_names": [x.name for x in same_project],
            }
        )
    from collections import Counter

    project_counts = Counter(b.project_id for b in buildings)
    projects_with_many = [pid for pid, c in project_counts.items() if c > 10]
    return render_template(
        "admin/buildings/index.html",
        rows=rows,
        projects_with_many_buildings=projects_with_many,
        title="Корпуса",
    )


def _reassign_building_fks(building_id, target_building_id):
    """Переназначить все FK с building_id на target_building_id. Не удаляет корпус."""
    Floor.query.filter(Floor.building_id == building_id).update(
        {Floor.building_id: target_building_id}, synchronize_session=False
    )
    Document.query.filter(Document.building_id == building_id).update(
        {Document.building_id: target_building_id}, synchronize_session=False
    )
    MaterialMovement.query.filter(MaterialMovement.building_id == building_id).update(
        {MaterialMovement.building_id: target_building_id}, synchronize_session=False
    )
    _update_schedule_works_building_id(building_id, target_building_id)
    BuildingParticipant.query.filter(
        BuildingParticipant.building_id == building_id
    ).update(
        {BuildingParticipant.building_id: target_building_id}, synchronize_session=False
    )


def _delete_building_cascade(building_id):
    """Удалить корпус полностью: обнулить building_id у документов/движений/графика, удалить этажи и корпус."""
    Document.query.filter(Document.building_id == building_id).update(
        {Document.building_id: None}, synchronize_session=False
    )
    MaterialMovement.query.filter(MaterialMovement.building_id == building_id).update(
        {MaterialMovement.building_id: None}, synchronize_session=False
    )
    _update_schedule_works_building_id(building_id, None)
    for floor in Floor.query.filter(Floor.building_id == building_id).all():
        db.session.delete(floor)
    BuildingParticipant.query.filter(
        BuildingParticipant.building_id == building_id
    ).delete(synchronize_session=False)
    db.session.execute(
        text("DELETE FROM buildings WHERE id = :id"), {"id": building_id}
    )


@bp.route("/buildings/<int:building_id>/delete", methods=["POST"])
@admin_required
def building_delete(building_id):
    """Удалить корпус полностью (каскад: этажи и связи обнуляются или удаляются)."""
    building = Building.query.get_or_404(building_id)
    building_name = building.name
    try:
        _delete_building_cascade(building_id)
        db.session.commit()
        flash(
            f"Корпус «{building_name}» удалён. Этажи и связи по корпусу удалены.",
            "success",
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {e}", "danger")
    return redirect(url_for("admin.buildings_list"))


@bp.route("/buildings/<int:building_id>/reassign", methods=["POST"])
@admin_required
def building_reassign(building_id):
    """Переназначить все связи корпуса на другой корпус того же проекта, затем удалить корпус."""
    building = Building.query.get_or_404(building_id)
    target_id = request.form.get("target_building_id", type=int)
    if not target_id or target_id == building_id:
        flash("Выберите другой корпус того же проекта для переназначения.", "danger")
        return redirect(url_for("admin.buildings_list"))
    target = Building.query.get(target_id)
    if not target or target.project_id != building.project_id:
        flash("Корпус назначения должен относиться к тому же проекту.", "danger")
        return redirect(url_for("admin.buildings_list"))
    building_name, target_name = building.name, target.name
    try:
        _reassign_building_fks(building_id, target_id)
        db.session.execute(
            text("DELETE FROM buildings WHERE id = :id"), {"id": building_id}
        )
        db.session.commit()
        flash(
            f"Корпус «{building_name}» удалён. Связи переназначены на «{target_name}».",
            "success",
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при переназначении: {e}", "danger")
    return redirect(url_for("admin.buildings_list"))


# ---------- Объёмы работ: полная очистка works / work_progress ----------


@bp.route("/works/reset_all", methods=["POST"])
@admin_required
def reset_all_works():
    """Полностью очистить таблицы works и work_progress (объёмы и ежедневное выполнение по всем объектам).

    Структура таблиц и связи остаются, удаляются только данные. Использовать ТОЛЬКО
    осознанно: действие необратимо, восстановление возможно только из резервной копии БД.
    """
    try:
        db.session.execute(text("DELETE FROM work_progress"))
        db.session.execute(text("DELETE FROM works"))
        db.session.commit()
        flash(
            "Все работы и ежедневное выполнение по объектам удалены. Таблицы works и work_progress очищены.",
            "success",
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при очистке данных по работам: {e}", "danger")
    return redirect(url_for("main.index"))
