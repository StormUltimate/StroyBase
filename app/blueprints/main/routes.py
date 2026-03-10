# app/blueprints/main/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError
from app.models import (
    Project, DailyWorkforce, Building, Floor, Document, MaterialMovement, MovementDocument,
    ScheduleWork, WorkPerformer, Work, WorkProgress,
)
from app.forms import ProjectForm
from app.extensions import db
import os
import shutil
import calendar
from datetime import date

main_bp = Blueprint('main', __name__, template_folder='templates/main')


@main_bp.route('/dashboards')
@login_required
def dashboards():
    """Сводные дашборды: по людям (сейчас), по графикам плановых/фактических работ — в перспективе."""
    projects = Project.query.order_by(Project.name).all()
    people_stats = {}
    try:
        expr_hours = func.coalesce(DailyWorkforce.shift_hours, 0) + func.coalesce(DailyWorkforce.shift_hours_night, 0)
        rows = db.session.query(
            DailyWorkforce.project_id,
            func.coalesce(func.sum(DailyWorkforce.workers_count), 0).label('total_workers'),
            func.coalesce(func.sum(expr_hours), 0).label('total_hours'),
        ).filter(DailyWorkforce.project_id.isnot(None)).group_by(DailyWorkforce.project_id).all()
        for r in rows:
            people_stats[r.project_id] = {'total_workers': int(r.total_workers or 0), 'total_hours': float(r.total_hours or 0)}
    except Exception:
        db.session.rollback()
        try:
            rows = db.session.query(
                DailyWorkforce.project_id,
                func.coalesce(func.sum(DailyWorkforce.workers_count), 0).label('total_workers'),
                func.coalesce(func.sum(DailyWorkforce.shift_hours), 0).label('total_hours'),
            ).filter(DailyWorkforce.project_id.isnot(None)).group_by(DailyWorkforce.project_id).all()
            for r in rows:
                people_stats[r.project_id] = {'total_workers': int(r.total_workers or 0), 'total_hours': float(r.total_hours or 0)}
        except Exception:
            db.session.rollback()

    # Оценка выполнения плана работ по объектам (средний % по работам проекта, как на дашборде проекта)
    project_planning = {}
    try:
        # Загружаем все работы одним запросом и группируем по проекту
        all_works = Work.query.filter(Work.project_id.isnot(None)).all()
        work_ids = [w.id for w in all_works]
        progress_by_work = {}
        if work_ids:
            rows = (
                db.session.query(
                    WorkProgress.work_id,
                    func.coalesce(func.sum(WorkProgress.daily_execution), 0).label('sum_exec'),
                )
                .filter(WorkProgress.work_id.in_(work_ids))
                .group_by(WorkProgress.work_id)
                .all()
            )
            for r in rows:
                progress_by_work[r.work_id] = float(r.sum_exec or 0.0)

        by_project = {}
        for w in all_works:
            vol = float(w.volume or 0.0)
            if vol <= 0:
                continue
            base = float(getattr(w, 'initial_executed', None) or 0.0)
            daily_sum = progress_by_work.get(w.id, 0.0)
            executed = base + daily_sum
            pct = executed / vol * 100.0 if vol > 0 else None
            if pct is None:
                continue
            pid = w.project_id
            if pid not in by_project:
                by_project[pid] = []
            by_project[pid].append(pct)

        for pid, pcts in by_project.items():
            if not pcts:
                continue
            avg_pct = sum(pcts) / len(pcts)
            project_planning[pid] = round(avg_pct, 1)
    except ProgrammingError:
        db.session.rollback()
        project_planning = {}

    # График людей за месяц для одного выбранного объекта (столбики по дням)
    today = date.today()
    chart_project_id = request.args.get('chart_project_id', type=int)
    if not chart_project_id and projects:
        chart_project_id = projects[0].id
    chart_year = request.args.get('chart_year', type=int) or today.year
    chart_month = request.args.get('chart_month', type=int) or today.month
    if chart_month < 1 or chart_month > 12:
        chart_month = today.month
    days_in_month = calendar.monthrange(chart_year, chart_month)[1]

    chart_labels = list(range(1, days_in_month + 1))
    chart_values_day = [0] * days_in_month
    chart_values_night = [0] * days_in_month
    max_workers = 0
    if chart_project_id:
        try:
            rows = (
                db.session.query(
                    DailyWorkforce.date,
                    func.coalesce(func.sum(DailyWorkforce.workers_count), 0).label('w_day'),
                    func.coalesce(func.sum(DailyWorkforce.workers_count_night), 0).label('w_night'),
                )
                .filter(
                    DailyWorkforce.project_id == chart_project_id,
                    DailyWorkforce.date >= date(chart_year, chart_month, 1),
                    DailyWorkforce.date <= date(chart_year, chart_month, days_in_month),
                )
                .group_by(DailyWorkforce.date)
                .all()
            )
            for r in rows:
                if not r.date:
                    continue
                idx = r.date.day - 1
                day_val = int(r.w_day or 0)
                night_val = int(r.w_night or 0)
                chart_values_day[idx] = day_val
                chart_values_night[idx] = night_val
                total_workers = day_val + night_val
                if total_workers > max_workers:
                    max_workers = total_workers
        except Exception:
            db.session.rollback()
            chart_values_day = [0] * days_in_month
            chart_values_night = [0] * days_in_month
            max_workers = 0

    return render_template(
        'main/dashboards.html',
        projects=projects,
        people_stats=people_stats,
        project_planning=project_planning,
        chart_project_id=chart_project_id,
        chart_year=chart_year,
        chart_month=chart_month,
        chart_labels=chart_labels,
        chart_values_day=chart_values_day,
        chart_values_night=chart_values_night,
        chart_max_workers=max_workers,
    )


@main_bp.route('/')
def index():
    if not current_user.is_authenticated:
        flash('Для просмотра объектов нужно войти', 'warning')
        return redirect(url_for('auth.login'))
    projects = Project.query.order_by(Project.id.desc()).all()
    return render_template('main/index.html', projects=projects)


@main_bp.route('/create_project', methods=['GET', 'POST'])
@login_required
def create_project():
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project(
            name=form.name.data.strip(),
            contract_number=form.contract_number.data.strip() or None,
            address=form.address.data.strip() or None,
            type_construction=form.type_construction.data or None,
            start_date=form.start_date.data,
            end_date=form.end_date.data
        )
        db.session.add(project)
        db.session.commit()

        media_path = os.path.join(current_app.config['MEDIA_DIR'], 'projects', str(project.id))
        os.makedirs(media_path, exist_ok=True)
        os.makedirs(os.path.join(media_path, '0_common'), exist_ok=True)

        flash(f'Объект "{project.name}" создан', 'success')
        return redirect(url_for('main.index'))
    return render_template('main/create_project.html', form=form)


@main_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)
    if form.validate_on_submit():
        form.populate_obj(project)
        db.session.commit()
        flash(f'Объект "{project.name}" обновлён', 'success')
        return redirect(url_for('main.index'))
    return render_template('main/edit_project.html', form=form, project=project)


def _project_delete_impact(project_id):
    """Подсчёт связанных записей перед удалением проекта (для подтверждения)."""
    buildings_count = Building.query.filter_by(project_id=project_id).count()
    floors_count = Floor.query.join(Building).filter(Building.project_id == project_id).count()
    documents_count = Document.query.filter_by(project_id=project_id).count()
    movements_count = MaterialMovement.query.filter_by(project_id=project_id).count()
    schedule_works_count = ScheduleWork.query.filter_by(project_id=project_id).count()
    return {
        'buildings': buildings_count,
        'floors': floors_count,
        'documents': documents_count,
        'movements': movements_count,
        'schedule_works': schedule_works_count,
    }


@main_bp.route('/project/<int:project_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if request.method == 'GET':
        impact = _project_delete_impact(project_id)
        return render_template(
            'main/delete_project_confirm.html',
            project=project,
            impact=impact,
        )
    if request.form.get('confirm') != 'yes':
        flash('Удаление отменено. Подтвердите флажок для удаления.', 'warning')
        return redirect(url_for('main.delete_project', project_id=project_id))
    project_name = project.name
    try:
        movement_ids = [m.id for m in MaterialMovement.query.filter_by(project_id=project_id).all()]
        for mid in movement_ids:
            MovementDocument.query.filter_by(movement_id=mid).delete()
        MaterialMovement.query.filter_by(project_id=project_id).delete()
        db.session.delete(project)
        db.session.commit()
        media_path = os.path.join(current_app.config['MEDIA_DIR'], 'projects', str(project_id))
        if os.path.exists(media_path):
            shutil.rmtree(media_path)
        current_app.logger.info('Project id=%s "%s" deleted (cascade: buildings, floors, documents, movements)', project_id, project_name)
        flash(f'Объект «{project_name}» и все связанные данные удалены.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error deleting project id=%s', project_id)
        flash(f'Ошибка при удалении: {e}', 'danger')
        return redirect(url_for('main.delete_project', project_id=project_id))
    return redirect(url_for('main.index'))