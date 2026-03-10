-- StroyBase: добавить колонки для вкладки «Договора» в таблицу documents
-- Выполнить в pgAdmin (подключение к БД StroyBase) по одному или все сразу.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS contract_number VARCHAR(100);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS contract_date DATE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS counterparty VARCHAR(255);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS amount NUMERIC(12, 2);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS contract_status VARCHAR(100);
