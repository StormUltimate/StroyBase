-- StroyBase: таблица оборудования по этажу с привязкой к паспорту (документ).
-- Выполнить в pgAdmin при необходимости.

CREATE TABLE IF NOT EXISTS floor_equipment (
    id SERIAL PRIMARY KEY,
    floor_id INTEGER REFERENCES floors(id) ON DELETE CASCADE,
    name VARCHAR(255),
    brand VARCHAR(255),
    passport_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_floor_equipment_floor ON floor_equipment(floor_id);
