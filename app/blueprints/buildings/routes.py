# app/blueprints/buildings/routes.py
"""
Buildings blueprint for StroyBase.
Handles CRUD for buildings (строения/здания), document upload/view/delete,
and related filtering.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    current_app,
    g,
    send_from_directory,
    abort,
)
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.exc import ProgrammingError
from app.extensions import db
from app.models import (
    Building,
    Project,
    Floor,
    Document,
    DocType,
    document_work_types,
    ScheduleWork,
    FloorMaterial,
    FloorQuantity,
)
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from PIL import Image
import uuid
import random

bp = Blueprint("buildings", __name__, url_prefix="/buildings")


@bp.before_request
@login_required
def load_building_if_exists():
    """Load building into g context if building_id or doc_id is present in view args."""
    building_id = request.view_args.get("building_id")
    if building_id is not None:
        g.building = Building.query.get_or_404(building_id)
        return

    doc_id = request.view_args.get("doc_id")
    if doc_id is not None:
        doc = Document.query.get_or_404(doc_id)
        if doc.building_id is None:
            abort(403, "This document is not attached to any building")
        g.building = Building.query.get_or_404(doc.building_id)


@bp.route("/create/<int:project_id>", methods=["GET", "POST"])
@login_required
def create_building(project_id):
    project = Project.query.get_or_404(project_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        building_class = request.form.get("building_class", "").strip() or None
        work_type = request.form.get("work_type", "").strip() or None
        note = request.form.get("note", "").strip() or None

        if not name:
            flash("Название строения обязательно", "danger")
            return render_template("buildings/create_building.html", project=project)

        colors = [
            "primary",
            "success",
            "info",
            "warning",
            "danger",
            "secondary",
            "dark",
        ]
        color = random.choice(colors)

        building = Building(
            project_id=project_id,
            name=name,
            building_class=building_class,
            work_type=work_type,
            note=note,
            color=color,
        )
        db.session.add(building)
        db.session.commit()

        flash("Строение успешно создано", "success")
        return redirect(url_for("project.dashboard", project_id=project_id))

    return render_template("buildings/create_building.html", project=project)


@bp.route("/edit/<int:building_id>", methods=["GET", "POST"])
@login_required
def edit_building(building_id):
    building = Building.query.get_or_404(building_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        building_class = request.form.get("building_class", "").strip() or None
        work_type = request.form.get("work_type", "").strip() or None
        note = request.form.get("note", "").strip() or None

        if not name:
            flash("Название строения обязательно", "danger")
            return render_template("buildings/edit.html", building=building), 200

        building.name = name
        building.building_class = building_class
        building.work_type = work_type
        building.note = note
        db.session.commit()
        flash("Строение успешно обновлено", "success")
        return redirect(url_for("buildings.view_building", building_id=building_id))

    return render_template("buildings/edit.html", building=building)


@bp.route("/delete/<int:building_id>", methods=["POST"])
@login_required
def delete_building(building_id):
    building = Building.query.get_or_404(building_id)
    project_id = building.project_id

    db.session.delete(building)
    db.session.commit()

    flash("Строение успешно удалено (вместе с этажами и документами)", "info")
    return redirect(url_for("project.dashboard", project_id=project_id))


@bp.route("/<int:building_id>")
@login_required
def view_building(building_id):
    building = g.building  # loaded by before_request

    floors = Floor.query.filter_by(building_id=building_id).order_by(Floor.name).all()
    doc_types = DocType.query.order_by(DocType.sort_order).all()

    # Filters from query string
    floor_id = request.args.get("floor_id", type=int)
    doc_type_id = request.args.get("doc_type_id", type=int)
    media_type = request.args.get("media_type", "all")
    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")

    query = Document.query.filter_by(building_id=building_id)

    if floor_id is not None:
        query = query.filter_by(floor_id=floor_id)

    if doc_type_id:
        query = query.join(document_work_types).filter(
            document_work_types.c.doc_type_id == doc_type_id
        )

    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
            query = query.filter(Document.uploaded_at >= from_date)
        except ValueError:
            flash('Invalid "from" date format', "warning")

    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, "%Y-%m-%d")
            query = query.filter(Document.uploaded_at <= to_date)
        except ValueError:
            flash('Invalid "to" date format', "warning")

    all_docs = query.order_by(
        Document.file_modified_at.desc().nullslast(), Document.uploaded_at.desc()
    ).all()

    # Separate media and documents
    media_docs = []
    doc_docs = []
    photo_ext = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    video_ext = {".mp4", ".webm", ".mov", ".avi"}

    for doc in all_docs:
        ext = os.path.splitext((doc.filename or "").lower())[1]
        is_photo = ext in photo_ext
        is_video = ext in video_ext
        # Скан документа в виде изображения всегда попадает во вкладку «Документы»
        if is_photo and getattr(doc, "is_document_image", None):
            doc_docs.append(doc)
            continue
        if is_photo or is_video:
            if (
                media_type == "all"
                or (media_type == "photo" and is_photo)
                or (media_type == "video" and is_video)
            ):
                media_docs.append(doc)
        else:
            doc_docs.append(doc)

    # Договора: документы с видом «Договор» для вкладки «Договора»
    contract_doc_type = DocType.query.filter_by(name="Договор").first()
    contract_doc_type_id = contract_doc_type.id if contract_doc_type else None
    contract_docs = []
    if contract_doc_type_id:
        c_query = (
            Document.query.filter_by(building_id=building_id)
            .join(document_work_types)
            .filter(document_work_types.c.doc_type_id == contract_doc_type_id)
        )
        contract_date_from = request.args.get("contract_date_from")
        contract_date_to = request.args.get("contract_date_to")
        contract_search = (request.args.get("contract_search") or "").strip()
        if contract_date_from:
            try:
                c_query = c_query.filter(
                    Document.contract_date
                    >= datetime.strptime(contract_date_from, "%Y-%m-%d").date()
                )
            except ValueError:
                pass
        if contract_date_to:
            try:
                c_query = c_query.filter(
                    Document.contract_date
                    <= datetime.strptime(contract_date_to, "%Y-%m-%d").date()
                )
            except ValueError:
                pass
        if contract_search:
            search_like = f"%{contract_search}%"
            c_query = c_query.filter(
                or_(
                    Document.contract_number.ilike(search_like),
                    Document.counterparty.ilike(search_like),
                    Document.title.ilike(search_like),
                )
            )
        contract_docs = c_query.order_by(
            Document.contract_date.desc().nullslast(), Document.uploaded_at.desc()
        ).all()

    # doc_docs и contract_docs передаются в shared/document_tab.html (вкладки «Документы», «Договора»).
    # Для будущих вкладок ПД/РД/ИД можно фильтровать по doc_filter_category (DocType.name содержит подстроку).
    try:
        schedule_works = list(building.schedule_works)
    except ProgrammingError:
        db.session.rollback()
        # Таблица schedule_works ещё не создана в pgAdmin — показываем пустой список
        schedule_works = []

    # План и график работ по объёмам (Works/WorkProgress) — одно строение, как на объекте
    from app.blueprints.project.routes import _build_works_summary

    try:
        works_by_building, works_summary_project, works_summary_buildings = (
            _build_works_summary(
                building.project_id,
                [building],
                graphs_building_id=building_id,
                graphs_works_from_str=request.args.get("graphs_works_from"),
                graphs_works_to_str=request.args.get("graphs_works_to"),
            )
        )
    except Exception:
        works_by_building = [{"building": building, "entries": []}]
        works_summary_project = {
            "total_volume": 0.0,
            "total_executed": 0.0,
            "percent": None,
        }
        works_summary_buildings = [
            {
                "building": building,
                "total_volume": 0.0,
                "total_executed": 0.0,
                "percent": None,
                "building_avg_percent": None,
            }
        ]

    # Сводка материалов по строению: группировка по тегу/категории, наименованию и бренду по всем этажам строения
    from decimal import Decimal

    building_material_summary = []
    try:
        building_materials = (
            FloorMaterial.query.join(Floor, FloorMaterial.floor_id == Floor.id)
            .filter(Floor.building_id == building_id)
            .all()
        )
        building_material_summary_map = {}
        for m in building_materials:
            category_name = m.category.name if getattr(m, "category", None) else None
            key = (category_name, m.name, m.brand or m.gost or None, m.unit or None)
            if key not in building_material_summary_map:
                building_material_summary_map[key] = {
                    "category": category_name,
                    "name": m.name,
                    "brand": m.brand or m.gost or None,
                    "unit": m.unit or None,
                    "planned_total": Decimal("0"),
                    "actual_total": Decimal("0"),
                    "total_cost": Decimal("0"),
                }
            row = building_material_summary_map[key]
            if m.planned_quantity is not None:
                row["planned_total"] += Decimal(m.planned_quantity)
            if m.actual_quantity is not None:
                row["actual_total"] += Decimal(m.actual_quantity)
            if hasattr(m, "total_cost") and m.total_cost is not None:
                row["total_cost"] += Decimal(str(m.total_cost))

        building_material_summary = sorted(
            building_material_summary_map.values(),
            key=lambda r: (
                r["category"] or "",
                r["name"] or "",
                r["brand"] or "",
            ),
        )
    except ProgrammingError:
        db.session.rollback()
        building_material_summary = []

    # Сводка площадей и величин по строению: группировка по наименованию и единице по всем этажам строения
    building_quantities_summary = []
    try:
        building_quantities = (
            FloorQuantity.query.join(Floor, FloorQuantity.floor_id == Floor.id)
            .filter(Floor.building_id == building_id)
            .all()
        )
        quantities_map = {}
        for q in building_quantities:
            key = (q.name or "—", (q.unit or "").strip() or None)
            if key not in quantities_map:
                quantities_map[key] = {
                    "name": q.name or "—",
                    "unit": q.unit or None,
                    "total_quantity": Decimal("0"),
                }
            row = quantities_map[key]
            if q.quantity is not None:
                row["total_quantity"] += Decimal(str(q.quantity))
        building_quantities_summary = sorted(
            quantities_map.values(),
            key=lambda r: (r["name"] or "", r["unit"] or ""),
        )
    except ProgrammingError:
        db.session.rollback()
        building_quantities_summary = []
    total_floors_area = sum((f.total_area_m2 or 0) for f in floors) if floors else 0
    return render_template(
        "buildings/view.html",
        building=building,
        project=building.project,
        floors=floors,
        total_floors_area=total_floors_area,
        doc_types=doc_types,
        media_docs=media_docs,
        doc_docs=doc_docs,
        contract_docs=contract_docs,
        contract_doc_type_id=contract_doc_type_id,
        schedule_works=schedule_works,
        building_material_summary=building_material_summary,
        building_quantities_summary=building_quantities_summary,
        works_by_building=works_by_building,
        works_summary_project=works_summary_project,
        works_summary_buildings=works_summary_buildings,
        graphs_works_from_str=request.args.get("graphs_works_from"),
        graphs_works_to_str=request.args.get("graphs_works_to"),
        root_path=current_app.root_path.replace("\\", "/"),
    )


def _parse_date(value):
    """Вернуть date или None из строки YYYY-MM-DD."""
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_tags_raw(raw: str):
    """Разобрать строку тегов 'монолит, отделка; кровля' в список имён."""
    if not raw:
        return []
    parts = [p.strip() for p in str(raw).replace(";", ",").split(",")]
    return [p for p in parts if p]


def _ensure_doc_types_by_names(names):
    """Найти или создать DocType по переданным именам и вернуть список id."""
    ids = []
    for name in names:
        if not name:
            continue
        dt = DocType.query.filter_by(name=name).first()
        if not dt:
            dt = DocType(name=name)
            db.session.add(dt)
            db.session.flush()
        ids.append(dt.id)
    return ids


@bp.route("/<int:building_id>/schedule/add", methods=["POST"])
@login_required
def add_schedule_work(building_id):
    building = Building.query.get_or_404(building_id)
    name = (request.form.get("name") or "").strip() or None
    planned_start = _parse_date(request.form.get("planned_start"))
    planned_end = _parse_date(request.form.get("planned_end"))
    fact_start = _parse_date(request.form.get("fact_start"))
    fact_end = _parse_date(request.form.get("fact_end"))
    percent_raw = request.form.get("percent_complete")
    percent_complete = None
    if percent_raw not in (None, ""):
        try:
            percent_complete = float(percent_raw)
            if percent_complete < 0 or percent_complete > 100:
                percent_complete = None
        except (ValueError, TypeError):
            pass
    status = (request.form.get("status") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    work = ScheduleWork(
        project_id=building.project_id,
        building_id=building_id,
        name=name,
        planned_start=planned_start,
        planned_end=planned_end,
        fact_start=fact_start,
        fact_end=fact_end,
        percent_complete=percent_complete,
        status=status,
        notes=notes,
    )
    db.session.add(work)
    try:
        db.session.commit()
        flash("Работа успешно добавлена в график", "success")
    except ProgrammingError:
        db.session.rollback()
        flash(
            "Ошибка БД: структура таблицы schedule_works устарела. "
            "Запустите миграции БД командой: flask db upgrade.",
            "danger",
        )
    return redirect(
        url_for("buildings.view_building", building_id=building_id) + "#schedules"
    )


@bp.route("/<int:building_id>/upload_documents", methods=["POST"])
@login_required
def upload_building_documents(building_id):
    building = Building.query.get_or_404(building_id)
    project_id = building.project_id

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        flash("Please select at least one file", "danger")
        return redirect(url_for("buildings.view_building", building_id=building_id))

    floor_id = request.form.get("floor_id", type=int) or None
    if floor_id:
        floor = Floor.query.get_or_404(floor_id)
        if floor.building_id != building_id:
            flash("Selected floor does not belong to this building", "danger")
            return redirect(url_for("buildings.view_building", building_id=building_id))

    # Prepare upload directory
    base_dir = os.path.join(
        current_app.root_path, "static", "media", "projects", str(project_id)
    )
    sub_dir = f"building_{building_id}"
    if floor_id:
        sub_dir = os.path.join(sub_dir, f"floor_{floor_id}")

    upload_dir = os.path.join(base_dir, sub_dir)
    os.makedirs(upload_dir, exist_ok=True)

    work_type_ids = [
        int(wt) for wt in request.form.getlist("work_type_ids") if wt.isdigit()
    ]
    title = request.form.get("title", "").strip() or None
    description = request.form.get("description", "").strip() or None
    extra_tag_names = _parse_tags_raw(request.form.get("tags"))
    extra_type_ids = (
        _ensure_doc_types_by_names(extra_tag_names) if extra_tag_names else []
    )
    all_type_ids = sorted(set(work_type_ids or []) | set(extra_type_ids))

    uploaded_count = 0

    for file in files:
        if not file.filename:
            continue

        original_name = file.filename
        safe_name = secure_filename(original_name)
        unique_name = f"{uuid.uuid4()}_{safe_name}"
        file_path = os.path.join(upload_dir, unique_name)

        file.save(file_path)

        try:
            file_modified_at = datetime.fromtimestamp(os.path.getmtime(file_path))
        except Exception:
            file_modified_at = datetime.utcnow()

        thumbnail_path = None
        width = height = None

        ext = os.path.splitext(original_name.lower())[1]
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
            try:
                img = Image.open(file_path)
                width, height = img.size
                img.thumbnail((240, 240))
                thumb_name = f"thumb_{unique_name}"
                thumb_path = os.path.join(upload_dir, thumb_name)
                img.save(thumb_path, optimize=True, quality=85)
                thumbnail_path = thumb_path
            except Exception as e:
                current_app.logger.warning(f"Thumbnail creation failed: {e}")

        # Relative paths for DB (URL-friendly)
        rel_path = os.path.join(
            "media", "projects", str(project_id), sub_dir, unique_name
        ).replace("\\", "/")
        rel_thumb = None
        if thumbnail_path:
            rel_thumb = os.path.join(
                "media", "projects", str(project_id), sub_dir, f"thumb_{unique_name}"
            ).replace("\\", "/")

        doc = Document(
            project_id=project_id,
            building_id=building_id,
            floor_id=floor_id,
            title=title,
            description=description,
            filename=original_name,
            stored_path=rel_path,
            thumbnail_path=rel_thumb,
            file_size=os.path.getsize(file_path),
            uploaded_at=datetime.utcnow(),
            file_modified_at=file_modified_at,
            width_px=width,
            height_px=height,
            is_document_image=True if request.form.get("is_document_image") else False,
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id

        for wt_id in all_type_ids:
            db.session.execute(
                document_work_types.insert().values(
                    document_id=doc.id, doc_type_id=wt_id
                )
            )

        uploaded_count += 1

    db.session.commit()
    flash(f"{uploaded_count} file(s) uploaded successfully", "success")
    return redirect(url_for("buildings.view_building", building_id=building_id))


@bp.route("/delete_document/<int:doc_id>", methods=["POST"])
@login_required
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    building_id = doc.building_id

    if not building_id:
        flash("Document is not attached to any building", "danger")
        return redirect(url_for("project.dashboard", project_id=doc.project_id))

    filename = doc.filename
    db.session.delete(doc)
    db.session.commit()

    flash(
        f'Document "{filename}" removed from database (physical file preserved)', "info"
    )
    return redirect(url_for("buildings.view_building", building_id=building_id))


@bp.route("/document/<int:doc_id>/view")
@login_required
def view_document(doc_id):
    doc = Document.query.get_or_404(doc_id)

    # Security check via g.building (set by before_request)
    if doc.building_id != g.building.id:
        abort(403, "You do not have permission to view this document")

    # Путь к файлу внутри каталога static (аналогично floors.view_document и project.view_document)
    full_path = os.path.join(
        current_app.root_path, "static", doc.stored_path.lstrip("/")
    )

    if not os.path.isfile(full_path):
        abort(404, "File not found on server")

    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)

    # По умолчанию открываем в браузере; при ?download=1 отдаём как вложение
    force_download = request.args.get("download") == "1"

    return send_from_directory(
        directory, filename, as_attachment=force_download, download_name=doc.filename
    )
