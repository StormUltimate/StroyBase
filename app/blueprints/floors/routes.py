# app/blueprints/floors/routes.py — StroyBase
# Этажи: просмотр, документы, планы, метки, тех. информация (материалы, площади, оборудование).
# view_document: full_path с 'static', проверка существования файла.

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify, g, abort, send_from_directory
from flask_login import login_required
from app.extensions import db
from sqlalchemy.exc import ProgrammingError
from app.models import (
    Floor, Building, Document, DocType, document_work_types,
    FloorMaterial, FloorQuantity, FloorEquipment, Plan, Mark, MaterialCategory,
    MaterialMovement,
)
from app.forms import MaterialForm, FloorQuantityForm, FloorEquipmentForm
from werkzeug.utils import secure_filename
from datetime import datetime
from decimal import Decimal
import os
from PIL import Image
import uuid
import fitz  # PyMuPDF для PDF

bp = Blueprint('floors', __name__, template_folder='templates/floors')

@bp.before_request
def load_floor():
    floor_id = request.view_args.get('floor_id')
    if floor_id:
        g.floor = Floor.query.get_or_404(floor_id)
        return

    doc_id = request.view_args.get('doc_id')
    if doc_id:
        doc = Document.query.get_or_404(doc_id)
        if doc.floor_id is None:
            abort(403, "Документ не привязан к этажу")
        g.floor = Floor.query.get_or_404(doc.floor_id)


def _parse_tags_raw(raw: str):
    """Разобрать строку тегов 'монолит, отделка; кровля' в список имён."""
    if not raw:
        return []
    parts = [p.strip() for p in str(raw).replace(';', ',').split(',')]
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


def _floor_document_choices(floor):
    """Список (id, подпись) документов этажа для выбора сертификата/паспорта."""
    docs = Document.query.filter_by(floor_id=floor.id).order_by(Document.uploaded_at.desc()).all()
    return [('', '— не выбрано —')] + [
        (str(d.id), (d.title or d.filename or f'Документ #{d.id}')[:80])
        for d in docs
    ]


@bp.route('/floor/create/<int:building_id>', methods=['GET', 'POST'])
@login_required
def create_floor(building_id):
    building = Building.query.get_or_404(building_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        floor_type = request.form.get('floor_type', 'Обычный этаж')

        if not name:
            flash('Введите название этажа!', 'danger')
            return redirect(url_for('floors.create_floor', building_id=building_id))

        floor = Floor(
            building_id=building_id,
            name=name,
            floor_type=floor_type
        )
        db.session.add(floor)
        db.session.commit()
        flash(f'Этаж "{name}" создан!', 'success')
        return redirect(url_for('buildings.view_building', building_id=building_id))

    return render_template('floors/create.html', building=building)

@bp.route('/floor/edit/<int:floor_id>', methods=['GET', 'POST'])
@login_required
def edit_floor(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        floor_type = request.form.get('floor_type', 'Обычный этаж')
        note = request.form.get('note', '').strip()
        
        # Площади — float или None
        try:
            area_m2 = float(request.form.get('area_m2')) if request.form.get('area_m2') else None
        except (ValueError, TypeError):
            area_m2 = None
            
        try:
            total_area_m2 = float(request.form.get('total_area_m2')) if request.form.get('total_area_m2') else None
        except (ValueError, TypeError):
            total_area_m2 = None

        if not name:
            flash('Введите название этажа!', 'danger')
            return redirect(url_for('floors.edit_floor', floor_id=floor_id))

        floor.name = name
        floor.floor_type = floor_type
        floor.area_m2 = area_m2
        floor.total_area_m2 = total_area_m2
        floor.note = note
        
        db.session.commit()
        flash(f'Этаж "{name}" успешно обновлён', 'success')
        return redirect(url_for('buildings.view_building', building_id=floor.building_id))

    return render_template('floors/edit.html', floor=floor)

@bp.route('/floor/delete/<int:floor_id>', methods=['POST'])
@login_required
def delete_floor(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    building_id = floor.building_id
    db.session.delete(floor)
    db.session.commit()
    flash(f'Этаж "{floor.name}" удалён', 'info')
    return redirect(url_for('buildings.view_building', building_id=building_id))

@bp.route('/floor/<int:floor_id>')
@login_required
def view_floor(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    building = floor.building
    documents = floor.documents.order_by(
        Document.file_modified_at.desc().nullslast(),
        Document.uploaded_at.desc()
    ).all()

    # Фильтры галереи: дата загрузки, дата создания файла (file_modified_at), поиск по имени файла
    uploaded_from = request.args.get('filter_uploaded_from')
    uploaded_to = request.args.get('filter_uploaded_to')
    modified_from = request.args.get('filter_modified_from')
    modified_to = request.args.get('filter_modified_to')
    filename_search = (request.args.get('filter_filename') or '').strip().lower()

    def passes_filters(d):
        if uploaded_from:
            try:
                from_dt = datetime.strptime(uploaded_from, '%Y-%m-%d')
                if d.uploaded_at and d.uploaded_at.date() < from_dt.date():
                    return False
            except ValueError:
                pass
        if uploaded_to:
            try:
                to_dt = datetime.strptime(uploaded_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                if d.uploaded_at and d.uploaded_at > to_dt:
                    return False
            except ValueError:
                pass
        if modified_from and d.file_modified_at:
            try:
                from_d = datetime.strptime(modified_from, '%Y-%m-%d').date()
                if d.file_modified_at.date() < from_d:
                    return False
            except ValueError:
                pass
        if modified_to and d.file_modified_at:
            try:
                to_d = datetime.strptime(modified_to, '%Y-%m-%d').date()
                if d.file_modified_at.date() > to_d:
                    return False
            except ValueError:
                pass
        if filename_search and filename_search not in (d.filename or '').lower():
            return False
        return True

    filtered_documents = [d for d in documents if passes_filters(d)]
    plans = Plan.query.filter_by(floor_id=floor_id).order_by(Plan.uploaded_at.desc()).all()
    try:
        quantities = floor.quantities.order_by(FloorQuantity.name).all()
    except ProgrammingError:
        db.session.rollback()
        quantities = []
    try:
        equipment_list = floor.equipment.order_by(FloorEquipment.name).all()
    except ProgrammingError:
        db.session.rollback()
        equipment_list = []

    # Материалы на этаже: одна таблица (движение) + столбец «Проектный объём» из FloorMaterial
    try:
        floor_movements = MaterialMovement.query.filter_by(floor_id=floor_id).order_by(
            MaterialMovement.movement_date.desc().nullslast(),
            MaterialMovement.created_at.desc()
        ).all()
    except ProgrammingError:
        db.session.rollback()
        floor_movements = []

    # Проектный объём по записям движения: для каждой записи ищем FloorMaterial на этом этаже (по названию, при совпадении бренда/ед.)
    project_quantity_by_movement = {}
    try:
        floor_materials = FloorMaterial.query.filter_by(floor_id=floor_id).all()
        for mov in floor_movements:
            total = None
            for fm in floor_materials:
                name_ok = (mov.material_name or '').strip() == (fm.name or '').strip()
                if name_ok:
                    if fm.planned_quantity is not None:
                        total = (total or Decimal('0')) + Decimal(str(fm.planned_quantity))
            project_quantity_by_movement[mov.id] = total
    except ProgrammingError:
        db.session.rollback()
        project_quantity_by_movement = {m.id: None for m in floor_movements}

    # Сводка по движениям: группировка по наименованию, бренду, ед. изм. — сумма количества
    material_summary_map = {}
    for m in floor_movements:
        key = (m.material_name or '', m.brand or None, m.unit or None)
        if key not in material_summary_map:
            material_summary_map[key] = {
                "name": m.material_name or "—",
                "brand": m.brand or None,
                "unit": m.unit or None,
                "category": None,
                "quantity_total": Decimal("0"),
            }
        row = material_summary_map[key]
        if m.quantity is not None:
            row["quantity_total"] += Decimal(str(m.quantity))

    material_summary = sorted(
        material_summary_map.values(),
        key=lambda r: (r["name"] or "", r["brand"] or "", r["unit"] or ""),
    )

    # План / факт по материалам этажа: FloorMaterial (план) + агрегированные движения (факт)
    material_plan_fact_rows = []
    material_certificates_rows = []
    try:
        floor_materials = FloorMaterial.query.filter_by(floor_id=floor_id).order_by(FloorMaterial.name).all()

        # Фактический объём по ключу (наименование, бренд, ед. изм.)
        fact_by_key = {key: row["quantity_total"] for key, row in material_summary_map.items()}

        # Документы-сертификаты, привязанные к материалам этажа
        cert_ids = list({
            m.certificate_document_id
            for m in floor_materials
            if m.certificate_document_id
        })
        certificates_map = {}
        if cert_ids:
            cert_docs = Document.query.filter(Document.id.in_(cert_ids)).all()
            certificates_map = {d.id: d for d in cert_docs}

        for fm in floor_materials:
            key = ((fm.name or '').strip(), fm.brand or None, fm.unit or None)
            fact_qty = fact_by_key.get(key)
            plan_qty = fm.planned_quantity
            price_per_unit = fm.price_per_unit

            plan_cost = None
            fact_cost = None
            if plan_qty is not None and price_per_unit is not None:
                plan_cost = Decimal(str(plan_qty)) * Decimal(str(price_per_unit))
            if fact_qty is not None and price_per_unit is not None:
                fact_cost = fact_qty * Decimal(str(price_per_unit))

            deviation_percent = None
            severity = None
            severity_css = None
            if plan_qty is not None and fact_qty is not None:
                try:
                    plan_val = Decimal(str(plan_qty))
                    if plan_val != 0:
                        delta = fact_qty - plan_val
                        deviation_percent = (delta / plan_val) * Decimal('100')
                        abs_percent = abs(deviation_percent)
                        if abs_percent < Decimal('5'):
                            severity = 'ok'
                            severity_css = 'badge bg-success'
                        elif abs_percent < Decimal('15'):
                            severity = 'minor'
                            severity_css = 'badge bg-warning text-dark'
                        elif abs_percent < Decimal('30'):
                            severity = 'major'
                            severity_css = 'badge bg-danger'
                        else:
                            severity = 'critical'
                            severity_css = 'badge bg-danger'
                except Exception:
                    deviation_percent = None
                    severity = None
                    severity_css = None

            material_plan_fact_rows.append({
                "material": fm,
                "plan_qty": plan_qty,
                "fact_qty": fact_qty,
                "unit": fm.unit,
                "price_per_unit": price_per_unit,
                "plan_cost": plan_cost,
                "fact_cost": fact_cost,
                "deviation_percent": deviation_percent,
                "severity": severity,
                "severity_css": severity_css,
            })

            # Сертификат, привязанный напрямую к материалу
            if fm.certificate_document_id:
                cert_doc = certificates_map.get(fm.certificate_document_id)
                if cert_doc:
                    material_certificates_rows.append({
                        "material": fm,
                        "document": cert_doc,
                    })
    except ProgrammingError:
        db.session.rollback()
        material_plan_fact_rows = []
        material_certificates_rows = []
    photo_ext = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
    video_ext = ('.mp4', '.avi', '.mov', '.webm')
    media_docs = []
    doc_docs = []
    for d in filtered_documents:
        filename_lower = (d.filename or '').lower()
        is_photo = filename_lower.endswith(photo_ext)
        is_video = filename_lower.endswith(video_ext)
        if is_photo and getattr(d, 'is_document_image', None):
            doc_docs.append(d)
            continue
        if is_photo or is_video:
            media_docs.append(d)
        else:
            doc_docs.append(d)

    filter_values = {
        'filter_uploaded_from': uploaded_from,
        'filter_uploaded_to': uploaded_to,
        'filter_modified_from': modified_from,
        'filter_modified_to': modified_to,
        'filter_filename': request.args.get('filter_filename') or '',
    }
    return render_template('floors/view.html', floor=floor, building=building, documents=filtered_documents,
                          media_docs=media_docs, doc_docs=doc_docs, plans=plans,
                          floor_movements=floor_movements,
                          project_quantity_by_movement=project_quantity_by_movement,
                          quantities=quantities, equipment_list=equipment_list,
                          material_summary=material_summary,
                          material_plan_fact_rows=material_plan_fact_rows,
                          material_certificates_rows=material_certificates_rows,
                          filter_values=filter_values)

@bp.route('/floor/<int:floor_id>/upload_documents', methods=['POST'])
@login_required
def upload_documents(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    files = request.files.getlist('files[]')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    work_type_ids = request.form.getlist('work_type_ids')

    if not files:
        flash('Выберите файлы для загрузки', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))

    upload_dir = os.path.join(current_app.root_path, 'static', 'media', 'projects', str(floor.building.project_id), f'building_{floor.building_id}', f'floor_{floor_id}')
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        if file.filename == '':
            continue
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)
        try:
            file_modified_at = datetime.fromtimestamp(os.path.getmtime(file_path))
        except Exception:
            file_modified_at = datetime.utcnow()

        thumbnail_path = None
        width_px = height_px = None
        if original_filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            try:
                img = Image.open(file_path)
                width_px, height_px = img.size
                img.thumbnail((200, 200))
                thumb_filename = f"thumb_{unique_filename}"
                thumbnail_path = os.path.join(upload_dir, thumb_filename)
                img.save(thumbnail_path)
                thumbnail_path = thumbnail_path.replace(os.path.join(current_app.root_path, 'static'), '').replace('\\', '/').lstrip('/')
            except Exception as e:
                flash(f'Ошибка миниатюры: {str(e)}', 'warning')

        rel_path = file_path.replace(os.path.join(current_app.root_path, 'static'), '').replace('\\', '/').lstrip('/')

        doc = Document(
            project_id=floor.building.project_id,
            building_id=floor.building_id,
            floor_id=floor_id,
            title=title,
            description=description,
            filename=original_filename,
            stored_path=rel_path,
            thumbnail_path=thumbnail_path,
            file_size=os.path.getsize(file_path),
            uploaded_at=datetime.utcnow(),
            file_modified_at=file_modified_at,
            width_px=width_px,
            height_px=height_px,
            is_document_image=True if request.form.get('is_document_image') else False
        )
        db.session.add(doc)
        db.session.flush()  # Чтобы получить doc.id для ассоциаций

        # Добавляем виды работ / теги
        extra_tag_names = _parse_tags_raw(request.form.get('tags'))
        extra_type_ids = _ensure_doc_types_by_names(extra_tag_names) if extra_tag_names else []
        all_type_ids = sorted({int(wt) for wt in work_type_ids} | set(extra_type_ids)) if work_type_ids or extra_type_ids else []
        for wt_id in all_type_ids:
            stmt = document_work_types.insert().values(document_id=doc.id, doc_type_id=wt_id)
            db.session.execute(stmt)

    db.session.commit()
    flash('Документы загружены!', 'success')
    return redirect(url_for('floors.view_floor', floor_id=floor_id))


# Расширения файлов, считающихся изображениями (скан/фото документа → показывать в разделе «Документы», не в «Фото»)
_IMAGE_EXTENSIONS = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.tif'})


def _is_image_filename(filename):
    """Проверка по расширению: файл — изображение (скан/фото документа)."""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in _IMAGE_EXTENSIONS


def _save_floor_document(floor, file, title=None):
    """Сохранить один файл как документ этажа (сертификат/паспорт). Возвращает (doc, None) или (None, error_message).
    Файлы-изображения автоматически помечаются is_document_image=True, чтобы попадать в раздел «Документы», а не в «Фото»."""
    if not file or file.filename == '':
        return None, 'Выберите файл'
    upload_dir = os.path.join(current_app.root_path, 'static', 'media', 'projects', str(floor.building.project_id), f'building_{floor.building_id}', f'floor_{floor.id}')
    os.makedirs(upload_dir, exist_ok=True)
    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{original_filename}"
    file_path = os.path.join(upload_dir, unique_filename)
    file.save(file_path)
    try:
        file_modified_at = datetime.fromtimestamp(os.path.getmtime(file_path))
    except Exception:
        file_modified_at = datetime.utcnow()
    rel_path = file_path.replace(os.path.join(current_app.root_path, 'static'), '').replace('\\', '/').lstrip('/')
    # Загружено как документ (сертификат/паспорт) — если это картинка, сразу ставим флаг «скан документа»
    is_doc_image = _is_image_filename(original_filename)
    doc = Document(
        project_id=floor.building.project_id,
        building_id=floor.building_id,
        floor_id=floor.id,
        title=title,
        filename=original_filename,
        stored_path=rel_path,
        file_size=os.path.getsize(file_path),
        uploaded_at=datetime.utcnow(),
        file_modified_at=file_modified_at,
        is_document_image=is_doc_image
    )
    db.session.add(doc)
    db.session.commit()
    return doc, None


@bp.route('/floor/<int:floor_id>/upload_document_ajax', methods=['POST'])
@login_required
def upload_floor_document_ajax(floor_id):
    """Загрузка одного документа этажа (AJAX). Возвращает JSON { id, title } для подстановки в выпадающий список."""
    floor = Floor.query.get_or_404(floor_id)
    file = request.files.get('file')
    title = (request.form.get('title') or '').strip() or None
    doc, err = _save_floor_document(floor, file, title)
    if err:
        return jsonify({'error': err}), 400
    display = (doc.title or doc.filename or f'Документ #{doc.id}')[:80]
    return jsonify({'id': doc.id, 'title': display})


@bp.route('/floor/<int:floor_id>/upload_document', methods=['GET', 'POST'])
@login_required
def upload_floor_document(floor_id):
    """Загрузка одного документа этажа (сертификат, паспорт качества) с редиректом обратно в форму материала/оборудования."""
    floor = Floor.query.get_or_404(floor_id)
    if request.method == 'POST':
        file = request.files.get('file')
        title = (request.form.get('title') or '').strip() or None
        doc, err = _save_floor_document(floor, file, title)
        if err:
            flash(err, 'danger')
            return redirect(request.url)
        flash('Документ загружен. Выберите его в списке сертификата/паспорта.', 'success')
        return_to = request.form.get('return_to') or request.args.get('return_to', '')
        material_id = request.form.get('material_id') or request.args.get('material_id')
        equipment_id = request.form.get('equipment_id') or request.args.get('equipment_id')
        if return_to == 'edit_material' and material_id:
            return redirect(url_for('floors.edit_material', floor_id=floor_id, material_id=material_id, certificate_id=doc.id))
        if return_to == 'edit_equipment' and equipment_id:
            return redirect(url_for('floors.edit_equipment', floor_id=floor_id, equipment_id=equipment_id, passport_id=doc.id))
        if return_to == 'create_material':
            return redirect(url_for('floors.create_material', floor_id=floor_id))
        if return_to == 'create_equipment':
            return redirect(url_for('floors.create_equipment', floor_id=floor_id))
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    # GET: форма загрузки
    return_to = request.args.get('return_to', '')
    material_id = request.args.get('material_id', '')
    equipment_id = request.args.get('equipment_id', '')
    return render_template('floors/upload_document.html', floor=floor, return_to=return_to, material_id=material_id, equipment_id=equipment_id)


@bp.route('/floor/<int:floor_id>/create_material', methods=['GET', 'POST'])
@login_required
def create_material(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    form = MaterialForm()
    # SelectField требуют заданные choices до валидации
    form.category_id.choices = [('', '— не выбрано —')] + [
        (str(c.id), c.name) for c in MaterialCategory.query.order_by(MaterialCategory.name).all()
    ]
    form.certificate_document_id.choices = _floor_document_choices(floor)
    if form.validate_on_submit():
        cert_id = form.certificate_document_id.data
        category_id_val = form.category_id.data
        material = FloorMaterial(
            floor_id=floor_id,
            name=form.name.data,
            brand=form.brand.data,
            gost=form.gost.data,
            planned_quantity=form.planned_quantity.data,
            actual_quantity=form.actual_quantity.data,
            unit=form.unit.data,
            price_per_unit=form.price_per_unit.data,
            note=form.note.data,
            certificate_document_id=int(cert_id) if cert_id else None,
            category_id=int(category_id_val) if category_id_val else None
        )
        db.session.add(material)
        db.session.commit()
        flash('Материал добавлен', 'success')
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    
    return render_template('floors/create_material.html', form=form, floor=floor, title='Добавить материал')

@bp.route('/floor/<int:floor_id>/edit_material/<int:material_id>', methods=['GET', 'POST'])
@login_required
def edit_material(floor_id, material_id):
    floor = Floor.query.get_or_404(floor_id)
    material = FloorMaterial.query.get_or_404(material_id)
    if material.floor_id != floor_id:
        flash('Материал не принадлежит этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))
    
    form = MaterialForm(obj=material)
    # SelectField требуют заданные choices до валидации
    form.category_id.choices = [('', '— не выбрано —')] + [
        (str(c.id), c.name) for c in MaterialCategory.query.order_by(MaterialCategory.name).all()
    ]
    form.certificate_document_id.choices = _floor_document_choices(floor)
    if request.args.get('certificate_id'):
        form.certificate_document_id.data = request.args.get('certificate_id')
    if form.validate_on_submit():
        form.populate_obj(material)
        material.certificate_document_id = int(form.certificate_document_id.data) if form.certificate_document_id.data else None
        material.category_id = int(form.category_id.data) if form.category_id.data else None
        db.session.commit()
        flash('Материал обновлён', 'success')
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    
    return render_template('floors/edit_material.html', 
                           form=form, 
                           floor=floor,
                           material=material,
                           title='Редактировать материал')

@bp.route('/floor/<int:floor_id>/delete_material/<int:material_id>', methods=['POST'])
@login_required
def delete_material(material_id):
    material = FloorMaterial.query.get_or_404(material_id)
    floor_id = material.floor_id
    db.session.delete(material)
    db.session.commit()
    flash('Материал удалён', 'info')
    return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')


@bp.route('/floor/<int:floor_id>/create_quantity', methods=['GET', 'POST'])
@login_required
def create_quantity(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    form = FloorQuantityForm()
    if form.validate_on_submit():
        qty = FloorQuantity(
            floor_id=floor_id,
            name=form.name.data,
            quantity=form.quantity.data,
            unit=form.unit.data or 'м²',
            note=form.note.data
        )
        db.session.add(qty)
        db.session.commit()
        flash('Величина добавлена', 'success')
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    return render_template('floors/create_quantity.html', form=form, floor=floor, title='Добавить площадь / величину')


@bp.route('/floor/<int:floor_id>/edit_quantity/<int:quantity_id>', methods=['GET', 'POST'])
@login_required
def edit_quantity(floor_id, quantity_id):
    floor = Floor.query.get_or_404(floor_id)
    qty = FloorQuantity.query.get_or_404(quantity_id)
    if qty.floor_id != floor_id:
        flash('Величина не принадлежит этому этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))
    form = FloorQuantityForm(obj=qty)
    if form.validate_on_submit():
        qty.name = form.name.data
        qty.quantity = form.quantity.data
        qty.unit = form.unit.data or 'м²'
        qty.note = form.note.data
        db.session.commit()
        flash('Величина обновлена', 'success')
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    return render_template('floors/edit_quantity.html', form=form, floor=floor, quantity=qty, title='Редактировать величину')


@bp.route('/floor/<int:floor_id>/delete_quantity/<int:quantity_id>', methods=['POST'])
@login_required
def delete_quantity(floor_id, quantity_id):
    qty = FloorQuantity.query.get_or_404(quantity_id)
    if qty.floor_id != floor_id:
        flash('Величина не принадлежит этому этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))
    floor_id = qty.floor_id
    db.session.delete(qty)
    db.session.commit()
    flash('Величина удалена', 'info')
    return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')


@bp.route('/floor/<int:floor_id>/create_equipment', methods=['GET', 'POST'])
@login_required
def create_equipment(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    form = FloorEquipmentForm()
    form.passport_document_id.choices = _floor_document_choices(floor)
    if form.validate_on_submit():
        passport_id = form.passport_document_id.data
        eq = FloorEquipment(
            floor_id=floor_id,
            name=form.name.data,
            brand=form.brand.data,
            passport_document_id=int(passport_id) if passport_id else None,
            note=form.note.data
        )
        db.session.add(eq)
        db.session.commit()
        flash('Оборудование добавлено', 'success')
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    return render_template('floors/create_equipment.html', form=form, floor=floor, title='Добавить оборудование')


@bp.route('/floor/<int:floor_id>/edit_equipment/<int:equipment_id>', methods=['GET', 'POST'])
@login_required
def edit_equipment(floor_id, equipment_id):
    floor = Floor.query.get_or_404(floor_id)
    eq = FloorEquipment.query.get_or_404(equipment_id)
    if eq.floor_id != floor_id:
        flash('Оборудование не принадлежит этому этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))
    form = FloorEquipmentForm(obj=eq)
    form.passport_document_id.choices = _floor_document_choices(floor)
    if request.args.get('passport_id'):
        form.passport_document_id.data = request.args.get('passport_id')
    if form.validate_on_submit():
        eq.name = form.name.data
        eq.brand = form.brand.data
        eq.note = form.note.data
        passport_id = form.passport_document_id.data
        eq.passport_document_id = int(passport_id) if passport_id else None
        db.session.commit()
        flash('Оборудование обновлено', 'success')
        return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#tech')
    return render_template('floors/edit_equipment.html', form=form, floor=floor, equipment=eq, title='Редактировать оборудование')


@bp.route('/floor/<int:floor_id>/delete_equipment/<int:equipment_id>', methods=['POST'])
@login_required
def delete_equipment(floor_id, equipment_id):
    eq = FloorEquipment.query.get_or_404(equipment_id)
    if eq.floor_id != floor_id:
        flash('Оборудование не принадлежит этому этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))
    fid = eq.floor_id
    db.session.delete(eq)
    db.session.commit()
    flash('Оборудование удалено', 'info')
    return redirect(url_for('floors.view_floor', floor_id=fid) + '#tech')

@bp.route('/floor/<int:floor_id>/plan/<int:plan_id>')
@login_required
def floor_plan(floor_id, plan_id):
    floor = Floor.query.get_or_404(floor_id)
    plan = Plan.query.get_or_404(plan_id)
    if plan.floor_id != floor_id:
        flash('План не принадлежит этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))
    
    # Фильтрация документов (GET-параметры)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    work_types_str = request.args.get('work_types')
    
    docs_query = Document.query.filter(Document.floor_id == floor_id, Document.mark_id.isnot(None))
    
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            docs_query = docs_query.filter(Document.uploaded_at >= start_date)
        except ValueError:
            flash('Неверный формат даты начала', 'warning')
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            docs_query = docs_query.filter(Document.uploaded_at <= end_date)
        except ValueError:
            flash('Неверный формат даты окончания', 'warning')
    if work_types_str:
        work_type_ids = [int(wt) for wt in work_types_str.split(',') if wt.isdigit()]
        if work_type_ids:
            docs_query = docs_query.join(document_work_types).join(DocType).filter(DocType.id.in_(work_type_ids))
    
    filtered_documents = docs_query.order_by(
        Document.file_modified_at.desc().nullslast(),
        Document.uploaded_at.desc()
    ).all()
    all_work_types = DocType.query.order_by(DocType.sort_order).all()
    marks = plan.marks.all()
    highlight_mark_id = request.args.get('highlight_mark', type=int)
    back_url = request.args.get('back')
    embed = request.args.get('embed') == '1'

    # Режимы отображения: обычный план / план с маркерами / «меточный» план
    show_marks = request.args.get('show_marks', '0') == '1'
    only_mark_id = request.args.get('only_mark', type=int)

    template_name = 'floors/plan_embed.html' if embed else 'floors/floor_plan.html'

    return render_template(
        template_name,
        floor=floor,
        plan=plan,
        marks=marks,
        plans=floor.plans.all(),
        documents=filtered_documents,
        all_work_types=all_work_types,
        current_filters={'start_date': start_date_str, 'end_date': end_date_str, 'work_types': work_types_str},
        highlight_mark_id=highlight_mark_id,
        show_marks=show_marks,
        only_mark_id=only_mark_id,
        back_url=back_url,
    )


@bp.route('/floor/<int:floor_id>/plan/<int:plan_id>/add_mark', methods=['POST'])
@login_required
def add_mark(floor_id, plan_id):
    """Добавление метки на плане по клику: сохраняем относительные координаты и комментарий."""
    floor = Floor.query.get_or_404(floor_id)
    plan = Plan.query.get_or_404(plan_id)
    if plan.floor_id != floor.id:
        flash('План не принадлежит этому этажу', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))

    try:
        x = float(request.form.get('x', '').replace(',', '.'))
        y = float(request.form.get('y', '').replace(',', '.'))
    except ValueError:
        flash('Не удалось определить координаты метки. Повторите выбор точки на плане.', 'warning')
        return redirect(url_for('floors.floor_plan', floor_id=floor_id, plan_id=plan_id))

    note = request.form.get('note') or None

    mark = Mark(
        plan_id=plan.id,
        floor_id=floor.id,
        x=x,
        y=y,
        note=note
    )
    db.session.add(mark)
    db.session.commit()

    flash('Метка добавлена на план этажа', 'success')
    return redirect(url_for('floors.floor_plan', floor_id=floor_id, plan_id=plan_id))

@bp.route('/floor/<int:floor_id>/upload_plan', methods=['POST'])
@login_required
def upload_floor_plan(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    file = request.files.get('plan_file')
    custom_name = request.form.get('custom_name', 'Новый план').strip()
    page_number = request.form.get('page_number', type=int, default=1)

    if not file:
        flash('Выберите файл', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor_id))

    filename = secure_filename(file.filename)
    plan_dir = os.path.join(current_app.root_path, 'static', 'media', 'plans', str(floor_id))
    os.makedirs(plan_dir, exist_ok=True)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = os.path.join(plan_dir, unique_filename)
    file.save(filepath)

    image_path = None
    if filename.lower().endswith('.pdf'):
        try:
            pdf = fitz.open(filepath)
            if page_number < 1 or page_number > len(pdf):
                flash(f'Страница {page_number} вне диапазона', 'danger')
                os.remove(filepath)
                return redirect(url_for('floors.view_floor', floor_id=floor_id))
            page = pdf.load_page(page_number - 1)
            pix = page.get_pixmap(dpi=150)
            image_filename = f"{os.path.splitext(unique_filename)[0]}_page_{page_number}.png"
            image_path = os.path.join(plan_dir, image_filename)
            pix.save(image_path)
        except Exception as e:
            flash(f'Ошибка PDF: {str(e)}', 'danger')
            os.remove(filepath)
            return redirect(url_for('floors.view_floor', floor_id=floor_id))
    else:
        image_path = filepath

    rel_image_path = image_path.replace(os.path.join(current_app.root_path, 'static'), '').replace('\\', '/').lstrip('/')

    new_plan = Plan(
        floor_id=floor_id,
        name=custom_name,
        image_path=rel_image_path,
        uploaded_at=datetime.utcnow(),
        is_active=True
    )
    db.session.add(new_plan)
    db.session.commit()
    flash(f'План "{custom_name}" загружен', 'success')
    return redirect(url_for('floors.floor_plan', floor_id=floor_id, plan_id=new_plan.id))

@bp.route('/delete_document/<int:doc_id>', methods=['POST'])
@login_required
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    floor_id = doc.floor_id
    if not floor_id:
        flash('Документ не связан с этажом', 'danger')
        return redirect(url_for('buildings.view_building', building_id=doc.building_id))
    db.session.delete(doc)
    db.session.commit()
    flash(f'Документ "{doc.filename}" удалён из базы (файл на диске сохранён)', 'info')
    return redirect(url_for('floors.view_floor', floor_id=floor_id) + '#docs')

@bp.route('/photo/<int:photo_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_photo(photo_id):
    """Редактирование фото: название, описание, дата съёмки, привязка к метке на плане."""
    doc = Document.query.get_or_404(photo_id)
    if not doc.floor_id:
        flash('Фото не привязано к этажу', 'danger')
        return redirect(url_for('main.index'))
    floor = Floor.query.get_or_404(doc.floor_id)
    building = floor.building
    project = building.project if building else None
    marks = Mark.query.filter_by(floor_id=floor.id).order_by(Mark.id).all()
    all_doc_types = DocType.query.order_by(DocType.sort_order).all()
    current_types = [wt.id for wt in doc.work_types]
    buildings = Building.query.filter_by(project_id=project.id).order_by(Building.name).all() if project else []
    project_floors = Floor.query.join(Building).filter(Building.project_id == project.id).order_by(Building.name, Floor.name).all() if project else []

    if request.method == 'POST':
        doc.title = request.form.get('title') or None
        doc.description = request.form.get('description') or None
        # Виды работ / теги: из чекбоксов + свободный ввод
        new_work_type_ids = [int(x) for x in request.form.getlist('work_type_ids') if x.isdigit()]
        extra_tag_names = _parse_tags_raw(request.form.get('tags'))
        extra_type_ids = _ensure_doc_types_by_names(extra_tag_names) if extra_tag_names else []
        all_type_ids = sorted(set(new_work_type_ids or []) | set(extra_type_ids))
        if all_type_ids:
            doc.work_types = DocType.query.filter(DocType.id.in_(all_type_ids)).all()
        else:
            doc.work_types = []
        file_modified_str = request.form.get('file_modified_date')
        if file_modified_str:
            try:
                doc.file_modified_at = datetime.strptime(file_modified_str, '%Y-%m-%d')
            except ValueError:
                doc.file_modified_at = None
        else:
            doc.file_modified_at = None
        # Признак «скан документа» (изображение должно вести себя как документ)
        doc.is_document_image = True if request.form.get('is_document_image') else False

        # Привязка к корпусу и этажу (перемещение фото)
        building_id = request.form.get('building_id', type=int)
        floor_id = request.form.get('floor_id', type=int)

        new_building = None
        new_floor = None
        if building_id:
            new_building = Building.query.get_or_404(building_id)
            if project and new_building.project_id != project.id:
                flash('Выбранный корпус не принадлежит текущему объекту', 'danger')
                return redirect(url_for('floors.edit_photo', photo_id=photo_id))
        if floor_id:
            new_floor = Floor.query.get_or_404(floor_id)
            if project and new_floor.building.project_id != project.id:
                flash('Выбранный этаж не принадлежит текущему объекту', 'danger')
                return redirect(url_for('floors.edit_photo', photo_id=photo_id))
            new_building = new_floor.building

        if not floor_id and new_building:
            new_floor = None

        # Если фото было привязано к маркеру, а этаж меняется/убирается — отвязываем маркер
        if doc.mark_id:
            mark = Mark.query.get(doc.mark_id)
            needs_unbind = False
            if not mark:
                needs_unbind = True
            else:
                if not new_floor or mark.floor_id != new_floor.id:
                    needs_unbind = True
            if needs_unbind:
                if mark:
                    docs_count = mark.documents.count()
                doc.mark_id = None
                if mark and docs_count <= 1:
                    db.session.delete(mark)

        doc.building_id = new_building.id if new_building else doc.building_id
        doc.floor_id = new_floor.id if new_floor else doc.floor_id
        db.session.commit()
        flash('Фото успешно обновлено', 'success')
        return redirect(url_for('floors.view_floor', floor_id=doc.floor_id) + '#media')

    return render_template('floors/edit_photo.html', doc=doc, floor=floor, marks=marks,
                           all_doc_types=all_doc_types, current_types=current_types,
                           buildings=buildings, project_floors=project_floors)


@bp.route('/photo/<int:photo_id>/select_mark')
@login_required
def select_mark_for_photo(photo_id):
    """Выбор плана и точки на плане для привязки фото к метке."""
    doc = Document.query.get_or_404(photo_id)
    if not doc.floor_id:
        flash('Фото не привязано к этажу, выбор точки на плане невозможен.', 'danger')
        return redirect(url_for('floors.edit_photo', photo_id=photo_id))

    floor = Floor.query.get_or_404(doc.floor_id)
    plans = Plan.query.filter_by(floor_id=floor.id).order_by(Plan.uploaded_at.desc()).all()
    if not plans:
        flash('Для этого этажа ещё не загружены планы. Сначала загрузите план этажа.', 'warning')
        return redirect(url_for('floors.edit_photo', photo_id=photo_id))

    # Активный план — из querystring или первый по дате
    active_plan_id = request.args.get('plan_id', type=int)
    active_plan = None
    if active_plan_id:
        active_plan = next((p for p in plans if p.id == active_plan_id), None)
    if not active_plan:
        active_plan = plans[0]

    marks = active_plan.marks.all()

    return render_template(
        'floors/select_mark_for_photo.html',
        doc=doc,
        floor=floor,
        plans=plans,
        plan=active_plan,
        marks=marks
    )


@bp.route('/photo/<int:photo_id>/bind_mark', methods=['POST'])
@login_required
def bind_mark_to_photo(photo_id):
    """Создать метку на плане и привязать её к фото."""
    doc = Document.query.get_or_404(photo_id)
    if not doc.floor_id:
        flash('Фото не привязано к этажу, выбор точки на плане невозможен.', 'danger')
        return redirect(url_for('floors.edit_photo', photo_id=photo_id))

    floor = Floor.query.get_or_404(doc.floor_id)
    plan_id = request.form.get('plan_id', type=int)
    plan = Plan.query.get_or_404(plan_id) if plan_id else None
    if not plan or plan.floor_id != floor.id:
        flash('Выбран некорректный план этажа.', 'danger')
        return redirect(url_for('floors.select_mark_for_photo', photo_id=photo_id))

    try:
        x = float((request.form.get('x') or '').replace(',', '.'))
        y = float((request.form.get('y') or '').replace(',', '.'))
    except ValueError:
        flash('Не удалось определить координаты метки. Повторите выбор точки на плане.', 'warning')
        return redirect(url_for('floors.select_mark_for_photo', photo_id=photo_id, plan_id=plan.id))

    note = request.form.get('note') or None

    mark = Mark(
        plan_id=plan.id,
        floor_id=floor.id,
        x=x,
        y=y,
        note=note
    )
    db.session.add(mark)
    db.session.flush()  # получаем mark.id до коммита

    doc.mark_id = mark.id
    db.session.commit()

    flash('Фото привязано к выбранной точке на плане этажа.', 'success')
    return redirect(url_for('floors.edit_photo', photo_id=photo_id))


@bp.route('/photo/<int:photo_id>/delete_mark', methods=['POST'])
@login_required
def delete_mark_from_photo(photo_id):
    """Удалить текущую метку у фото (и саму метку, если она больше ни к чему не привязана)."""
    doc = Document.query.get_or_404(photo_id)
    if not doc.mark_id:
        flash('У фото нет привязанной метки.', 'warning')
        return redirect(url_for('floors.edit_photo', photo_id=photo_id))

    mark = Mark.query.get(doc.mark_id)
    if not mark:
        doc.mark_id = None
        db.session.commit()
        flash('Привязка к метке удалена.', 'info')
        return redirect(url_for('floors.edit_photo', photo_id=photo_id))

    # Сколько документов используют эту метку
    docs_count = mark.documents.count()
    doc.mark_id = None

    if docs_count <= 1:
        db.session.delete(mark)

    db.session.commit()
    flash('Привязка фото к метке удалена.', 'success')
    return redirect(url_for('floors.edit_photo', photo_id=photo_id))


@bp.route('/edit_document/<int:doc_id>', methods=['GET', 'POST'])
@login_required
def edit_document(doc_id):
    """Для совместимости: перенаправляем на единый редактор документов на уровне проекта."""
    doc = Document.query.get_or_404(doc_id)
    return redirect(url_for('project.edit_document', doc_id=doc.id))

@bp.route('/document/<int:doc_id>/view')
@login_required
def view_document(doc_id):
    """Безопасный просмотр/скачивание документа"""
    doc = Document.query.get_or_404(doc_id)
    
    # Проверка через g.floor (уже установлен before_request)
    if doc.floor_id != g.floor.id:
        abort(403, "Доступ запрещён: документ не принадлежит этому этажу")
    
    # Правильный full_path с добавлением 'static'
    full_path = os.path.join(current_app.root_path, 'static', doc.stored_path.lstrip('/'))
    
    if not os.path.isfile(full_path):
        abort(404, f"Файл не найден на сервере: {full_path}")
    
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    
    # По умолчанию открываем в браузере; при ?download=1 отдаём как вложение
    force_download = request.args.get('download') == '1'
    
    return send_from_directory(
        directory,
        filename,
        as_attachment=force_download,
        download_name=doc.filename
    )