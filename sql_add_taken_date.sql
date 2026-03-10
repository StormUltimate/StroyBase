-- Добавление поля даты создания/изменения файла (StroyBase)
-- Выполнить один раз: psql -U postgres -d StroyBase -f sql_add_taken_date.sql

ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_modified_at TIMESTAMP NULL;
