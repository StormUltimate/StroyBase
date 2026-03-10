-- StroyBase: учёт по дням с разделением дневная/ночная смена
-- Выполнить в pgAdmin при необходимости создать таблицу или добавить колонку ночной смены.

-- Таблица (если ещё нет): одна запись на проект + дата + подрядчик; день и ночь в одной строке
CREATE TABLE IF NOT EXISTS daily_workforce (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    contractor_name VARCHAR(255) NOT NULL,
    workers_count INTEGER DEFAULT 0,
    shift_hours NUMERIC(5,2) DEFAULT 0.00,       -- дневная смена, часов (макс. 12)
    shift_hours_night NUMERIC(5,2) DEFAULT 0.00,   -- ночная смена, часов (макс. 12), всего в сутках макс. 24
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_workforce ON daily_workforce (project_id, date, contractor_name);

-- Если таблица уже была создана без ночной смены — добавить колонку:
ALTER TABLE daily_workforce ADD COLUMN IF NOT EXISTS shift_hours_night NUMERIC(5,2) DEFAULT 0;

-- Отдельный счётчик людей по ночной смене (на кнопке «Ночь» — своё число):
ALTER TABLE daily_workforce ADD COLUMN IF NOT EXISTS workers_count_night INTEGER DEFAULT 0;
