-- Таблица задач общего плана производства (ГПП) для Gantt на дашборде проекта.
-- Выполнить в pgAdmin при включении функции «План работ (ГПП)».

CREATE TABLE IF NOT EXISTS plan_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(500),
    start_date DATE,
    end_date DATE,
    task_type VARCHAR(50),
    dependency_id INTEGER NULL REFERENCES plan_tasks(id) ON DELETE SET NULL,
    building_id INTEGER NULL REFERENCES buildings(id) ON DELETE SET NULL,
    floor_id INTEGER NULL REFERENCES floors(id) ON DELETE SET NULL,
    notes TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_plan_tasks_project ON plan_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_plan_tasks_dependency ON plan_tasks(dependency_id);
CREATE INDEX IF NOT EXISTS idx_plan_tasks_dates ON plan_tasks(start_date, end_date);
