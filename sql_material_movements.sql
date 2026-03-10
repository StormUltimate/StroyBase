-- StroyBase: создание таблицы material_movements и индексов (для pgAdmin).
-- Выполнить вручную, если таблицы ещё нет.
-- Привязка к объекту: project_id обязателен, building_id и floor_id опциональны.

-- Создание таблицы
CREATE TABLE IF NOT EXISTS material_movements (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    building_id INTEGER REFERENCES buildings(id) ON DELETE SET NULL,
    floor_id INTEGER REFERENCES floors(id) ON DELETE SET NULL,
    material_name VARCHAR(255),
    quantity NUMERIC(12, 2),
    unit VARCHAR(50),
    movement_type VARCHAR(50),
    movement_date DATE,
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для фильтрации и сортировки
CREATE INDEX IF NOT EXISTS idx_material_movements_project ON material_movements(project_id);
CREATE INDEX IF NOT EXISTS idx_material_movements_building ON material_movements(building_id);
CREATE INDEX IF NOT EXISTS idx_material_movements_floor ON material_movements(floor_id);
CREATE INDEX IF NOT EXISTS idx_material_movements_date ON material_movements(movement_date);
CREATE INDEX IF NOT EXISTS idx_material_movements_type ON material_movements(movement_type);

-- Комментарии к таблице и колонкам (опционально)
COMMENT ON TABLE material_movements IS 'Записи о движении материалов: приход, расход, перемещение. Привязка к проекту обязательна.';
COMMENT ON COLUMN material_movements.project_id IS 'Объект (проект) — обязательная привязка';
COMMENT ON COLUMN material_movements.building_id IS 'Корпус — опционально, можно указать позже';
COMMENT ON COLUMN material_movements.floor_id IS 'Этаж — опционально, можно указать позже';
