# app/models.py — StroyBase
# Модели: Project, Building, Floor, Document, Plan, Mark, FloorMaterial, MaterialMovement и др.

from datetime import datetime
from flask_login import UserMixin
from sqlalchemy.ext.hybrid import hybrid_property

from app.extensions import db, bcrypt


# ==================== АССОЦИАТИВНЫЕ ТАБЛИЦЫ ====================

document_work_types = db.Table(
    'document_work_types',
    db.Column('document_id', db.Integer, db.ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
    db.Column('doc_type_id', db.Integer, db.ForeignKey('doc_types.id', ondelete='CASCADE'), primary_key=True),
    extend_existing=True
)


material_documents = db.Table(
    'material_documents',
    db.Column('material_id', db.Integer, db.ForeignKey('floor_materials.id', ondelete='CASCADE'), primary_key=True),
    db.Column('document_id', db.Integer, db.ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
    db.Column('doc_type', db.String(50), nullable=True),          # certificate, invoice, photo, act, other...
    db.Column('description', db.Text, nullable=True),
    db.Column('is_main', db.Boolean, default=False),
    db.Column('uploaded_at', db.DateTime, default=datetime.utcnow),
    db.Column('order', db.Integer, default=0, nullable=False)
)


order_documents = db.Table(
    'order_documents',
    db.Column('order_id', db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), primary_key=True),
    db.Column('document_id', db.Integer, db.ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
)


# ==================== ОСНОВНЫЕ МОДЕЛИ ====================

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contract_number = db.Column(db.String(100))
    address = db.Column(db.String(200))
    type_construction = db.Column(db.String(100))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    buildings = db.relationship('Building', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='project', lazy='dynamic', cascade='all, delete-orphan')


class Building(db.Model):
    __tablename__ = 'buildings'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    building_class = db.Column(db.String(50))
    note = db.Column(db.Text)
    work_type = db.Column(db.String(100))
    color = db.Column(db.String(7))
    area_m2 = db.Column(db.Float)
    total_area_m2 = db.Column(db.Float)
    floors_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    floors = db.relationship('Floor', backref='building', lazy='dynamic', cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='building', lazy='dynamic')
    participants = db.relationship('BuildingParticipant', backref='building', lazy=True, cascade='all, delete-orphan')


class BuildingParticipant(db.Model):
    """Участник корпуса: Заказчик, Генподрядчик, Технадзор, Застройщик и т.д."""
    __tablename__ = 'building_participants'
    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='CASCADE'), nullable=True)
    role_name = db.Column(db.String(100), nullable=True)   # Заказчик, Генподрядчик, Технадзор, Застройщик, ООО
    company_name = db.Column(db.String(255), nullable=True)
    contact_person = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)


# Таблицу создать вручную в pgAdmin:
# CREATE TABLE schedule_works (
#     id SERIAL PRIMARY KEY,
#     project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
#     building_id INTEGER REFERENCES buildings(id) ON DELETE CASCADE,
#     floor_id INTEGER REFERENCES floors(id) ON DELETE SET NULL,
#     name TEXT,
#     planned_start DATE,
#     planned_end DATE,
#     fact_start DATE,
#     fact_end DATE,
#     percent_complete FLOAT,
#     status VARCHAR(50),
#     notes TEXT,
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );
# Для существующей таблицы:
# ALTER TABLE schedule_works ALTER COLUMN building_id DROP NOT NULL;
# ALTER TABLE schedule_works ADD COLUMN IF NOT EXISTS project_id INTEGER NULL REFERENCES projects(id) ON DELETE CASCADE;
# ALTER TABLE schedule_works ADD COLUMN IF NOT EXISTS floor_id   INTEGER NULL REFERENCES floors(id)   ON DELETE SET NULL;
# CREATE INDEX IF NOT EXISTS idx_schedule_works_project ON schedule_works(project_id);
# CREATE INDEX IF NOT EXISTS idx_schedule_works_building ON schedule_works(building_id);
# CREATE INDEX IF NOT EXISTS idx_schedule_works_floor ON schedule_works(floor_id);
class ScheduleWork(db.Model):
    """Работа в графике (ГПР/ГДРС): произвольное название, плановые и фактические даты, % выполнения, статус."""
    __tablename__ = 'schedule_works'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='CASCADE'), nullable=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id', ondelete='SET NULL'), nullable=True)
    name = db.Column(db.Text, nullable=True)                    # полностью свободное название работы от пользователя
    planned_start = db.Column(db.Date, nullable=True)
    planned_end = db.Column(db.Date, nullable=True)
    fact_start = db.Column(db.Date, nullable=True)
    fact_end = db.Column(db.Date, nullable=True)
    percent_complete = db.Column(db.Float, nullable=True)         # 0.0 - 100.0
    status = db.Column(db.String(50), nullable=True)            # "Запланировано", "В работе", "Завершено", "Просрочено"
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    project = db.relationship('Project', backref=db.backref('schedule_works', lazy=True, cascade='all, delete-orphan'))
    building = db.relationship('Building', backref=db.backref('schedule_works', lazy=True, cascade='all, delete-orphan'))
    floor = db.relationship('Floor', backref=db.backref('schedule_works', lazy=True))


# Задачи общего плана производства (ГПП) — Gantt на уровне проекта: название, период, тип (цвет), зависимость.
# SQL для pgAdmin: см. docs/sql/plan_tasks_create.sql
class PlanTask(db.Model):
    """Задача в общем плане производства (ГПП): отображается в Gantt на дашборде проекта."""
    __tablename__ = 'plan_tasks'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True)
    name = db.Column(db.String(500), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    task_type = db.Column(db.String(50), nullable=True)   # Подготовка, Демонтаж, Монтаж — для цвета/секции в Gantt
    dependency_id = db.Column(db.Integer, db.ForeignKey('plan_tasks.id', ondelete='SET NULL'), nullable=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='SET NULL'), nullable=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    project = db.relationship('Project', backref=db.backref('plan_tasks', lazy=True, cascade='all, delete-orphan'))
    dependency = db.relationship('PlanTask', remote_side=[id], backref=db.backref('dependents', lazy=True), foreign_keys=[dependency_id])
    building = db.relationship('Building', backref=db.backref('plan_tasks', lazy=True))
    floor = db.relationship('Floor', backref=db.backref('plan_tasks', lazy=True))


# Работы по корпусам (объёмы, единицы, плановые даты, % выполнения) — для сводной по проекту из Excel.
# Иерархия: Project → Building → Work → WorkProgress.
# SQL для pgAdmin: docs/sql/works_and_progress_create.sql
class Work(db.Model):
    """Работа по корпусу: тип/название, объём, единица, плановая дата завершения, % выполнения."""
    __tablename__ = 'works'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='CASCADE'), nullable=True)
    name = db.Column(db.String(500), nullable=True)           # тип работы / название
    volume = db.Column(db.Float, nullable=True)               # плановый объём
    unit = db.Column(db.String(50), nullable=True)           # м², м³, шт, т и т.д.
    planned_completion_date = db.Column(db.Date, nullable=True)
    percent_complete = db.Column(db.Float, nullable=True)    # 0.0 - 100.0
    initial_executed = db.Column(db.Float, nullable=True)    # объём, учтённый до ежедневного учёта (импорт/ручной ввод); итог = initial_executed + sum(work_progress.daily_execution)
    # Раздел работ: Демонтажные / Общестроительные / Инженерные системы
    category = db.Column(db.String(50), nullable=True)
    # Подраздел инженерных систем (электрика, вентиляция и т.д.) — только для category = 'Инженерные системы'
    system_subsection = db.Column(db.String(100), nullable=True)
    sort_order = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    project = db.relationship('Project', backref=db.backref('works', lazy=True, cascade='all, delete-orphan'))
    building = db.relationship('Building', backref=db.backref('works', lazy=True, cascade='all, delete-orphan'))

    @property
    def system_subsection_or_default(self):
        """Имя подраздела инженерных систем для группировки в UI."""
        return self.system_subsection or 'Прочие системы'


class WorkProgress(db.Model):
    """Ежедневное выполнение по работе (объём за день)."""
    __tablename__ = 'work_progress'
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('works.id', ondelete='CASCADE'), nullable=True)
    date = db.Column(db.Date, nullable=True)
    daily_execution = db.Column(db.Float, nullable=True)       # объём выполненный за день
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    work = db.relationship('Work', backref=db.backref('progress', lazy='dynamic', cascade='all, delete-orphan'))


# SQL для ручного создания в pgAdmin (PostgreSQL: ON UPDATE NOW() не поддерживается — использовать триггер для updated_at или убрать):
# CREATE TABLE IF NOT EXISTS daily_workforce (
#     id SERIAL PRIMARY KEY,
#     project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
#     date DATE NOT NULL,
#     contractor_name VARCHAR(255) NOT NULL,
#     workers_count INTEGER DEFAULT 0,
#     shift_hours NUMERIC(5,2) DEFAULT 0.00,
#     notes TEXT,
#     created_at TIMESTAMP DEFAULT NOW(),
#     updated_at TIMESTAMP DEFAULT NOW()
# );
# CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_workforce ON daily_workforce (project_id, date, contractor_name);
# Для дневной/ночной смены добавить колонку: ALTER TABLE daily_workforce ADD COLUMN IF NOT EXISTS shift_hours_night NUMERIC(5,2) DEFAULT 0;
# Historical data is preserved because we store contractor_name as snapshot. No FK to WorkPerformer → old days never break.
class DailyWorkforce(db.Model):
    """Учёт людей на объекте по дням: только проект (общий объём подрядчиков на площадке), без building_id.
    contractor_name — снимок из справочника или вручную; исторические записи не ломаются при изменении справочника."""
    __tablename__ = 'daily_workforce'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True)
    date = db.Column(db.Date, nullable=True)
    contractor_name = db.Column(db.String(255), nullable=True)   # Подрядчик / субподрядчик
    workers_count = db.Column(db.Integer, nullable=True)           # человек в дневной смене
    workers_count_night = db.Column(db.Integer, nullable=True)    # человек в ночной смене (отдельно от дня)
    shift_hours = db.Column(db.Float, nullable=True)              # дневная смена, часов (макс. 12)
    shift_hours_night = db.Column(db.Float, nullable=True)       # ночная смена, часов (макс. 12), всего в сутках макс. 24
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    project = db.relationship('Project', backref=db.backref('daily_workforce', lazy=True, cascade='all, delete-orphan'))


# Таблицу создать вручную в pgAdmin: work_performers (id, project_id, name, company, notes).
class WorkPerformer(db.Model):
    """Справочник исполнителей работ по проекту (id, project_id, name, organization=company, note=notes).
    Без дат и объёмов — только список для выбора в календаре."""
    __tablename__ = 'work_performers'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True)
    name = db.Column(db.String(255), nullable=True)
    company = db.Column(db.String(255), nullable=True)   # в API отдаётся как organization
    notes = db.Column(db.Text, nullable=True)           # в API отдаётся как note
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    project = db.relationship('Project', backref=db.backref('work_performers', lazy=True, cascade='all, delete-orphan'))


class Floor(db.Model):
    __tablename__ = 'floors'
    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    floor_type = db.Column(db.String(50))
    note = db.Column(db.Text)
    area_m2 = db.Column(db.Float)
    total_area_m2 = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    documents = db.relationship('Document', backref='floor', lazy='dynamic')
    plans = db.relationship('Plan', backref='floor', lazy='dynamic', cascade='all, delete-orphan')
    marks = db.relationship('Mark', backref='floor', lazy='dynamic', cascade='all, delete-orphan')
    materials = db.relationship('FloorMaterial', backref='floor', lazy='dynamic', cascade='all, delete-orphan')
    equipment = db.relationship('FloorEquipment', backref='floor', lazy='dynamic', cascade='all, delete-orphan')
    quantities = db.relationship('FloorQuantity', backref='floor', lazy='dynamic', cascade='all, delete-orphan')
    tasks = db.relationship('Task', backref='floor', lazy='dynamic', cascade='all, delete-orphan')


# ==================== МОДЕЛИ ДОКУМЕНТОВ, ПЛАНОВ, МЕТОК ====================

class DocType(db.Model):
    __tablename__ = 'doc_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=100)


class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id'), nullable=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id'), nullable=True)
    mark_id = db.Column(db.Integer, db.ForeignKey('marks.id'), nullable=True)

    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    filename = db.Column(db.String(255))
    stored_path = db.Column(db.String(255))
    thumbnail_path = db.Column(db.String(255))
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_modified_at = db.Column(db.DateTime, nullable=True)  # дата создания/изменения файла (или вручную)
    width_px = db.Column(db.Integer)
    height_px = db.Column(db.Integer)
    # Признак того, что изображение является сканом документа (акт, письмо и т.п.), а не «фото стройки»
    is_document_image = db.Column(db.Boolean, nullable=True)
    # Поля для документов типа «Договор» (вкладка Договора на странице корпуса)
    contract_number = db.Column(db.String(100), nullable=True)   # номер договора
    contract_date = db.Column(db.Date, nullable=True)            # дата заключения
    counterparty = db.Column(db.String(255), nullable=True)      # контрагент
    amount = db.Column(db.Numeric(12, 2), nullable=True)          # сумма
    contract_status = db.Column(db.String(100), nullable=True)    # статус

    work_types = db.relationship('DocType', secondary=document_work_types, backref='documents')
    linked_materials = db.relationship('FloorMaterial', secondary=material_documents, backref='documents', lazy='dynamic')
    orders = db.relationship('Order', secondary=order_documents, backref='documents', lazy='dynamic')

    @property
    def marker(self):
        """Связь с меткой на плане (алиас для mark)."""
        return self.mark


class Plan(db.Model):
    __tablename__ = 'plans'
    id = db.Column(db.Integer, primary_key=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id'), nullable=False)
    name = db.Column(db.String(255))
    image_path = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    marks = db.relationship('Mark', backref='plan', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def custom_name(self):
        return self.name or 'План'


class Mark(db.Model):
    __tablename__ = 'marks'
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=False)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id'))
    x = db.Column(db.Float)
    y = db.Column(db.Float)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    documents = db.relationship('Document', backref='mark', lazy='dynamic')


# ==================== МАТЕРИАЛЫ, КАТЕГОРИИ, ЗАКАЗЫ ====================

class MaterialCategory(db.Model):
    __tablename__ = 'material_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('material_categories.id'), nullable=True)
    parent = db.relationship('MaterialCategory', remote_side=[id], backref='children')

    materials = db.relationship('FloorMaterial', backref='category', lazy='dynamic')


class FloorMaterial(db.Model):
    __tablename__ = 'floor_materials'
    id = db.Column(db.Integer, primary_key=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id'), nullable=False)

    name = db.Column(db.String(255), nullable=False)
    brand = db.Column(db.String(255))
    gost = db.Column(db.String(255))
    unit = db.Column(db.String(50))
    color = db.Column(db.String(100))
    price_per_unit = db.Column(db.Numeric(10, 2))

    planned_quantity = db.Column(db.Numeric(10, 2))
    actual_quantity = db.Column(db.Numeric(10, 2))
    status = db.Column(db.String(100), default='Запланировано')

    purchase_date = db.Column(db.Date)
    delivery_date = db.Column(db.Date)
    arrival_date = db.Column(db.Date)
    install_date = db.Column(db.Date)
    demolition_date = db.Column(db.Date)

    note = db.Column(db.Text)

    certificate_document_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('material_categories.id'))
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))

    orders = db.relationship('Order', backref='material', lazy='dynamic', cascade='all, delete-orphan')

    @hybrid_property
    def total_cost(self):
        if self.actual_quantity is not None and self.price_per_unit is not None:
            return float(self.actual_quantity) * float(self.price_per_unit)
        return 0.0


# Оборудование по этажу с привязкой к паспорту (документ).
# SQL для pgAdmin:
# CREATE TABLE IF NOT EXISTS floor_equipment (
#     id SERIAL PRIMARY KEY,
#     floor_id INTEGER REFERENCES floors(id) ON DELETE CASCADE,
#     name VARCHAR(255),
#     brand VARCHAR(255),
#     passport_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
#     note TEXT
# );
# CREATE INDEX IF NOT EXISTS idx_floor_equipment_floor ON floor_equipment(floor_id);
class FloorEquipment(db.Model):
    """Оборудование на этаже с привязкой к паспорту (документ)."""
    __tablename__ = 'floor_equipment'
    id = db.Column(db.Integer, primary_key=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id', ondelete='CASCADE'), nullable=True)
    name = db.Column(db.String(255), nullable=True)
    brand = db.Column(db.String(255), nullable=True)
    passport_document_id = db.Column(db.Integer, db.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True)
    note = db.Column(db.Text, nullable=True)


# Площади и величины по этажу (потолок, стены, погонные метры, кубы) — без привязки к материалу.
# SQL для pgAdmin:
# CREATE TABLE IF NOT EXISTS floor_quantities (
#     id SERIAL PRIMARY KEY,
#     floor_id INTEGER REFERENCES floors(id) ON DELETE CASCADE,
#     name VARCHAR(255),
#     quantity NUMERIC(12, 2),
#     unit VARCHAR(50),
#     note TEXT
# );
# CREATE INDEX IF NOT EXISTS idx_floor_quantities_floor ON floor_quantities(floor_id);
class FloorQuantity(db.Model):
    """Площадь, погонные или кубические метры по этажу (потолок, стены, плинтус и т.д.)."""
    __tablename__ = 'floor_quantities'
    id = db.Column(db.Integer, primary_key=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id', ondelete='CASCADE'), nullable=True)
    name = db.Column(db.String(255), nullable=True)       # например: Площадь потолка, Плинтус, Шпатлёвка стен
    quantity = db.Column(db.Numeric(12, 2), nullable=True)
    unit = db.Column(db.String(50), nullable=True)       # м², п.м, м³, шт
    note = db.Column(db.Text, nullable=True)


class Order(db.Model):
    """Заказ / поставка конкретного материала"""
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('floor_materials.id'), nullable=False)

    supplier_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    price_per_unit = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(12, 2), nullable=False)

    order_date = db.Column(db.Date, default=datetime.utcnow().date)
    expected_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='Запланировано')
    note = db.Column(db.Text)


# Запись о движении материала: привязка к объекту (проект обязателен, корпус/этаж — опционально).
# SQL для ручного создания/изменения в pgAdmin:
# CREATE TABLE IF NOT EXISTS material_movements (
#     id SERIAL PRIMARY KEY,
#     project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#     building_id INTEGER REFERENCES buildings(id) ON DELETE SET NULL,
#     floor_id INTEGER REFERENCES floors(id) ON DELETE SET NULL,
#     material_name VARCHAR(255),
#     quantity NUMERIC(12, 2),
#     unit VARCHAR(50),
#     movement_type VARCHAR(50),
#     movement_date DATE,
#     note TEXT,
#     created_at TIMESTAMP DEFAULT NOW()
# );
# CREATE INDEX IF NOT EXISTS idx_material_movements_project ON material_movements(project_id);
# CREATE INDEX IF NOT EXISTS idx_material_movements_building ON material_movements(building_id);
# CREATE INDEX IF NOT EXISTS idx_material_movements_floor ON material_movements(floor_id);
# CREATE INDEX IF NOT EXISTS idx_material_movements_date ON material_movements(movement_date);
class MaterialMovement(db.Model):
    """Запись о движении материала: приход, расход, перемещение. Привязка к проекту обязательна, к корпусу/этажу — опциональна. Документы (накладная, УПД, сертификаты) — через movement_document_links."""
    __tablename__ = 'material_movements'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='SET NULL'), nullable=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id', ondelete='SET NULL'), nullable=True)

    material_name = db.Column(db.String(255), nullable=True)
    brand = db.Column(db.String(255), nullable=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=True)
    unit = db.Column(db.String(50), nullable=True)
    volume_m3 = db.Column(db.Numeric(12, 4), nullable=True)
    length_m = db.Column(db.Numeric(12, 4), nullable=True)
    weight_kg = db.Column(db.Numeric(12, 4), nullable=True)
    movement_type = db.Column(db.String(50), nullable=True)   # Приход, Расход, Перемещение
    movement_date = db.Column(db.Date, nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    project = db.relationship('Project', backref=db.backref('material_movements', lazy=True))
    building = db.relationship('Building', backref=db.backref('material_movements', lazy=True))
    floor = db.relationship('Floor', backref=db.backref('material_movements', lazy=True))


# Связь «движение материала» ↔ «документ» с типом (накладная, УПД, сертификат).
# SQL: docs/sql/material_movement_extend_and_documents.sql
class MovementDocument(db.Model):
    """Привязка документа к записи о движении материала (накладная, УПД, сертификат)."""
    __tablename__ = 'movement_documents'
    movement_id = db.Column(db.Integer, db.ForeignKey('material_movements.id', ondelete='CASCADE'), primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
    doc_type = db.Column(db.String(50), nullable=True)   # invoice, upd, certificate, other
    description = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, default=0, nullable=False)

    movement = db.relationship('MaterialMovement', backref=db.backref('movement_document_links', lazy='dynamic', cascade='all, delete-orphan'))
    document = db.relationship('Document', backref=db.backref('movement_document_links', lazy='dynamic'))


# ==================== ЗАДАЧИ (фундамент — пока минимально) ====================

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id'), nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(100), default='К выполнению')
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    materials = db.relationship('FloorMaterial', backref='task', lazy='dynamic')


# ==================== ПОЛЬЗОВАТЕЛИ ====================

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(64), index=True, unique=True, nullable=False)
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), index=True, unique=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='viewer')          # viewer, editor, pto, foreman, admin
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    refresh_token = db.Column(db.String(512))
    refresh_token_expiry = db.Column(db.DateTime)

    tasks = db.relationship('Task', backref='assignee', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)