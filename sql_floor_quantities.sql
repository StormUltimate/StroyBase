-- StroyBase: таблица площадей и величин по этажу (потолок, стены, п.м, м³).
-- Выполнить в pgAdmin при необходимости.

CREATE TABLE IF NOT EXISTS floor_quantities (
    id SERIAL PRIMARY KEY,
    floor_id INTEGER REFERENCES floors(id) ON DELETE CASCADE,
    name VARCHAR(255),
    quantity NUMERIC(12, 2),
    unit VARCHAR(50),
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_floor_quantities_floor ON floor_quantities(floor_id);
