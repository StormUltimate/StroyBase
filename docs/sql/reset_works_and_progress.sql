-- ВНИМАНИЕ: ОПАСНАЯ ОПЕРАЦИЯ!
-- Этот скрипт УДАЛИТ все данные о работах и ежедневном выполнении (таблицы works и work_progress).
-- Перед запуском ОБЯЗАТЕЛЬНО сделайте резервную копию БД через pg_dump или pgAdmin.
-- Пример:
--   pg_dump -h HOST -U USER -d DBNAME -Fc -f backup_before_reset_works.dump

    BEGIN;

    -- Сначала удаляем зависимую таблицу work_progress, затем works
    DROP TABLE IF EXISTS work_progress CASCADE;
    DROP TABLE IF EXISTS works CASCADE;

    -- Создаём works заново
    -- initial_executed = объём, учтённый до ежедневного учёта (импорт/ручной ввод);
    -- итог выполненного = initial_executed + sum(work_progress.daily_execution)

    CREATE TABLE works (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NULL REFERENCES projects(id) ON DELETE CASCADE,
        building_id INTEGER NULL REFERENCES buildings(id) ON DELETE CASCADE,
        name VARCHAR(500),
        volume FLOAT CHECK (volume IS NULL OR volume >= 0),
        unit VARCHAR(50),
        planned_completion_date DATE,
        percent_complete FLOAT,
        initial_executed FLOAT CHECK (initial_executed IS NULL OR initial_executed >= 0),
        sort_order INTEGER,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        category VARCHAR(50)
    );

    COMMENT ON TABLE works IS 'Плановые объёмы работ по корпусам (иерархия: Project → Building → Work).';
    COMMENT ON COLUMN works.project_id IS 'Ссылка на объект (projects.id).';
    COMMENT ON COLUMN works.building_id IS 'Ссылка на корпус (buildings.id).';
    COMMENT ON COLUMN works.name IS 'Наименование работы / вида работ.';
    COMMENT ON COLUMN works.volume IS 'Плановый объём работ.';
    COMMENT ON COLUMN works.unit IS 'Единица измерения (м, м², шт. и т.п.).';
    COMMENT ON COLUMN works.planned_completion_date IS 'Плановая дата завершения работы.';
    COMMENT ON COLUMN works.percent_complete IS 'Процент выполнения (для совместимости, основной расчёт идёт от факта).';
    COMMENT ON COLUMN works.initial_executed IS 'Объём, учтённый до ежедневного учёта (импорт/ручной ввод). Итог выполненного = initial_executed + sum(work_progress.daily_execution).';
    COMMENT ON COLUMN works.sort_order IS 'Порядок сортировки работ на экранах.';
    COMMENT ON COLUMN works.notes IS 'Примечания по работе.';
    COMMENT ON COLUMN works.category IS 'Раздел работ: Демонтажные работы / Общестроительные работы / Инженерные системы.';

    -- Уникальность работы по корпусу и имени (нормализованное имя проверяется на уровне приложения)
    ALTER TABLE works
        ADD CONSTRAINT unique_work_per_building
        UNIQUE (building_id, name)
        DEFERRABLE INITIALLY DEFERRED;

    -- Индексы для производительности и поиска по нормализованному имени
    CREATE INDEX idx_works_project ON works(project_id);
    CREATE INDEX idx_works_building ON works(building_id);
    CREATE INDEX idx_works_planned_date ON works(planned_completion_date);
    CREATE INDEX idx_works_normalized_name ON works (building_id, lower(name));
    CREATE INDEX idx_works_category ON works (building_id, category, name);

    -- Создаём work_progress заново
    -- date = дата выполнения части работ (день, за который учтён объём daily_execution)

    CREATE TABLE work_progress (
        id SERIAL PRIMARY KEY,
        work_id INTEGER NULL REFERENCES works(id) ON DELETE CASCADE,
        date DATE,                    -- дата выполнения (день)
        daily_execution FLOAT,        -- объём, выполненный в этот день
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(work_id, date)
    );

    COMMENT ON TABLE work_progress IS 'Ежедневное выполнение по работам (факт по дням).';
    COMMENT ON COLUMN work_progress.work_id IS 'Ссылка на работу (works.id).';
    COMMENT ON COLUMN work_progress.date IS 'Дата выполнения части работ (день).';
    COMMENT ON COLUMN work_progress.daily_execution IS 'Объём, выполненный в указанный день.';
    COMMENT ON COLUMN work_progress.notes IS 'Примечания по выполнению в конкретный день.';

    CREATE INDEX idx_work_progress_work ON work_progress(work_id);
    CREATE INDEX idx_work_progress_date ON work_progress(date);

    COMMIT;

