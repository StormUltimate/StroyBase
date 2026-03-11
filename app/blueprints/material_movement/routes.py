# app/blueprints/material_movement/routes.py — StroyBase
# Раздел «Движение материалов»: только записи MaterialMovement (приход/расход/перемещение по объектам).
# Одна страница (таблица + фильтры + модальное окно добавления), одна страница редактирования с документами.
# Материалы по этажам (FloorMaterial) ведутся в разделе «Этажи» (floors).
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    current_app,
    send_from_directory,
    jsonify,
)
from flask_login import login_required
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError
import os
from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.utils.sanitize_names import normalize_name
from app.models import (
    Document,
    Floor,
    Building,
    Project,
    MaterialMovement,
    MovementDocument,
    FloorMaterial,
)
from app.forms import MaterialMovementForm

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _sanitize_display_name(s, fallback=""):
    """Санитизация названия для отображения в API. Логика совпадает с app.utils.sanitize_names (скрипт очистки БД)."""
    return normalize_name(s, fallback)


bp = Blueprint(
    name="movement",
    import_name=__name__,
    url_prefix="/movement",
    template_folder="templates/material_movement",
)


def _dedupe_by_id(items, id_key="id", fallback_name_template="— {id}"):
    """Убрать дубликаты по id; пустые name заменить на fallback. Для выпадающих списков."""
    seen = set()
    out = []
    for item in items:
        id_val = item.get(id_key)
        if id_val is None or id_val in seen:
            continue
        seen.add(id_val)
        item = dict(item)
        name = (item.get("name") or "").strip()
        if not name:
            try:
                item["name"] = fallback_name_template.format(id=id_val)
            except KeyError:
                item["name"] = str(id_val)
        out.append(item)
    return out


def _build_project_stock_summary(project_id):
    """Сводка по складу материалов для проекта: приход на склад объекта, расход на строения/этажи и остаток."""
    try:
        movements = MaterialMovement.query.filter_by(project_id=project_id).all()
    except ProgrammingError:
        db.session.rollback()
        return (
            [],
            "Таблица material_movements не найдена в БД. Создайте её в pgAdmin (см. комментарий в models.py).",
        )

    # Цены материалов берём из плана по ТХ (FloorMaterial) по этому проекту
    try:
        floor_materials = (
            FloorMaterial.query.join(Floor, FloorMaterial.floor_id == Floor.id)
            .join(Building, Floor.building_id == Building.id)
            .filter(Building.project_id == project_id)
            .all()
        )
    except ProgrammingError:
        db.session.rollback()
        floor_materials = []

    price_by_key = {}
    for fm in floor_materials:
        if fm.price_per_unit is None:
            continue
        key = (
            normalize_name(fm.name or "", ""),
            (fm.brand or "").strip().lower() or None,
            (fm.unit or "").strip() or None,
        )
        if key not in price_by_key:
            price_by_key[key] = fm.price_per_unit

    summary = {}

    for m in movements:
        if m.quantity is None:
            continue
        try:
            qty = Decimal(str(m.quantity))
        except Exception:
            continue

        key = (
            normalize_name(m.material_name or "", ""),
            (m.brand or "").strip().lower() or None,
            (m.unit or "").strip() or None,
        )
        row = summary.get(key)
        if not row:
            row = {
                "material_name": (m.material_name or "—"),
                "brand": (m.brand or None),
                "unit": (m.unit or None),
                "incoming_qty": Decimal("0"),
                "out_qty": Decimal("0"),
                "stock_qty": Decimal("0"),
                "price_per_unit": None,
                "stock_cost": None,
            }
            summary[key] = row

        # Приход на склад объекта: без привязки к строению/этажу
        if m.movement_type == "Приход" and m.building_id is None and m.floor_id is None:
            row["incoming_qty"] += qty

        # Расход на строения/этажи: с привязкой к строению (building_id)
        if m.movement_type == "Расход" and m.building_id is not None:
            row["out_qty"] += qty

    result = []
    for key, row in summary.items():
        row["stock_qty"] = row["incoming_qty"] - row["out_qty"]
        price = price_by_key.get(key)
        row["price_per_unit"] = price
        if price is not None:
            try:
                row["stock_cost"] = row["stock_qty"] * Decimal(str(price))
            except Exception:
                row["stock_cost"] = None
        result.append(row)

    result.sort(
        key=lambda r: (
            (r["material_name"] or "").lower(),
            (r["brand"] or "").lower() if r["brand"] else "",
            r["unit"] or "",
        )
    )
    return result, None


@bp.route("/api/buildings", methods=["GET"])
@login_required
def api_buildings():
    """Список строений только по project_id. Иерархия: проект → строения. Без project_id возвращаем 400."""
    project_id = request.args.get("project_id", type=int)
    if not project_id:
        return jsonify({"error": "Требуется параметр project_id"}), 400
    try:
        rows = (
            Building.query.filter_by(project_id=project_id)
            .order_by(Building.name)
            .all()
        )
        items = []
        for b in rows:
            fallback = f"Строение {b.id}"
            name = _sanitize_display_name(b.name, fallback)
            if name == fallback and b.name and str(b.name).strip():
                current_app.logger.debug(
                    "material_movement api_buildings: sanitization fallback for building id=%s raw_name=%r",
                    b.id,
                    b.name[:100] if b.name else None,
                )
            items.append({"id": b.id, "project_id": b.project_id, "name": name})
        items = _dedupe_by_id(items, id_key="id", fallback_name_template="Строение {id}")
        items.sort(key=lambda x: (x.get("name") or "").lower())
        return jsonify(items)
    except ProgrammingError:
        db.session.rollback()
        return jsonify([]), 500


@bp.route("/api/floors", methods=["GET"])
@login_required
def api_floors():
    """Список этажей только по building_id. Иерархия: строение → этажи. Без building_id возвращаем 400."""
    building_id = request.args.get("building_id", type=int)
    if not building_id:
        return jsonify({"error": "Требуется параметр building_id"}), 400
    try:
        rows = Floor.query.filter_by(building_id=building_id).order_by(Floor.name).all()
        items = []
        for f in rows:
            fallback = f"Этаж {f.id}"
            name = _sanitize_display_name(f.name, fallback)
            if name == fallback and f.name and str(f.name).strip():
                current_app.logger.debug(
                    "material_movement api_floors: sanitization fallback for floor id=%s raw_name=%r",
                    f.id,
                    f.name[:100] if f.name else None,
                )
            items.append({"id": f.id, "building_id": f.building_id, "name": name})
        items = _dedupe_by_id(items, id_key="id", fallback_name_template="Этаж {id}")
        items.sort(key=lambda x: (x.get("name") or "").lower())
        return jsonify(items)
    except ProgrammingError:
        db.session.rollback()
        return jsonify([]), 500


@bp.route("/", methods=["GET"])
@login_required
def index():
    """Список записей о движении материалов с фильтрами. При открытии с project_id — авто-выбор проекта."""
    project_id = request.args.get("project_id", type=int)
    building_id = request.args.get("building_id", type=int)
    floor_id = request.args.get("floor_id", type=int)
    material_name = request.args.get("material_name", "").strip() or None
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    movement_type = request.args.get("movement_type") or None

    page = request.args.get("page", 1, type=int)
    per_page = 50

    try:
        query = MaterialMovement.query.options(
            joinedload(MaterialMovement.project),
            joinedload(MaterialMovement.building),
            joinedload(MaterialMovement.floor),
        )
        if project_id:
            query = query.filter(MaterialMovement.project_id == project_id)
        if building_id:
            query = query.filter(MaterialMovement.building_id == building_id)
        if floor_id:
            query = query.filter(MaterialMovement.floor_id == floor_id)
        if material_name:
            query = query.filter(
                MaterialMovement.material_name.ilike(f"%{material_name}%")
            )
        if date_from:
            try:
                query = query.filter(
                    MaterialMovement.movement_date
                    >= datetime.strptime(date_from, "%Y-%m-%d").date()
                )
            except ValueError:
                pass
        if date_to:
            try:
                query = query.filter(
                    MaterialMovement.movement_date
                    <= datetime.strptime(date_to, "%Y-%m-%d").date()
                )
            except ValueError:
                pass
        if movement_type:
            query = query.filter(MaterialMovement.movement_type == movement_type)

        query = query.order_by(
            MaterialMovement.movement_date.desc().nullslast(),
            MaterialMovement.created_at.desc(),
        )
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        movements = pagination.items
    except ProgrammingError:
        db.session.rollback()
        movements = []
        pagination = None
        flash(
            "Таблица material_movements не найдена в БД. Выполните: flask db upgrade",
            "warning",
        )

    projects = Project.query.order_by(Project.name).all()
    # Для модалки строения и этажи не отдаём в HTML — подгружаются по API (api_buildings, api_floors) с санитизацией названий, без артефактов
    projects_display = [
        (p.id, _sanitize_display_name(p.name, f"Проект {p.id}")) for p in projects
    ]

    preset_building_id = request.args.get("building_id", type=int)
    preset_floor_id = request.args.get("floor_id", type=int)

    return render_template(
        "material_movement/index.html",
        movements=movements,
        pagination=pagination,
        projects_display=projects_display,
        preset_project_id=project_id,
        preset_building_id=preset_building_id,
        preset_floor_id=preset_floor_id,
        current_filters={
            "project_id": project_id,
            "building_id": building_id,
            "floor_id": floor_id,
            "material_name": material_name or request.args.get("material_name", ""),
            "date_from": date_from or request.args.get("date_from", ""),
            "date_to": date_to or request.args.get("date_to", ""),
            "movement_type": movement_type or request.args.get("movement_type", ""),
        },
    )


@bp.route("/stock", methods=["GET"])
@login_required
def stock():
    """Склад материалов по проекту: приход на объект, расход на строения/этажи и остаток с оценкой в деньгах."""
    project_id = request.args.get("project_id", type=int)

    projects = Project.query.order_by(Project.name).all()
    projects_display = [
        (p.id, _sanitize_display_name(p.name, f"Проект {p.id}")) for p in projects
    ]

    stock_rows = []
    error_message = None
    if project_id:
        stock_rows, error_message = _build_project_stock_summary(project_id)

    return render_template(
        "material_movement/stock.html",
        projects_display=projects_display,
        current_project_id=project_id,
        stock_rows=stock_rows,
        error_message=error_message,
    )


@bp.route("/create", methods=["POST"])
@login_required
def create_movement():
    """Создание записи о движении материала. project_id обязателен, building_id/floor_id опциональны. Строения и этажи в модалке подгружаются по API с каскадной фильтрацией."""
    form = MaterialMovementForm()
    projects = Project.query.order_by(Project.name).all()
    form.project_id.choices = [("", "— Выберите проект —")] + [
        (p.id, p.name) for p in projects
    ]
    project_id = request.form.get("project_id", type=int)
    form.building_id.choices = [("", "— Не привязан —")]
    form.floor_id.choices = [("", "— Не привязан —")]
    if project_id:
        form.building_id.choices += [
            (b.id, b.name)
            for b in Building.query.filter_by(project_id=project_id)
            .order_by(Building.name)
            .all()
        ]
    building_id = request.form.get("building_id", type=int)
    if building_id:
        form.floor_id.choices += [
            (f.id, f.name)
            for f in Floor.query.filter_by(building_id=building_id)
            .order_by(Floor.name)
            .all()
        ]

    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for e in errors:
                flash(f"{getattr(form, field).label.text}: {e}", "danger")
        return redirect(
            url_for("movement.index", **{k: v for k, v in request.args.items() if v})
        )

    try:
        movement = MaterialMovement(
            project_id=form.project_id.data,
            building_id=form.building_id.data or None,
            floor_id=form.floor_id.data or None,
            material_name=form.material_name.data or None,
            brand=form.brand.data or None,
            quantity=form.quantity.data,
            unit=form.unit.data or None,
            volume_m3=form.volume_m3.data,
            length_m=form.length_m.data,
            weight_kg=form.weight_kg.data,
            movement_type=form.movement_type.data or None,
            movement_date=form.movement_date.data,
            note=form.note.data or None,
        )
        db.session.add(movement)
        db.session.commit()
        flash("Запись о движении материала успешно создана", "success")
    except ProgrammingError as e:
        db.session.rollback()
        flash(
            "Ошибка базы данных. Убедитесь, что таблица material_movements создана (см. комментарий в models.py).",
            "danger",
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при сохранении: {e}", "danger")

    return redirect(
        url_for(
            "movement.index",
            project_id=form.project_id.data,
            **{k: v for k, v in request.args.items() if k != "project_id" and v},
        )
    )


@bp.route("/edit/<int:movement_id>", methods=["GET", "POST"])
@login_required
def edit_movement(movement_id):
    """Редактирование записи о движении. Строения — только выбранного проекта, этажи — только выбранного строения (каскад)."""
    movement = MaterialMovement.query.get_or_404(movement_id)
    form = MaterialMovementForm(obj=movement)

    projects = Project.query.order_by(Project.name).all()
    form.project_id.choices = [("", "— Выберите проект —")] + [
        (p.id, p.name) for p in projects
    ]
    project_id = (
        movement.project_id
        if request.method == "GET"
        else request.form.get("project_id", type=int)
    )
    building_id = (
        movement.building_id
        if request.method == "GET"
        else request.form.get("building_id", type=int)
    )
    form.building_id.choices = [("", "— Не привязан —")]
    form.floor_id.choices = [("", "— Не привязан —")]
    if project_id:
        form.building_id.choices += [
            (b.id, b.name)
            for b in Building.query.filter_by(project_id=project_id)
            .order_by(Building.name)
            .all()
        ]
    if building_id:
        form.floor_id.choices += [
            (f.id, f.name)
            for f in Floor.query.filter_by(building_id=building_id)
            .order_by(Floor.name)
            .all()
        ]

    if form.validate_on_submit():
        try:
            movement.project_id = form.project_id.data
            movement.building_id = form.building_id.data or None
            movement.floor_id = form.floor_id.data or None
            movement.material_name = form.material_name.data or None
            movement.brand = form.brand.data or None
            movement.quantity = form.quantity.data
            movement.unit = form.unit.data or None
            movement.volume_m3 = form.volume_m3.data
            movement.length_m = form.length_m.data
            movement.weight_kg = form.weight_kg.data
            movement.movement_type = form.movement_type.data or None
            movement.movement_date = form.movement_date.data
            movement.note = form.note.data or None
            db.session.commit()
            flash("Запись о движении успешно обновлена", "success")
            return redirect(url_for("movement.index", project_id=movement.project_id))
        except ProgrammingError:
            db.session.rollback()
            flash("Ошибка базы данных.", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении: {e}", "danger")

    try:
        document_links = movement.movement_document_links.order_by(
            MovementDocument.order
        ).all()
    except Exception:
        document_links = []

    return render_template(
        "material_movement/edit_movement.html",
        movement=movement,
        form=form,
        document_links=document_links,
        api_buildings_url=url_for("movement.api_buildings"),
        api_floors_url=url_for("movement.api_floors"),
    )


DOC_TYPE_LABELS = {
    "invoice": "Накладная",
    "upd": "УПД",
    "certificate": "Сертификат",
    "other": "Другое",
}


@bp.route("/edit/<int:movement_id>/attach-document", methods=["POST"])
@login_required
def attach_movement_document(movement_id):
    """Загрузить файл и привязать к записи о движении (накладная, УПД, сертификат)."""
    movement = MaterialMovement.query.get_or_404(movement_id)
    if "file" not in request.files:
        flash("Файл не выбран", "danger")
        return redirect(url_for("movement.edit_movement", movement_id=movement_id))
    file = request.files["file"]
    if not file or file.filename == "" or not allowed_file(file.filename):
        flash("Недопустимый файл или расширение", "danger")
        return redirect(url_for("movement.edit_movement", movement_id=movement_id))
    doc_type = request.form.get("doc_type", "other") or "other"
    if doc_type not in DOC_TYPE_LABELS:
        doc_type = "other"
    upload_dir = os.path.join(
        current_app.root_path,
        "static",
        "media",
        "projects",
        str(movement.project_id),
        "movement_docs",
        str(movement_id),
    )
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
    file_path = os.path.join(upload_dir, unique_name)
    file.save(file_path)
    rel_path = f"media/projects/{movement.project_id}/movement_docs/{movement_id}/{unique_name}".replace(
        "\\", "/"
    )
    doc = Document(
        project_id=movement.project_id,
        building_id=movement.building_id,
        floor_id=movement.floor_id,
        title=request.form.get("title")
        or f"{DOC_TYPE_LABELS.get(doc_type)} — {movement.material_name or 'материал'}",
        filename=filename,
        stored_path=rel_path,
        file_size=os.path.getsize(file_path),
        uploaded_at=datetime.utcnow(),
    )
    db.session.add(doc)
    db.session.flush()
    max_order = (
        db.session.query(func.max(MovementDocument.order))
        .filter(MovementDocument.movement_id == movement_id)
        .scalar()
        or 0
    )
    link = MovementDocument(
        movement_id=movement_id,
        document_id=doc.id,
        doc_type=doc_type,
        order=max_order + 1,
    )
    db.session.add(link)
    db.session.commit()
    flash(f"Документ «{filename}» привязан к записи", "success")
    return redirect(url_for("movement.edit_movement", movement_id=movement_id))


@bp.route("/edit/<int:movement_id>/detach-document/<int:document_id>", methods=["POST"])
@login_required
def detach_movement_document(movement_id, document_id):
    """Отвязать документ от записи о движении (запись Document не удаляется)."""
    movement = MaterialMovement.query.get_or_404(movement_id)
    link = MovementDocument.query.filter_by(
        movement_id=movement_id, document_id=document_id
    ).first_or_404()
    db.session.delete(link)
    db.session.commit()
    flash("Документ отвязан от записи", "success")
    return redirect(url_for("movement.edit_movement", movement_id=movement_id))


@bp.route("/edit/<int:movement_id>/document/<int:document_id>")
@login_required
def serve_movement_document(movement_id, document_id):
    """Отдать файл документа, привязанного к движению материала."""
    movement = MaterialMovement.query.get_or_404(movement_id)
    link = MovementDocument.query.filter_by(
        movement_id=movement_id, document_id=document_id
    ).first_or_404()
    doc = link.document
    if not doc or not doc.stored_path:
        from flask import abort

        abort(404)
    full_path = os.path.join(
        current_app.root_path, "static", doc.stored_path.replace("/", os.sep)
    )
    if not os.path.isfile(full_path):
        from flask import abort

        abort(404)
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename, as_attachment=False)
