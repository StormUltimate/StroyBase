-- Добавление столбцов project_id и floor_id в таблицу schedule_works (если их ещё нет).
-- Выполнить вручную в pgAdmin при ошибке «столбец project_id в таблице schedule_works не существует».
-- После выполнения перезапустите приложение.

ALTER TABLE schedule_works ALTER COLUMN building_id DROP NOT NULL;

ALTER TABLE schedule_works ADD COLUMN IF NOT EXISTS project_id INTEGER NULL REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE schedule_works ADD COLUMN IF NOT EXISTS floor_id   INTEGER NULL REFERENCES floors(id)   ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_schedule_works_project ON schedule_works(project_id);
CREATE INDEX IF NOT EXISTS idx_schedule_works_building ON schedule_works(building_id);
CREATE INDEX IF NOT EXISTS idx_schedule_works_floor ON schedule_works(floor_id);
