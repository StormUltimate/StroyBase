-- ARCHIVED: схема теперь управляется миграциями Alembic / Flask-Migrate.
-- Оригинальный SQL сохранён для справки.
-- Работы по корпусам и ежедневное выполнение (для сводной по проекту из Excel).
-- Иерархия: Project → Building → Work → WorkProgress.
-- Выполнить в pgAdmin. Без таблицы work_progress модалка «Ежедневное выполнение» на странице корпуса не будет сохранять данные.
-- Для уже существующих работ: скрипт scripts/backfill_work_progress_to_date.py записывает весь объём на одну выбранную дату, дальше можно править по дням.

-- initial_executed = объём, учтённый до ежедневного учёта (импорт); итог выполненного = initial_executed + sum(work_progress.daily_execution)
CREATE TABLE IF NOT EXISTS works (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NULL REFERENCES projects(id) ON DELETE CASCADE,
    building_id INTEGER NULL REFERENCES buildings(id) ON DELETE CASCADE,
    name VARCHAR(500),
    volume FLOAT,
    unit VARCHAR(50),
    planned_completion_date DATE,
    percent_complete FLOAT,
    initial_executed FLOAT,
    sort_order INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    category VARCHAR(50)
);

-- Ограничения и индексы можно добавить отдельно через works_add_category.sql,
-- но для новых инсталляций сразу задаём индекс по проекту/корпусу/дате/разделу.
CREATE INDEX IF NOT EXISTS idx_works_project ON works(project_id);
CREATE INDEX IF NOT EXISTS idx_works_building ON works(building_id);
CREATE INDEX IF NOT EXISTS idx_works_planned_date ON works(planned_completion_date);
CREATE INDEX IF NOT EXISTS idx_works_category ON works (building_id, category, name);

-- date = дата выполнения части работ (день, за который учтён объём daily_execution)
CREATE TABLE IF NOT EXISTS work_progress (
    id SERIAL PRIMARY KEY,
    work_id INTEGER NULL REFERENCES works(id) ON DELETE CASCADE,
    date DATE,                    -- дата выполнения (день)
    daily_execution FLOAT,       -- объём, выполненный в этот день
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(work_id, date)
);

CREATE INDEX IF NOT EXISTS idx_work_progress_work ON work_progress(work_id);
CREATE INDEX IF NOT EXISTS idx_work_progress_date ON work_progress(date);
