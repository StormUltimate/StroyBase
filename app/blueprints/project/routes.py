# app/blueprints/project/routes.py — StroyBase
# Проекты: дашборд, документы, загрузка. upload_documents с опциональным building_id.

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify, send_from_directory, send_file, abort
from flask_login import login_required
from app.extensions import db
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import or_, and_, text, bindparam
from types import SimpleNamespace
from app.models import Project, Building, Floor, Document, DocType, Plan, document_work_types, ScheduleWork, PlanTask, DailyWorkforce, WorkPerformer, Mark, FloorMaterial, MaterialCategory, MaterialMovement, Work, WorkProgress, FloorQuantity
from werkzeug.utils import secure_filename
from datetime import datetime, date
import calendar
import os
import tempfile
import subprocess
import sys
from io import BytesIO
from PIL import Image
import fitz  # PyMuPDF
import uuid
import psycopg2

# Создание блюпринта
project_bp = Blueprint('project', __name__, url_prefix='/project')


def _extract_db_programming_error(exc):
    """Вернуть psycopg2.ProgrammingError (если вложен в SQLAlchemy-исключение) или исходную ошибку."""
    if isinstance(exc, psycopg2.ProgrammingError):
        return exc
    orig = getattr(exc, "orig", None)
    if isinstance(orig, psycopg2.ProgrammingError):
        return orig
    return exc


def _format_db_programming_error(exc):
    """Преобразовать ошибку БД в человекочитаемое сообщение для UI."""
    msg = str(exc)
    lower = msg.lower()
    if 'relation "work_progress" does not exist' in lower:
        return 'Таблица work_progress отсутствует. Структура БД устарела. Запустите миграции: flask db upgrade.'
    if 'column "initial_executed" does not exist' in lower:
        return 'В таблице works отсутствует столбец initial_executed. Структура БД устарела. Запустите миграции: flask db upgrade.'
    if 'column "date" does not exist' in lower:
        return 'В таблице work_progress отсутствует столбец date. Структура БД устарела. Запустите миграции: flask db upgrade.'
    return f'Ошибка БД: {msg}. Проверьте структуру таблиц.'

@project_bp.route('/<int:project_id>/dashboard')
@login_required
def dashboard(project_id):
    project = Project.query.get_or_404(project_id)
    buildings = Building.query.filter_by(project_id=project_id).order_by(Building.name).all()
    doc_types = DocType.query.order_by(DocType.sort_order).all()

    # Фильтры из GET
    building_id = request.args.get('building_id', type=int)
    floor_id = request.args.get('floor_id', type=int)
    doc_type_id = request.args.get('doc_type_id', type=int)
    media_type = request.args.get('media_type', 'all')
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')

    # Базовый запрос по проекту
    query = Document.query.filter_by(project_id=project_id)

    # Фильтр по корпусу (если указан)
    if building_id is not None:
        query = query.filter_by(building_id=building_id)
    # Фильтр по этажу (если указан)
    if floor_id is not None:
        query = query.filter_by(floor_id=floor_id)

    # Фильтр по виду работ
    if doc_type_id:
        query = query.join(document_work_types).filter(document_work_types.c.doc_type_id == doc_type_id)

    # Фильтр по дате файла (file_modified_at)
    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            query = query.filter(Document.file_modified_at.isnot(None),
                                 Document.file_modified_at >= from_date)
        except ValueError:
            flash('Неверный формат даты файла "от"', 'warning')
    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            query = query.filter(Document.file_modified_at.isnot(None),
                                 Document.file_modified_at <= to_date)
        except ValueError:
            flash('Неверный формат даты файла "до"', 'warning')

    # Получить все отфильтрованные документы (сначала по дате файла, затем по дате загрузки)
    all_docs = query.order_by(
        Document.file_modified_at.desc().nullslast(),
        Document.uploaded_at.desc()
    ).all()

    # Разделение на медиа и документы
    media_docs = []
    doc_docs = []
    photo_ext = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    video_ext = ('.mp4', '.avi', '.mov', '.webm')

    for doc in all_docs:
        filename_lower = (doc.filename or '').lower()
        is_photo = filename_lower.endswith(photo_ext)
        is_video = filename_lower.endswith(video_ext)
        # Скан документа в виде изображения всегда идёт во вкладку «Документы»
        if is_photo and getattr(doc, 'is_document_image', None):
            doc_docs.append(doc)
            continue
        if is_photo or is_video:
            if media_type == 'all' or \
               (media_type == 'photo' and is_photo) or \
               (media_type == 'video' and is_video):
                media_docs.append(doc)
        else:
            doc_docs.append(doc)

    # Все этажи проекта (для фильтра по этажам)
    project_floors = Floor.query.join(Building).filter(Building.project_id == project_id).order_by(Building.name, Floor.name).all()

    # Сводная тех. информация по материалам проекта (для вкладки «Тех. информация»)
    from decimal import Decimal
    project_material_summary = []
    try:
        project_materials = (
            FloorMaterial.query
            .join(Floor, FloorMaterial.floor_id == Floor.id)
            .join(Building, Floor.building_id == Building.id)
            .filter(Building.project_id == project_id)
            .all()
        )
        project_material_summary_map = {}
        for m in project_materials:
            category_name = m.category.name if getattr(m, "category", None) else None
            key = (category_name, m.name, m.brand or m.gost or None, m.unit or None)
            if key not in project_material_summary_map:
                project_material_summary_map[key] = {
                    "category": category_name,
                    "name": m.name,
                    "brand": m.brand or m.gost or None,
                    "unit": m.unit or None,
                    "planned_total": Decimal("0"),
                    "actual_total": Decimal("0"),
                    "total_cost": Decimal("0"),
                }
            row = project_material_summary_map[key]
            if m.planned_quantity is not None:
                row["planned_total"] += Decimal(m.planned_quantity)
            if m.actual_quantity is not None:
                row["actual_total"] += Decimal(m.actual_quantity)
            if hasattr(m, "total_cost") and m.total_cost is not None:
                row["total_cost"] += Decimal(str(m.total_cost))

        project_material_summary = sorted(
            project_material_summary_map.values(),
            key=lambda r: (
                r["category"] or "",
                r["name"] or "",
                r["brand"] or "",
            ),
        )
    except ProgrammingError:
        db.session.rollback()
        project_material_summary = []

    # Сводка площадей и величин по объекту: группировка по наименованию и единице по всем этажам проекта
    project_quantities_summary = []
    try:
        project_quantities = (
            FloorQuantity.query
            .join(Floor, FloorQuantity.floor_id == Floor.id)
            .join(Building, Floor.building_id == Building.id)
            .filter(Building.project_id == project_id)
            .all()
        )
        quantities_map = {}
        for q in project_quantities:
            key = (q.name or '—', (q.unit or '').strip() or None)
            if key not in quantities_map:
                quantities_map[key] = {
                    "name": q.name or '—',
                    "unit": q.unit or None,
                    "total_quantity": Decimal("0"),
                }
            row = quantities_map[key]
            if q.quantity is not None:
                row["total_quantity"] += Decimal(str(q.quantity))
        project_quantities_summary = sorted(
            quantities_map.values(),
            key=lambda r: (r["name"] or "", r["unit"] or ""),
        )
    except ProgrammingError:
        db.session.rollback()
        project_quantities_summary = []

    # Фильтры для вкладки "Графики" на уровне проекта
    graphs_building_id = request.args.get('graphs_building_id', type=int)
    graphs_floor_id = request.args.get('graphs_floor_id', type=int)
    graphs_status = (request.args.get('graphs_status') or '').strip() or None
    graphs_from_str = request.args.get('graphs_from')
    graphs_to_str = request.args.get('graphs_to')

    # Графики и люди: свод работ по объекту + учёт людей по дням (таблицы могут отсутствовать в БД)
    try:
        sw_query = ScheduleWork.query.outerjoin(Building, ScheduleWork.building_id == Building.id)
        # Работы, явно привязанные к проекту, или работы корпусов этого проекта (для старых записей без project_id)
        sw_query = sw_query.filter(
            or_(
                ScheduleWork.project_id == project_id,
                Building.project_id == project_id
            )
        )
        if graphs_building_id:
            sw_query = sw_query.filter(
                or_(
                    ScheduleWork.building_id == graphs_building_id,
                    Building.id == graphs_building_id
                )
            )
        if graphs_floor_id:
            sw_query = sw_query.filter(ScheduleWork.floor_id == graphs_floor_id)
        if graphs_status:
            sw_query = sw_query.filter(ScheduleWork.status == graphs_status)
        if graphs_from_str:
            from_date = _parse_date_project(graphs_from_str)
            if from_date:
                sw_query = sw_query.filter(
                    ScheduleWork.planned_start.isnot(None),
                    ScheduleWork.planned_start >= from_date
                )
            else:
                flash('Неверный формат даты "от" для графиков', 'warning')
        if graphs_to_str:
            to_date = _parse_date_project(graphs_to_str)
            if to_date:
                sw_query = sw_query.filter(
                    ScheduleWork.planned_end.isnot(None),
                    ScheduleWork.planned_end <= to_date
                )
            else:
                flash('Неверный формат даты "до" для графиков', 'warning')
        project_schedule_works = sw_query.order_by(
            ScheduleWork.planned_start.asc().nullslast(),
            ScheduleWork.id
        ).all()
    except ProgrammingError:
        db.session.rollback()
        project_schedule_works = []
    try:
        daily_workforce = DailyWorkforce.query.filter_by(project_id=project_id).order_by(DailyWorkforce.date.desc().nullslast()).all()
    except Exception:
        db.session.rollback()
        daily_workforce = []
    # Уже отсортировано по date desc в запросе
    # Итого по дням для колонки «Итого за день»
    daily_totals = {}
    for r in daily_workforce:
        if r.date:
            if r.date not in daily_totals:
                daily_totals[r.date] = {'workers': 0, 'hours': 0.0}
            daily_totals[r.date]['workers'] += (r.workers_count or 0)
            daily_totals[r.date]['hours'] += (r.shift_hours or 0.0) + (getattr(r, 'shift_hours_night', None) or 0.0)

    # Справочник исполнителей работ (таблица может отсутствовать)
    try:
        work_performers = WorkPerformer.query.filter_by(project_id=project_id).order_by(WorkPerformer.name).all()
    except Exception:
        db.session.rollback()
        work_performers = []

    # Календарь на месяц: выбранный месяц и список дней с итогами и записями
    today = date.today()
    calendar_year = request.args.get('calendar_year', type=int) or today.year
    calendar_month = request.args.get('calendar_month', type=int) or today.month
    if calendar_month < 1:
        calendar_month = 1
    if calendar_month > 12:
        calendar_month = 12
    if calendar_year < 2000:
        calendar_year = today.year
    month_days = calendar.monthrange(calendar_year, calendar_month)[1]
    daily_workforce_by_date = {}
    for r in daily_workforce:
        if r.date:
            daily_workforce_by_date.setdefault(r.date, []).append(r)
    calendar_days = []
    for day in range(1, month_days + 1):
        d = date(calendar_year, calendar_month, day)
        recs = daily_workforce_by_date.get(d, [])
        th = sum((x.shift_hours or 0.0) + (getattr(x, 'shift_hours_night', None) or 0.0) for x in recs)
        # Отдельно по сменам: люди день (workers_count) и ночь (workers_count_night)
        tw_day = sum(x.workers_count or 0 for x in recs)
        tw_night = sum(getattr(x, 'workers_count_night', None) or 0 for x in recs)
        tw = tw_day + tw_night  # общее число учтённых человек-смен
        th_day = sum(x.shift_hours or 0.0 for x in recs)
        th_night = sum(getattr(x, 'shift_hours_night', None) or 0.0 for x in recs)
        calendar_days.append({
            'date': d, 'day': day, 'total_workers': tw, 'total_hours': th, 'records': recs,
            'total_workers_day': tw_day, 'total_workers_night': tw_night,
            'total_hours_day': th_day, 'total_hours_night': th_night,
        })
    first_weekday = calendar.weekday(calendar_year, calendar_month, 1)
    calendar_cells = [None] * first_weekday
    for cell in calendar_days:
        calendar_cells.append(cell)
    while len(calendar_cells) < 42:
        calendar_cells.append(None)
    calendar_rows = [calendar_cells[i * 7:(i + 1) * 7] for i in range(6)]
    month_name_ru = ('Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь')[calendar_month - 1]
    if calendar_month == 1:
        prev_month, prev_year = 12, calendar_year - 1
    else:
        prev_month, prev_year = calendar_month - 1, calendar_year
    if calendar_month == 12:
        next_month, next_year = 1, calendar_year + 1
    else:
        next_month, next_year = calendar_month + 1, calendar_year

    total_floors_area = sum((f.total_area_m2 or 0) for f in project_floors) if project_floors else 0

    try:
        project_movements = MaterialMovement.query.filter_by(project_id=project_id).order_by(
            MaterialMovement.movement_date.desc().nullslast(),
            MaterialMovement.created_at.desc()
        ).limit(30).all()
    except ProgrammingError:
        db.session.rollback()
        project_movements = []

    plan_tasks = []
    gantt_mermaid = ''
    try:
        plan_tasks = PlanTask.query.filter_by(project_id=project_id).order_by(
            PlanTask.sort_order.asc().nullslast(),
            PlanTask.start_date.asc().nullslast(),
            PlanTask.id
        ).all()
        gantt_mermaid = _build_gantt_mermaid(plan_tasks)
    except ProgrammingError:
        db.session.rollback()

    # Works (works/work_progress): сводка и детализация по корпусам
    graphs_works_from_str = request.args.get('graphs_works_from')
    graphs_works_to_str = request.args.get('graphs_works_to')
    works_by_building, works_summary_project, works_summary_buildings = _build_works_summary(
        project_id, buildings, graphs_building_id, graphs_works_from_str, graphs_works_to_str
    )
    works_aggregated_by_name = _build_works_aggregated_by_name(project_id, graphs_works_from_str, graphs_works_to_str)

    return render_template('project/dashboard.html', project=project, buildings=buildings, project_floors=project_floors,
                           project_movements=project_movements,
                           total_floors_area=total_floors_area,
                           doc_types=doc_types, media_docs=media_docs, doc_docs=doc_docs,
                           project_schedule_works=project_schedule_works, daily_workforce=daily_workforce,
                           daily_totals=daily_totals, work_performers=work_performers,
                           calendar_year=calendar_year, calendar_month=calendar_month, calendar_days=calendar_days,
                           calendar_cells=calendar_cells, calendar_rows=calendar_rows, month_name_ru=month_name_ru,
                           prev_month=prev_month, prev_year=prev_year, next_month=next_month, next_year=next_year,
                           daily_workforce_by_date=daily_workforce_by_date,
                           graphs_building_id=graphs_building_id,
                           graphs_floor_id=graphs_floor_id,
                           graphs_status=graphs_status,
                           graphs_from_str=graphs_from_str,
                           graphs_to_str=graphs_to_str,
                           project_material_summary=project_material_summary,
                           project_quantities_summary=project_quantities_summary,
                           plan_tasks=plan_tasks,
                           gantt_mermaid=gantt_mermaid,
                           works_by_building=works_by_building,
                           works_summary_project=works_summary_project,
                           works_summary_buildings=works_summary_buildings,
                           works_aggregated_by_name=works_aggregated_by_name,
                           graphs_works_from_str=graphs_works_from_str,
                           graphs_works_to_str=graphs_works_to_str,
                           root_path=current_app.root_path.replace('\\', '/'))


def _parse_date_project(value):
    """Вернуть date или None из строки YYYY-MM-DD."""
    if not value or not str(value).strip():
        return None
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _build_works_summary_fallback(project_id, buildings, graphs_building_id=None, graphs_works_from_str=None, graphs_works_to_str=None):
    """Запасной путь без колонки initial_executed: загрузка через сырой SQL, initial_executed = 0."""
    works_by_building = []
    works_summary_project = {'total_volume': 0.0, 'total_executed': 0.0, 'percent': None}
    works_summary_buildings = []
    try:
        from_date_works = _parse_date_project(graphs_works_from_str) if graphs_works_from_str else None
        to_date_works = _parse_date_project(graphs_works_to_str) if graphs_works_to_str else None
        sql_works = (
            "SELECT id, project_id, building_id, name, volume, unit, planned_completion_date, percent_complete, sort_order, notes "
            "FROM works WHERE project_id = :pid"
        )
        params = {"pid": project_id}
        if graphs_building_id:
            sql_works += " AND building_id = :bid"
            params["bid"] = graphs_building_id
        sql_works += " ORDER BY sort_order ASC NULLS LAST, id"
        rows = db.session.execute(text(sql_works), params).fetchall()
        work_ids = [r[0] for r in rows]
        progress_by_work = {}
        if work_ids:
            t = text("SELECT work_id, date, daily_execution FROM work_progress WHERE work_id IN :ids").bindparams(bindparam('ids', expanding=True))
            prog = db.session.execute(t, {"ids": work_ids}).fetchall()
            for work_id, pdate, daily in prog:
                if pdate and (from_date_works is None or pdate >= from_date_works) and (to_date_works is None or pdate <= to_date_works):
                    progress_by_work.setdefault(work_id, 0.0)
                    progress_by_work[work_id] += float(daily or 0)
        by_building = {}
        for r in rows:
            wid, pid, bid, name, volume, unit, planned_date, pct_complete, sort_order, notes = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]
            executed = progress_by_work.get(wid, 0.0)
            vol = float(volume or 0)
            pct = round(executed / vol * 100.0, 1) if vol > 0 else None
            work_row = SimpleNamespace(
                id=wid, project_id=pid, building_id=bid, name=name, volume=vol, unit=unit,
                planned_completion_date=planned_date, percent_complete=pct_complete, sort_order=sort_order, notes=notes,
                initial_executed=0.0,
            )
            entry = {'work': work_row, 'executed': executed, 'volume': vol, 'percent': pct}
            by_building.setdefault(bid or 0, []).append(entry)
        for b in buildings:
            entries = by_building.get(b.id, [])
            works_by_building.append({'building': b, 'entries': entries})
        # В расчёт средних процентов и итогов не попадают работы без объёма (volume IS NULL или = 0)
        entries_with_volume = [
            e for entries in by_building.values() for e in entries
            if (e['volume'] is not None and e['volume'] > 0)
        ]
        total_vol = sum(e['volume'] for e in entries_with_volume)
        total_ex = sum(e['executed'] for e in entries_with_volume)
        works_summary_project['total_volume'] = total_vol
        works_summary_project['total_executed'] = total_ex
        pct_list = [e['percent'] for e in entries_with_volume if e.get('percent') is not None]
        project_avg_percent = round(sum(pct_list) / len(pct_list), 1) if pct_list else None
        works_summary_project['percent'] = project_avg_percent
        works_summary_project['project_avg_percent'] = project_avg_percent
        for b in buildings:
            entries = by_building.get(b.id, [])
            entries_vol = [e for e in entries if (e['volume'] is not None and e['volume'] > 0)]
            tv = sum(e['volume'] for e in entries_vol)
            te = sum(e['executed'] for e in entries_vol)
            pct_list_b = [e['percent'] for e in entries_vol if e.get('percent') is not None]
            building_avg_percent = round(sum(pct_list_b) / len(pct_list_b), 1) if pct_list_b else None
            works_summary_buildings.append({
                'building': b,
                'total_volume': tv,
                'total_executed': te,
                'percent': building_avg_percent,
                'building_avg_percent': building_avg_percent,
            })
    except Exception:
        db.session.rollback()
    return works_by_building, works_summary_project, works_summary_buildings


def _build_works_summary(project_id, buildings, graphs_building_id=None, graphs_works_from_str=None, graphs_works_to_str=None):
    """Построить works_by_building, works_summary_project, works_summary_buildings.
    Общий % по корпусу/объекту — среднее арифметическое процентов по всем работам (каждая работа даёт свой % = выполненное/объём×100)."""
    works_by_building = []
    works_summary_project = {'total_volume': 0.0, 'total_executed': 0.0, 'percent': None}
    works_summary_buildings = []
    try:
        works_query = Work.query.filter_by(project_id=project_id)
        if graphs_building_id:
            works_query = works_query.filter(Work.building_id == graphs_building_id)
        works_query = works_query.order_by(Work.sort_order.asc().nullslast(), Work.id)
        all_works = works_query.all()
        from_date_works = _parse_date_project(graphs_works_from_str) if graphs_works_from_str else None
        to_date_works = _parse_date_project(graphs_works_to_str) if graphs_works_to_str else None

        def _executed_for_work(work):
            base = float(getattr(work, 'initial_executed', None) or 0)
            daily_sum = 0.0
            for p in work.progress:
                if p.date and (from_date_works is None or p.date >= from_date_works) and (to_date_works is None or p.date <= to_date_works):
                    daily_sum += (p.daily_execution or 0)
            return base + daily_sum

        by_building = {}
        for w in all_works:
            executed = _executed_for_work(w)
            vol = w.volume or 0
            pct = round(executed / vol * 100.0, 1) if vol > 0 else None
            entry = {'work': w, 'executed': executed, 'volume': vol, 'percent': pct}
            bid = w.building_id or 0
            by_building.setdefault(bid, []).append(entry)
        for b in buildings:
            entries = by_building.get(b.id, [])
            works_by_building.append({'building': b, 'entries': entries})
        entries_with_volume = [e for entries in by_building.values() for e in entries if (e['volume'] or 0) > 0]
        total_vol = sum(e['volume'] for e in entries_with_volume)
        total_ex = sum(e['executed'] for e in entries_with_volume)
        works_summary_project['total_volume'] = total_vol
        works_summary_project['total_executed'] = total_ex
        # Общий % по объекту — среднее арифметическое процентов по всем работам (каждая работа участвует в расчёте)
        pct_list = [e['percent'] for e in entries_with_volume if e.get('percent') is not None]
        project_avg_percent = round(sum(pct_list) / len(pct_list), 1) if pct_list else None
        works_summary_project['percent'] = project_avg_percent
        for b in buildings:
            entries = by_building.get(b.id, [])
            entries_vol = [e for e in entries if (e['volume'] or 0) > 0]
            tv = sum(e['volume'] for e in entries_vol)
            te = sum(e['executed'] for e in entries_vol)
            # Общий % по корпусу — среднее арифметическое процентов по всем работам корпуса
            pct_list_b = [e['percent'] for e in entries_vol if e.get('percent') is not None]
            building_avg_percent = round(sum(pct_list_b) / len(pct_list_b), 1) if pct_list_b else None
            works_summary_buildings.append({
                'building': b,
                'total_volume': tv,
                'total_executed': te,
                'percent': building_avg_percent,
                'building_avg_percent': building_avg_percent,
            })
        works_summary_project['project_avg_percent'] = project_avg_percent
    except ProgrammingError:
        db.session.rollback()
        return _build_works_summary_fallback(project_id, buildings, graphs_building_id, graphs_works_from_str, graphs_works_to_str)
    return works_by_building, works_summary_project, works_summary_buildings


def _build_works_aggregated_by_name_fallback(project_id, graphs_works_from_str=None, graphs_works_to_str=None):
    """Запасной путь без колонки initial_executed для сводки по видам работ.
    Учитывает раздел работ (category) и, для инженерных систем, подраздел (system_subsection)."""
    result = []
    try:
        from_date_works = _parse_date_project(graphs_works_from_str) if graphs_works_from_str else None
        to_date_works = _parse_date_project(graphs_works_to_str) if graphs_works_to_str else None
        rows = db.session.execute(
            text("SELECT id, name, volume, unit, category, system_subsection FROM works WHERE project_id = :pid ORDER BY name, id"),
            {"pid": project_id}
        ).fetchall()
        work_ids = [r[0] for r in rows]
        progress_by_work = {}
        if work_ids:
            t = text("SELECT work_id, date, daily_execution FROM work_progress WHERE work_id IN :ids").bindparams(bindparam('ids', expanding=True))
            prog = db.session.execute(t, {"ids": work_ids}).fetchall()
            for work_id, pdate, daily in prog:
                if pdate and (from_date_works is None or pdate >= from_date_works) and (to_date_works is None or pdate <= to_date_works):
                    progress_by_work.setdefault(work_id, 0.0)
                    progress_by_work[work_id] += float(daily or 0)
        by_name = {}
        for r in rows:
            wid, name, volume, unit, category, system_subsection = r
            executed = progress_by_work.get(wid, 0.0)
            vol = float(volume or 0)
            name_key = (name or '').strip() or '—'
            category = (category or 'Общестроительные работы').strip()
            subsection = None
            if category == 'Инженерные системы':
                subsection = (system_subsection or 'Прочие системы').strip()
            key = (category, subsection, name_key)
            if key not in by_name:
                by_name[key] = {
                    'name': name_key,
                    'unit': unit or '—',
                    'category': category,
                    'system_subsection': subsection,
                    'total_volume': 0.0,
                    'total_executed': 0.0,
                }
            by_name[key]['total_volume'] += vol
            by_name[key]['total_executed'] += executed
        for (category, subsection, name_key), agg in sorted(
            by_name.items(), key=lambda x: (x[0][0] or '', x[0][1] or '', x[0][2] or '')
        ):
            vol = agg['total_volume']
            ex = agg['total_executed']
            pct = round(ex / vol * 100.0, 1) if vol and vol > 0 else None
            result.append({
                'name': agg['name'],
                'unit': agg['unit'],
                'category': category,
                'system_subsection': subsection,
                'total_volume': vol,
                'total_executed': ex,
                'percent': pct,
                'deviation': ex - vol,
            })
    except Exception:
        db.session.rollback()
    return result


def _build_works_aggregated_by_name(project_id, graphs_works_from_str=None, graphs_works_to_str=None):
    """Сводная по видам работ: группировка по разделу, названию и (для инженерных систем) подразделу.
    Суммы объёма и выполнения, % = выполнено/план."""
    result = []
    try:
        works_query = Work.query.filter_by(project_id=project_id).order_by(Work.name, Work.id)
        all_works = works_query.all()
        from_date_works = _parse_date_project(graphs_works_from_str) if graphs_works_from_str else None
        to_date_works = _parse_date_project(graphs_works_to_str) if graphs_works_to_str else None

        def _executed_for_work(work):
            base = float(getattr(work, 'initial_executed', None) or 0)
            daily_sum = 0.0
            for p in work.progress:
                if p.date and (from_date_works is None or p.date >= from_date_works) and (to_date_works is None or p.date <= to_date_works):
                    daily_sum += (p.daily_execution or 0)
            return base + daily_sum

        by_name = {}
        for w in all_works:
            executed = _executed_for_work(w)
            vol = w.volume or 0
            name_key = (w.name or '').strip() or '—'
            category = (w.category or 'Общестроительные работы').strip()
            subsection = None
            if category == 'Инженерные системы':
                subsection = (getattr(w, 'system_subsection_or_default', None) or getattr(w, 'system_subsection', None) or 'Прочие системы').strip()
            key = (category, subsection, name_key)
            if key not in by_name:
                by_name[key] = {
                    'name': name_key,
                    'unit': w.unit or '—',
                    'category': category,
                    'system_subsection': subsection,
                    'total_volume': 0.0,
                    'total_executed': 0.0,
                }
            by_name[key]['total_volume'] += vol
            by_name[key]['total_executed'] += executed

        for (category, subsection, name_key), agg in sorted(
            by_name.items(), key=lambda x: (x[0][0] or '', x[0][1] or '', x[0][2] or '')
        ):
            vol = agg['total_volume']
            ex = agg['total_executed']
            pct = round(ex / vol * 100.0, 1) if vol and vol > 0 else None
            result.append({
                'name': agg['name'],
                'unit': agg['unit'],
                'category': category,
                'system_subsection': agg.get('system_subsection'),
                'total_volume': vol,
                'total_executed': ex,
                'percent': pct,
                'deviation': ex - vol,
            })
    except ProgrammingError:
        db.session.rollback()
        return _build_works_aggregated_by_name_fallback(project_id, graphs_works_from_str, graphs_works_to_str)
    return result


@project_bp.route('/<int:project_id>/works_summary_json')
@login_required
def works_summary_json(project_id):
    """JSON: сводка по объёмам (works_summary_project, works_summary_buildings) для обновления блока после update_daily."""
    project = Project.query.get_or_404(project_id)
    buildings = Building.query.filter_by(project_id=project_id).order_by(Building.name).all()
    graphs_building_id = request.args.get('graphs_building_id', type=int)
    graphs_works_from_str = request.args.get('graphs_works_from')
    graphs_works_to_str = request.args.get('graphs_works_to')
    _, works_summary_project, works_summary_buildings = _build_works_summary(
        project_id, buildings, graphs_building_id, graphs_works_from_str, graphs_works_to_str
    )
    out_project = {
        'total_volume': works_summary_project['total_volume'],
        'total_executed': works_summary_project['total_executed'],
        'percent': works_summary_project['percent'],
    }
    out_buildings = [
        {
            'building_id': b['building'].id,
            'building_name': b['building'].name,
            'total_volume': b['total_volume'],
            'total_executed': b['total_executed'],
            'percent': b['percent'],
        }
        for b in works_summary_buildings
    ]
    return jsonify(works_summary_project=out_project, works_summary_buildings=out_buildings)


def _build_gantt_mermaid(plan_tasks):
    """Собрать диаграмму Mermaid Gantt из списка PlanTask. Секции по task_type, зависимости через after."""
    if not plan_tasks:
        return ''
    id_map = {t.id: 't%d' % t.id for t in plan_tasks}
    lines = ['gantt', '    title Общий план производства', '    dateFormat YYYY-MM-DD', '    axisFormat %d.%m']
    sections = {'Подготовка': [], 'Демонтаж': [], 'Монтаж': [], 'Прочее': []}
    for t in plan_tasks:
        st = (t.task_type if t.task_type in sections else 'Прочее')
        name_esc = (t.name or 'Задача %s' % t.id).replace('"', "'").replace('\n', ' ')
        if len(name_esc) > 60:
            name_esc = name_esc[:57] + '...'
        lines_here = []
        if t.start_date and t.end_date and t.end_date >= t.start_date:
            dur_days = (t.end_date - t.start_date).days + 1
            if t.dependency_id and t.dependency_id in id_map:
                lines_here.append('    "%s" :%s, after %s, %dd' % (name_esc, id_map[t.id], id_map[t.dependency_id], dur_days))
            else:
                lines_here.append('    "%s" :%s, %s, %dd' % (name_esc, id_map[t.id], t.start_date.isoformat(), dur_days))
        else:
            lines_here.append('    "%s" :%s, 2024-01-01, 1d' % (name_esc, id_map[t.id]))
        sections[st].extend(lines_here)
    for section_name in ('Подготовка', 'Демонтаж', 'Монтаж', 'Прочее'):
        if sections[section_name]:
            lines.append('    section %s' % section_name)
            lines.extend(sections[section_name])
    return '\n'.join(lines)


@project_bp.route('/<int:project_id>/works/<int:work_id>/progress')
@login_required
def work_progress_json(project_id, work_id):
    """JSON: ежедневное выполнение по работе (labels, data). Совместимость с Chart.js."""
    return _work_daily_json(project_id, work_id, keys=('labels', 'data'))


@project_bp.route('/<int:project_id>/works/<int:work_id>/daily_json')
@login_required
def work_daily_json(project_id, work_id):
    """JSON: ежедневное выполнение по работе для модалки. {dates: [...], executions: [...]}. Поддержка month/year или from_date/to_date."""
    return _work_daily_json(project_id, work_id, keys=('dates', 'executions'))


def _work_daily_json(project_id, work_id, keys=('dates', 'executions')):
    date_key, value_key = keys[0], keys[1]
    project = Project.query.get_or_404(project_id)
    try:
        work = Work.query.filter_by(id=work_id, project_id=project_id).first()
    except ProgrammingError:
        db.session.rollback()
        row = db.session.execute(
            text("SELECT id, name FROM works WHERE id = :id AND project_id = :pid"),
            {"id": work_id, "pid": project_id}
        ).fetchone()
        if not row:
            return jsonify({'error': 'Work not found'}), 404
        work = SimpleNamespace(id=row[0], name=row[1])
    if not work:
        return jsonify({'error': 'Work not found'}), 404
    from_str = request.args.get('from_date')
    to_str = request.args.get('to_date')
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    from_d = _parse_date_project(from_str) if from_str else None
    to_d = _parse_date_project(to_str) if to_str else None
    if month is not None and year is not None and 1 <= month <= 12:
        import calendar as cal
        _, last_day = cal.monthrange(year, month)
        from_d = from_d or date(year, month, 1)
        to_d = to_d or date(year, month, last_day)
    try:
        q = WorkProgress.query.filter_by(work_id=work_id).order_by(WorkProgress.date.asc())
        if from_d:
            q = q.filter(WorkProgress.date >= from_d)
        if to_d:
            q = q.filter(WorkProgress.date <= to_d)
        rows = q.all()
    except ProgrammingError as e:
        db.session.rollback()
        db_err = _extract_db_programming_error(e)
        msg = _format_db_programming_error(db_err)
        current_app.logger.error(f"DB error: {str(e)}")
        return jsonify({
            date_key: [],
            value_key: [],
            'work_name': work.name,
            'error': msg,
        })
    date_list = []
    value_list = []
    for r in rows:
        if r.date:
            date_list.append(r.date.strftime('%d.%m.%Y') if date_key == 'labels' else r.date.isoformat())
            value_list.append(float(r.daily_execution or 0))
    return jsonify({
        date_key: date_list,
        value_key: value_list,
        'work_name': work.name,
    })


@project_bp.route('/<int:project_id>/works/add', methods=['POST'])
@login_required
def add_work(project_id):
    """Добавить работу по корпусу (name, volume, unit, planned_date)."""
    project = Project.query.get_or_404(project_id)
    building_id = request.form.get('building_id', type=int)
    if not building_id:
        flash('Укажите корпус.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    building = Building.query.filter_by(id=building_id, project_id=project_id).first()
    if not building:
        flash('Корпус не найден.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Введите наименование работы.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    try:
        vol = float(request.form.get('volume') or 0)
        if vol <= 0:
            flash('Объём должен быть больше 0.', 'warning')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    except (ValueError, TypeError):
        flash('Некорректный объём.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    unit = (request.form.get('unit') or '').strip()
    planned_str = (request.form.get('planned_date') or '').strip()
    planned_date = _parse_date_project(planned_str) if planned_str else None
    category = (request.form.get('category') or '').strip()
    allowed_categories = (
        'Демонтажные работы',
        'Общестроительные работы',
        'Инженерные системы',
    )
    if category not in allowed_categories:
        category = work.category or 'Общестроительные работы'
    category = (request.form.get('category') or '').strip()
    allowed_categories = (
        'Демонтажные работы',
        'Общестроительные работы',
        'Инженерные системы',
    )
    if category not in allowed_categories:
        category = 'Общестроительные работы'
    initial_executed = None
    ie_raw = request.form.get('initial_executed')
    if ie_raw not in (None, ''):
        try:
            initial_executed = max(0.0, float(ie_raw))
        except (ValueError, TypeError):
            pass
    try:
        w = Work(
            project_id=project_id,
            building_id=building_id,
            name=name,
            volume=vol,
            unit=unit or None,
            planned_completion_date=planned_date,
            initial_executed=initial_executed,
            category=category,
        )
        db.session.add(w)
        db.session.commit()
        flash('Работа добавлена.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Ошибка сохранения: ' + str(e), 'danger')
    next_url = request.form.get('next', '').strip()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/works/<int:work_id>/edit', methods=['POST'])
@login_required
def edit_work(project_id, work_id):
    """Обновить работу (name, volume, unit, planned_date). % пересчитывается в представлениях."""
    project = Project.query.get_or_404(project_id)
    work = Work.query.filter_by(id=work_id, project_id=project_id).first()
    if not work:
        flash('Работа не найдена.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Введите наименование работы.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    try:
        vol = float(request.form.get('volume') or 0)
        if vol <= 0:
            flash('Объём должен быть больше 0.', 'warning')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    except (ValueError, TypeError):
        flash('Некорректный объём.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    unit = (request.form.get('unit') or '').strip()
    planned_str = (request.form.get('planned_date') or '').strip()
    planned_date = _parse_date_project(planned_str) if planned_str else None
    initial_executed = None
    ie_raw = request.form.get('initial_executed')
    if ie_raw not in (None, ''):
        try:
            initial_executed = max(0.0, float(ie_raw))
        except (ValueError, TypeError):
            pass
    try:
        work.name = name
        work.volume = vol
        work.unit = unit or None
        work.planned_completion_date = planned_date
        work.initial_executed = initial_executed
        work.category = category
        db.session.commit()
        flash('Работа обновлена.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Ошибка сохранения: ' + str(e), 'danger')
    next_url = request.form.get('next', '').strip()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/works/<int:work_id>/delete', methods=['POST'])
@login_required
def delete_work(project_id, work_id):
    """Удалить работу и все записи work_progress (каскад)."""
    project = Project.query.get_or_404(project_id)
    work = Work.query.filter_by(id=work_id, project_id=project_id).first()
    if not work:
        flash('Работа не найдена.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    try:
        WorkProgress.query.filter_by(work_id=work_id).delete()
        db.session.delete(work)
        db.session.commit()
        flash('Работа удалена.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Ошибка удаления.', 'danger')
    next_url = request.form.get('next', '').strip()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/works/export_excel')
@login_required
def works_export_excel(project_id):
    """Выгрузка работ и ежедневного выполнения в Excel (формат work1.xlsx)."""
    project = Project.query.get_or_404(project_id)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            tmp_path = f.name
        root = current_app.root_path
        if os.path.isdir(os.path.join(root, 'scripts')):
            script_path = os.path.join(root, 'scripts', 'export_works_to_excel.py')
        else:
            script_path = os.path.join(os.path.dirname(root), 'scripts', 'export_works_to_excel.py')
        if not os.path.isfile(script_path):
            flash('Скрипт экспорта не найден.', 'warning')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
        subprocess.run([sys.executable, script_path, '--project-id', str(project_id), '-o', tmp_path],
                      cwd=os.path.dirname(root), timeout=60, check=True)
        with open(tmp_path, 'rb') as fh:
            data = BytesIO(fh.read())
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        data.seek(0)
        return send_file(data, as_attachment=True, download_name=f'works_project_{project_id}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except subprocess.CalledProcessError:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        flash('Ошибка при формировании Excel.', 'danger')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        flash('Ошибка выгрузки: ' + str(e), 'danger')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/works/import_excel', methods=['POST'])
@login_required
def works_import_excel(project_id):
    """Загрузка работ из Excel (формат work1.xlsx)."""
    project = Project.query.get_or_404(project_id)
    if 'excel_file' not in request.files:
        flash('Выберите файл Excel.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    f = request.files['excel_file']
    if not f or not f.filename or not f.filename.lower().endswith(('.xlsx', '.xls')):
        flash('Нужен файл .xlsx или .xls.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    tmp_path = None
    clean_before_import = bool(request.form.get('clean_before_import'))
    try:
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            tmp.write(f.read())
            tmp_path = tmp.name
        root = current_app.root_path
        if os.path.isdir(os.path.join(root, 'scripts')):
            script_path = os.path.join(root, 'scripts', 'import_works_from_excel.py')
        else:
            script_path = os.path.join(os.path.dirname(root), 'scripts', 'import_works_from_excel.py')
        if not os.path.isfile(script_path):
            flash('Скрипт импорта не найден.', 'warning')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
        cmd = [sys.executable, script_path, tmp_path, '--project-id', str(project_id)]
        if clean_before_import:
            cmd.append('--clean')
        subprocess.run(cmd, cwd=os.path.dirname(root), timeout=120, check=True)
        flash('Импорт выполнен. Данные загружены из Excel.', 'success')
    except subprocess.CalledProcessError:
        flash('Ошибка при импорте (проверьте формат файла и наличие корпусов).', 'danger')
    except Exception as e:
        flash('Ошибка загрузки: ' + str(e), 'danger')
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except (OSError, NameError):
                pass
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/works/<int:work_id>/update_daily', methods=['POST'])
@login_required
def update_daily(project_id, work_id):
    """Установить/обновить объём выполнения за день (date=YYYY-MM-DD, value=число). JSON или form."""
    wants_json = request.is_json or (request.get_json(silent=True) is not None) or (request.headers.get('X-Requested-With') == 'XMLHttpRequest')
    project = Project.query.get_or_404(project_id)
    try:
        work = Work.query.filter_by(id=work_id, project_id=project_id).first()
    except ProgrammingError:
        db.session.rollback()
        row = db.session.execute(
            text("SELECT id, project_id, building_id, name, volume FROM works WHERE id = :id AND project_id = :pid"),
            {"id": work_id, "pid": project_id}
        ).fetchone()
        if not row:
            if wants_json:
                return jsonify({'error': 'Работа не найдена'}), 404
            flash('Работа не найдена.', 'warning')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
        work = SimpleNamespace(id=row[0], project_id=row[1], building_id=row[2], name=row[3], volume=row[4], initial_executed=0.0)
    if not work:
        if wants_json:
            return jsonify({'error': 'Работа не найдена'}), 404
        flash('Работа не найдена.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    date_str = request.form.get('date') or (request.get_json(silent=True) or {}).get('date')
    value_raw = request.form.get('value') or (request.get_json(silent=True) or {}).get('value')
    d = _parse_date_project(date_str) if date_str else None
    if not d:
        if wants_json:
            return jsonify({'error': 'Некорректная дата'}), 400
        flash('Некорректная дата.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    try:
        val = float(value_raw) if value_raw not in (None, '') else 0.0
    except (ValueError, TypeError):
        val = 0.0
    if val < 0:
        if wants_json:
            return jsonify({'ok': False, 'error': 'Значение не может быть отрицательным'}), 400
        flash('Значение не может быть отрицательным.', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    val = round(val, 2)
    try:
        progress = WorkProgress.query.filter_by(work_id=work_id, date=d).first()
        if progress:
            progress.daily_execution = val
        else:
            progress = WorkProgress(work_id=work_id, date=d, daily_execution=val)
            db.session.add(progress)
        db.session.commit()
        if wants_json:
            base = float(getattr(work, 'initial_executed', None) or 0)
            if hasattr(work, 'progress'):
                daily_sum = sum(float(p.daily_execution or 0) for p in work.progress)
            else:
                daily_sum = db.session.execute(
                    text("SELECT COALESCE(SUM(daily_execution), 0) FROM work_progress WHERE work_id = :wid"),
                    {"wid": work_id}
                ).scalar() or 0
            new_total = base + float(daily_sum)
            vol = getattr(work, 'volume', None) or 0
            new_pct = round(new_total / vol * 100.0, 1) if vol and float(vol) > 0 else None
            return jsonify({
                'ok': True,
                'date': d.isoformat(),
                'value': val,
                'executed': round(new_total, 2),
                'percent': new_pct,
                'building_id': getattr(work, 'building_id', None),
            })
        flash('Значение за день сохранено.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB error: {str(e)}")
        if wants_json:
            db_err = _extract_db_programming_error(e)
            err_msg = _format_db_programming_error(db_err)
            return jsonify({'error': err_msg}), 500
        flash('Ошибка сохранения: ' + _format_db_programming_error(_extract_db_programming_error(e)), 'danger')
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


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


@project_bp.route('/<int:project_id>/workforce/add', methods=['POST'])
@login_required
def add_workforce(project_id):
    project = Project.query.get_or_404(project_id)
    date = _parse_date_project(request.form.get('date'))
    contractor_name = (request.form.get('contractor_name') or '').strip() or None
    workers_count = request.form.get('workers_count', type=int)
    if workers_count is not None and workers_count < 0:
        workers_count = None
    shift_hours_raw = request.form.get('shift_hours')
    shift_hours = None
    if shift_hours_raw not in (None, ''):
        try:
            shift_hours = float(shift_hours_raw)
            if shift_hours < 0:
                shift_hours = None
        except (ValueError, TypeError):
            pass
    notes = (request.form.get('notes') or '').strip() or None
    record = DailyWorkforce(
        project_id=project_id,
        date=date,
        contractor_name=contractor_name,
        workers_count=workers_count,
        shift_hours=shift_hours,
        notes=notes
    )
    db.session.add(record)
    try:
        db.session.commit()
        flash('Запись о людях успешно добавлена', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Таблица daily_workforce не найдена в БД. Структура БД устарела. Запустите миграции: flask db upgrade.', 'warning')
    cal_month = request.form.get('calendar_month', type=int)
    cal_year = request.form.get('calendar_year', type=int)
    q = {'calendar_month': cal_month, 'calendar_year': cal_year} if cal_month and cal_year else {}
    return redirect(url_for('project.dashboard', project_id=project_id, **q) + '#project-people')


@project_bp.route('/<int:project_id>/workforce/<int:record_id>/edit', methods=['POST'])
@login_required
def edit_workforce(project_id, record_id):
    project = Project.query.get_or_404(project_id)
    record = DailyWorkforce.query.filter_by(id=record_id, project_id=project_id).first_or_404()
    record.contractor_name = (request.form.get('contractor_name') or '').strip() or None
    workers_count = request.form.get('workers_count', type=int)
    record.workers_count = workers_count if workers_count is not None and workers_count >= 0 else record.workers_count
    shift_hours_raw = request.form.get('shift_hours')
    if shift_hours_raw not in (None, ''):
        try:
            record.shift_hours = float(shift_hours_raw)
            if record.shift_hours < 0:
                record.shift_hours = None
        except (ValueError, TypeError):
            pass
    else:
        record.shift_hours = None
    record.notes = (request.form.get('notes') or '').strip() or None
    try:
        db.session.commit()
        flash('Запись изменена', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Ошибка сохранения', 'warning')
    cal_month = request.form.get('calendar_month', type=int)
    cal_year = request.form.get('calendar_year', type=int)
    q = {'calendar_month': cal_month, 'calendar_year': cal_year} if cal_month and cal_year else {}
    return redirect(url_for('project.dashboard', project_id=project_id, **q) + '#project-people')


@project_bp.route('/<int:project_id>/workforce/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_workforce(project_id, record_id):
    project = Project.query.get_or_404(project_id)
    record = DailyWorkforce.query.filter_by(id=record_id, project_id=project_id).first_or_404()
    try:
        db.session.delete(record)
        db.session.commit()
        flash('Запись удалена', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Ошибка удаления', 'warning')
    ref = request.referrer or ''
    return redirect(ref if ref else url_for('project.dashboard', project_id=project_id) + '#project-people')


@project_bp.route('/<int:project_id>/workforce/day/<date_str>')
@login_required
def workforce_day(project_id, date_str):
    """GET: JSON { records: [...], performers: [{ name, organization }] } для модалки дня."""
    project = Project.query.get_or_404(project_id)
    day_date = _parse_date_project(date_str)
    if not day_date:
        return jsonify({'error': 'Неверная дата'}), 400
    try:
        records = DailyWorkforce.query.filter_by(project_id=project_id, date=day_date).all()
        performers = WorkPerformer.query.filter_by(project_id=project_id).order_by(WorkPerformer.name).all()
    except Exception:
        db.session.rollback()
        return jsonify({'records': [], 'performers': []})
    out_records = [
        {
            'id': r.id,
            'contractor_name': r.contractor_name or '',
            'workers_count': r.workers_count if r.workers_count is not None else 0,
            'workers_count_night': int(getattr(r, 'workers_count_night', 0) or 0),
            'shift_hours': float(r.shift_hours) if r.shift_hours is not None else 0.0,
            'shift_hours_night': float(r.shift_hours_night) if getattr(r, 'shift_hours_night', None) is not None else 0.0,
            'notes': r.notes or ''
        }
        for r in records
    ]
    out_performers = [
        {'name': p.name or '', 'organization': p.company or ''}
        for p in performers
    ]
    return jsonify({'records': out_records, 'performers': out_performers})


@project_bp.route('/<int:project_id>/workforce/day/save', methods=['POST'])
@login_required
def workforce_day_save(project_id):
    """POST: JSON { date, records: [ { contractor_name, workers_count, shift_hours, shift_hours_night, notes } ] }. День и ночь макс. 12 ч каждый, всего 24 ч в сутки."""
    project = Project.query.get_or_404(project_id)
    data = request.get_json(silent=True) or {}
    date_str = data.get('date') or request.form.get('date')
    day_date = _parse_date_project(date_str)
    if not day_date:
        flash('Не указана или неверная дата', 'warning')
        return redirect(url_for('project.dashboard', project_id=project_id) + '#project-people')
    records_data = data.get('records', [])
    try:
        DailyWorkforce.query.filter_by(project_id=project_id, date=day_date).delete()
        for rec in records_data:
            contractor_name = (rec.get('contractor_name') or '').strip()
            if not contractor_name:
                continue
            workers_count = rec.get('workers_count')
            if workers_count is not None and (not isinstance(workers_count, int) or workers_count < 0):
                workers_count = 0
            elif workers_count is None:
                workers_count = 0
            workers_count_night = rec.get('workers_count_night')
            if workers_count_night is not None and (not isinstance(workers_count_night, int) or workers_count_night < 0):
                workers_count_night = 0
            elif workers_count_night is None:
                workers_count_night = 0
            shift_hours = rec.get('shift_hours')
            if shift_hours is not None:
                try:
                    shift_hours = min(12.0, max(0.0, float(shift_hours)))
                except (TypeError, ValueError):
                    shift_hours = 0.0
            else:
                shift_hours = 0.0
            shift_hours_night = rec.get('shift_hours_night')
            if shift_hours_night is not None:
                try:
                    shift_hours_night = min(12.0, max(0.0, float(shift_hours_night)))
                except (TypeError, ValueError):
                    shift_hours_night = 0.0
            else:
                shift_hours_night = 0.0
            if shift_hours + shift_hours_night > 24:
                shift_hours_night = 24.0 - shift_hours
            notes = (rec.get('notes') or '').strip() or None
            row = DailyWorkforce(
                project_id=project_id,
                date=day_date,
                contractor_name=contractor_name,
                workers_count=workers_count,
                workers_count_night=workers_count_night,
                shift_hours=shift_hours,
                shift_hours_night=shift_hours_night,
                notes=notes
            )
            db.session.add(row)
        db.session.commit()
        flash('Данные за день сохранены', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Ошибка сохранения. Проверьте наличие таблицы daily_workforce в БД.', 'warning')
    calendar_month = request.args.get('month') or data.get('month') or request.form.get('calendar_month', type=int)
    calendar_year = request.args.get('year') or data.get('year') or request.form.get('calendar_year', type=int)
    today = date.today()
    if not calendar_month or not calendar_year:
        calendar_month, calendar_year = today.month, today.year
    q = {'calendar_month': calendar_month, 'calendar_year': calendar_year}
    return redirect(url_for('project.dashboard', project_id=project_id, **q) + '#project-people')


@project_bp.route('/<int:project_id>/performers/add', methods=['POST'])
@login_required
def add_performer(project_id):
    project = Project.query.get_or_404(project_id)
    name = (request.form.get('name') or '').strip() or None
    company = (request.form.get('company') or '').strip() or None
    notes = (request.form.get('notes') or '').strip() or None
    try:
        performer = WorkPerformer(project_id=project_id, name=name, company=company, notes=notes)
        db.session.add(performer)
        db.session.commit()
        flash('Исполнитель добавлен в справочник', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Таблица work_perформers не найдена. Структура БД устарела. Запустите миграции: flask db upgrade.', 'warning')
    cal_month = request.form.get('calendar_month', type=int)
    cal_year = request.form.get('calendar_year', type=int)
    q = {'calendar_month': cal_month, 'calendar_year': cal_year} if (cal_month and cal_year) else {}
    return redirect(url_for('project.dashboard', project_id=project_id, **q) + '#project-people')


@project_bp.route('/<int:project_id>/performers/<int:performer_id>/delete', methods=['POST'])
@login_required
def delete_performer(project_id, performer_id):
    project = Project.query.get_or_404(project_id)
    performer = WorkPerformer.query.filter_by(id=performer_id, project_id=project_id).first_or_404()
    try:
        db.session.delete(performer)
        db.session.commit()
        flash('Исполнитель удалён из справочника', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Ошибка при удалении', 'warning')
    cal_month = request.form.get('calendar_month', type=int)
    cal_year = request.form.get('calendar_year', type=int)
    q = {'calendar_month': cal_month, 'calendar_year': cal_year} if (cal_month and cal_year) else {}
    return redirect(url_for('project.dashboard', project_id=project_id, **q) + '#project-people')


@project_bp.route('/<int:project_id>/schedules/add', methods=['POST'])
@login_required
def add_schedule_work(project_id):
    """Добавить работу в график на уровне объекта (с опциональной привязкой к корпусу и этажу)."""
    project = Project.query.get_or_404(project_id)
    name = (request.form.get('name') or '').strip() or None
    planned_start = _parse_date_project(request.form.get('planned_start'))
    planned_end = _parse_date_project(request.form.get('planned_end'))
    fact_start = _parse_date_project(request.form.get('fact_start'))
    fact_end = _parse_date_project(request.form.get('fact_end'))
    percent_raw = request.form.get('percent_complete')
    percent_complete = None
    if percent_raw not in (None, ''):
        try:
            percent_complete = float(percent_raw)
            if percent_complete < 0 or percent_complete > 100:
                percent_complete = None
        except (ValueError, TypeError):
            percent_complete = None
    status = (request.form.get('status') or '').strip() or None
    notes = (request.form.get('notes') or '').strip() or None

    building_id = request.form.get('building_id', type=int)
    floor_id = request.form.get('floor_id', type=int)

    building = None
    floor = None
    if building_id:
        building = Building.query.get_or_404(building_id)
        if building.project_id != project_id:
            flash('Выбранный корпус не принадлежит объекту', 'danger')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')
    if floor_id:
        floor = Floor.query.get_or_404(floor_id)
        if floor.building.project_id != project_id or (building and floor.building_id != building.id):
            flash('Выбранный этаж не принадлежит объекту/корпусу', 'danger')
            return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')

    work = ScheduleWork(
        project_id=project_id,
        building_id=building.id if building else None,
        floor_id=floor.id if floor else None,
        name=name,
        planned_start=planned_start,
        planned_end=planned_end,
        fact_start=fact_start,
        fact_end=fact_end,
        percent_complete=percent_complete,
        status=status,
        notes=notes
    )
    db.session.add(work)
    try:
        db.session.commit()
        flash('Работа успешно добавлена в график объекта', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash(
            'Ошибка БД при сохранении графика: в таблице schedule_works отсутствуют нужные столбцы. '
            'Структура БД устарела. Запустите миграции: flask db upgrade.',
            'danger'
        )
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


# ----- Общий план производства (ГПП) — Gantt -----

@project_bp.route('/<int:project_id>/plan/add_task', methods=['POST'])
@login_required
def add_plan_task(project_id):
    """Добавить задачу в общий план производства (ГПП)."""
    project = Project.query.get_or_404(project_id)
    name = (request.form.get('name') or '').strip() or None
    start_date = _parse_date_project(request.form.get('start_date'))
    end_date = _parse_date_project(request.form.get('end_date'))
    task_type = (request.form.get('task_type') or '').strip() or None
    if task_type and task_type not in ('Подготовка', 'Демонтаж', 'Монтаж'):
        task_type = None
    dependency_id = request.form.get('dependency_id', type=int) or None
    building_id = request.form.get('building_id', type=int) or None
    floor_id = request.form.get('floor_id', type=int) or None
    notes = (request.form.get('notes') or '').strip() or None

    if dependency_id:
        dep = PlanTask.query.filter_by(id=dependency_id, project_id=project_id).first()
        if not dep:
            dependency_id = None

    if building_id:
        b = Building.query.get(building_id)
        if not b or b.project_id != project_id:
            building_id = None
    if floor_id:
        f = Floor.query.get(floor_id)
        if not f or f.building.project_id != project_id:
            floor_id = None

    task = PlanTask(
        project_id=project_id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        task_type=task_type,
        dependency_id=dependency_id,
        building_id=building_id,
        floor_id=floor_id,
        notes=notes
    )
    db.session.add(task)
    try:
        db.session.commit()
        flash('Задача добавлена в план производства', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash(
            'Ошибка БД: таблица plan_tasks не найдена. Структура БД устарела. Запустите миграции: flask db upgrade.',
            'danger'
        )
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/plan/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_plan_task(project_id, task_id):
    """Редактировать задачу ГПП."""
    project = Project.query.get_or_404(project_id)
    task = PlanTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()
    name = (request.form.get('name') or '').strip() or None
    start_date = _parse_date_project(request.form.get('start_date'))
    end_date = _parse_date_project(request.form.get('end_date'))
    task_type = (request.form.get('task_type') or '').strip() or None
    if task_type and task_type not in ('Подготовка', 'Демонтаж', 'Монтаж'):
        task_type = None
    dependency_id = request.form.get('dependency_id', type=int) or None
    if dependency_id == task.id:
        dependency_id = None
    if dependency_id:
        dep = PlanTask.query.filter_by(id=dependency_id, project_id=project_id).first()
        if not dep:
            dependency_id = None
    building_id = request.form.get('building_id', type=int) or None
    floor_id = request.form.get('floor_id', type=int) or None
    if building_id:
        b = Building.query.get(building_id)
        if not b or b.project_id != project_id:
            building_id = None
    if floor_id:
        f = Floor.query.get(floor_id)
        if not f or f.building.project_id != project_id:
            floor_id = None
    notes = (request.form.get('notes') or '').strip() or None

    task.name = name
    task.start_date = start_date
    task.end_date = end_date
    task.task_type = task_type
    task.dependency_id = dependency_id
    task.building_id = building_id
    task.floor_id = floor_id
    task.notes = notes
    try:
        db.session.commit()
        flash('Задача обновлена', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Ошибка БД при обновлении задачи', 'danger')
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/<int:project_id>/plan/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_plan_task(project_id, task_id):
    """Удалить задачу ГПП."""
    project = Project.query.get_or_404(project_id)
    task = PlanTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()
    db.session.delete(task)
    try:
        db.session.commit()
        flash('Задача удалена из плана', 'success')
    except ProgrammingError:
        db.session.rollback()
        flash('Ошибка БД при удалении задачи', 'danger')
    return redirect(url_for('project.dashboard', project_id=project_id) + '#project-graphs')


@project_bp.route('/floor/<int:floor_id>/upload_plan', methods=['POST'])
@login_required
def upload_floor_plan(floor_id):
    floor = Floor.query.get_or_404(floor_id)
    file = request.files.get('plan_file')
    doc_type_id = request.form.get('doc_type_id', type=int)
    page_number = request.form.get('page_number', type=int) or 1

    if not file or not doc_type_id:
        flash('Выберите файл и тип плана', 'danger')
        return redirect(url_for('floors.view_floor', floor_id=floor.id))

    doc_type = DocType.query.get_or_404(doc_type_id)
    filename = secure_filename(file.filename)
    plan_dir = os.path.join(current_app.root_path, 'static', 'media', 'plans', str(floor.id))
    os.makedirs(plan_dir, exist_ok=True)
    filepath = os.path.join(plan_dir, filename)
    file.save(filepath)

    image_filename = filename
    if filename.lower().endswith('.pdf'):
        try:
            pdf = fitz.open(filepath)
            if page_number < 1 or page_number > pdf.page_count:
                flash(f'Номер страницы вне диапазона (1-{pdf.page_count})', 'danger')
                return redirect(url_for('floors.view_floor', floor_id=floor.id))
            page = pdf.load_page(page_number - 1)
            pix = page.get_pixmap(dpi=150)
            image_filename = f"{os.path.splitext(filename)[0]}_page_{page_number}.png"
            image_path = os.path.join(plan_dir, image_filename)
            pix.save(image_path)
            pdf.close()
        except Exception as e:
            flash(f'Ошибка обработки PDF: {e}', 'danger')
            return redirect(url_for('floors.view_floor', floor_id=floor.id))

    rel_image_path = os.path.join('media', 'plans', str(floor.id), image_filename).replace('\\', '/')

    plan = Plan(
        floor_id=floor_id,
        name=image_filename,
        image_path=rel_image_path,
        uploaded_at=datetime.utcnow()
    )
    db.session.add(plan)
    db.session.commit()
    flash('План этажа загружен', 'success')
    return redirect(url_for('floors.view_floor', floor_id=floor.id))


@project_bp.route('/<int:project_id>/create_building', methods=['GET', 'POST'])
@login_required
def create_building(project_id):
    project = Project.query.get_or_404(project_id)
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            building = Building(name=name, project_id=project_id)
            db.session.add(building)
            db.session.commit()
            flash('Корпус создан', 'success')
            return redirect(url_for('project.dashboard', project_id=project_id))
        flash('Название обязательно', 'danger')
    return render_template('project/create_building.html', project=project)  # Шаблон для формы


@project_bp.route('/<int:project_id>/upload_documents', methods=['POST'])
@login_required
def upload_documents(project_id):
    project = Project.query.get_or_404(project_id)

    files = request.files.getlist('files')
    building_id = request.form.get('building_id', type=int) or None
    floor_id = request.form.get('floor_id', type=int) or None
    work_type_ids = request.form.getlist('work_type_ids', type=int)
    title = request.form.get('title', '').strip() or None
    description = request.form.get('description', '').strip() or None
    extra_tag_names = _parse_tags_raw(request.form.get('tags'))
    extra_type_ids = _ensure_doc_types_by_names(extra_tag_names) if extra_tag_names else []
    all_type_ids = sorted(set(work_type_ids or []) | set(extra_type_ids))

    if not files or all(f.filename == '' for f in files):
        flash('Выберите хотя бы один файл', 'danger')
        return redirect(url_for('project.dashboard', project_id=project_id))

    if building_id:
        building = Building.query.get_or_404(building_id)
        if building.project_id != project_id:
            flash('Корпус не принадлежит объекту', 'danger')
            return redirect(url_for('project.dashboard', project_id=project_id))
    if floor_id:
        floor = Floor.query.get_or_404(floor_id)
        if floor.building.project_id != project_id or (building_id and floor.building_id != building_id):
            flash('Этаж не принадлежит выбранному объекту/корпусу', 'danger')
            return redirect(url_for('project.dashboard', project_id=project_id))

    base_dir = os.path.join(current_app.root_path, 'static', 'media', 'projects', str(project_id))
    sub_dir = ''
    if building_id:
        sub_dir = f'building_{building_id}'
        if floor_id:
            sub_dir = os.path.join(sub_dir, f'floor_{floor_id}')
    upload_dir = os.path.join(base_dir, sub_dir)
    os.makedirs(upload_dir, exist_ok=True)

    uploaded_count = 0
    for file in files:
        if file.filename == '':
            continue

        original_filename = file.filename
        secure_fs_filename = secure_filename(file.filename)
        unique_fs_filename = f"{uuid.uuid4()}_{secure_fs_filename}"
        file_path = os.path.join(upload_dir, unique_fs_filename)
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
                thumb_filename = f"thumb_{unique_fs_filename}"
                thumb_path = os.path.join(upload_dir, thumb_filename)
                img.save(thumb_path)
                thumbnail_path = thumb_path
            except Exception as e:
                flash(f'Ошибка создания миниатюры: {e}', 'warning')

        rel_stored = os.path.join('media', 'projects', str(project_id), sub_dir, unique_fs_filename).replace('\\', '/')
        rel_thumbnail = thumbnail_path and os.path.join('media', 'projects', str(project_id), sub_dir, thumb_filename).replace('\\', '/') or None

        document = Document(
            project_id=project_id,
            building_id=building_id,
            floor_id=floor_id,
            title=title,
            description=description,
            filename=original_filename,
            stored_path=rel_stored,
            thumbnail_path=rel_thumbnail,
            file_size=os.path.getsize(file_path),
            uploaded_at=datetime.utcnow(),
            file_modified_at=file_modified_at,
            width_px=width_px,
            height_px=height_px,
            is_document_image=True if request.form.get('is_document_image') else False
        )

        db.session.add(document)
        db.session.flush()

        if all_type_ids:
            for wt_id in all_type_ids:
                db.session.execute(document_work_types.insert().values(
                    document_id=document.id,
                    doc_type_id=wt_id
                ))

        uploaded_count += 1

    db.session.commit()
    flash(f'Загружено {uploaded_count} файлов', 'success')

    # Редирект с параметром building_id (если был выбран), чтобы сразу увидеть файлы в соответствующем фильтре
    redirect_params = {}
    if building_id:
        redirect_params['building_id'] = building_id
    if floor_id:
        redirect_params['floor_id'] = floor_id
    return redirect(url_for('project.dashboard', project_id=project_id, **redirect_params))


@project_bp.route('/delete_document/<int:doc_id>', methods=['POST'])
@login_required
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    project_id = doc.project_id
    if not project_id:
        flash('Ошибка: документ не привязан к проекту', 'danger')
        return redirect(url_for('main.index'))
    db.session.delete(doc)
    db.session.commit()
    flash(f'Документ "{doc.filename}" удалён из базы (файл на диске сохранён)', 'info')
    return redirect(url_for('project.dashboard', project_id=project_id))


@project_bp.route('/document/<int:doc_id>/view')
@login_required
def view_document(doc_id):
    """Просмотр/скачивание документа на уровне проекта (поддерживает проектные, корпусные и этажные файлы)."""
    doc = Document.query.get_or_404(doc_id)

    # Определяем проект для документа (прямо или через корпус/этаж)
    project_id = doc.project_id
    if not project_id and doc.building_id:
        building = Building.query.get(doc.building_id)
        project_id = building.project_id if building else None
    if not project_id and doc.floor_id:
        floor = Floor.query.get(doc.floor_id)
        project_id = floor.building.project_id if floor and floor.building else None

    if not project_id:
        flash('Документ не привязан к объекту, просмотр невозможен', 'danger')
        return redirect(url_for('main.index'))

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


@project_bp.route('/document/<int:doc_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_document(doc_id):
    """Редактирование документа (название, описание, теги, корпус/этаж, статус скана) на любом уровне."""
    doc = Document.query.get_or_404(doc_id)

    # Определяем проект/корпус/этаж для контекста и редиректа
    project = None
    building = None
    floor = None

    if doc.project_id:
        project = Project.query.get(doc.project_id)
    if doc.building_id:
        building = Building.query.get(doc.building_id)
        if building and not project:
            project = building.project
    if doc.floor_id:
        floor = Floor.query.get(doc.floor_id)
        if floor and not building:
            building = floor.building
        if floor and not project:
            project = floor.building.project

    if not project:
        flash('Документ не привязан к объекту, редактирование невозможно', 'danger')
        return redirect(url_for('main.index'))

    all_doc_types = DocType.query.order_by(DocType.sort_order).all()
    current_types = [wt.id for wt in doc.work_types]

    # Списки корпусов и этажей для выбора
    buildings = Building.query.filter_by(project_id=project.id).order_by(Building.name).all()
    project_floors = Floor.query.join(Building).filter(Building.project_id == project.id).order_by(Building.name, Floor.name).all()

    if request.method == 'POST':
        doc.title = (request.form.get('title') or '').strip() or None
        doc.description = (request.form.get('description') or '').strip() or None

        # Виды работ / теги: чекбоксы + свободный ввод
        new_type_ids = [int(x) for x in request.form.getlist('work_type_ids') if x.isdigit()]
        extra_tag_names = _parse_tags_raw(request.form.get('tags'))
        extra_type_ids = _ensure_doc_types_by_names(extra_tag_names) if extra_tag_names else []
        all_type_ids = sorted(set(new_type_ids or []) | set(extra_type_ids))
        if all_type_ids:
            doc.work_types = DocType.query.filter(DocType.id.in_(all_type_ids)).all()
        else:
            doc.work_types = []

        # Признак «скан документа»
        doc.is_document_image = True if request.form.get('is_document_image') else False

        # Привязка к корпусу и этажу (в пределах проекта)
        building_id = request.form.get('building_id', type=int)
        floor_id = request.form.get('floor_id', type=int)

        new_building = None
        new_floor = None
        if building_id:
            new_building = Building.query.get_or_404(building_id)
            if new_building.project_id != project.id:
                flash('Выбранный корпус не принадлежит текущему объекту', 'danger')
                return redirect(url_for('project.edit_document', doc_id=doc.id))
        if floor_id:
            new_floor = Floor.query.get_or_404(floor_id)
            if new_floor.building.project_id != project.id:
                flash('Выбранный этаж не принадлежит текущему объекту', 'danger')
                return redirect(url_for('project.edit_document', doc_id=doc.id))
            # Если корпус не выбран или выбран другой, берём корпус этажа
            new_building = new_floor.building

        # Если этаж не выбран, но корпус выбран — просто сбрасываем floor_id
        if not floor_id and new_building:
            new_floor = None

        # Если документ был привязан к маркеру, а этаж изменился или стал пустым — отвязываем маркер (и, при необходимости, удаляем его)
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

        doc.building_id = new_building.id if new_building else None
        doc.floor_id = new_floor.id if new_floor else None

        db.session.commit()
        flash('Документ обновлён', 'success')

        # Возврат туда, откуда пришли (если есть), иначе на вкладку документов проекта
        ref = request.referrer or ''
        if ref and '/buildings/' in ref:
            return redirect(ref.split('#')[0] + '#docs')
        if ref and '/floor/' in ref:
            return redirect(ref.split('#')[0] + '#docs')
        return redirect(url_for('project.dashboard', project_id=project.id) + '#docs')

    back_url = request.referrer or url_for('project.dashboard', project_id=project.id) + '#docs'
    return render_template(
        'project/edit_document.html',
        doc=doc,
        project=project,
        building=building,
        floor=floor,
        all_doc_types=all_doc_types,
        current_types=current_types,
        buildings=buildings,
        project_floors=project_floors,
        back_url=back_url
    )