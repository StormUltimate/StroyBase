-- Добавить столбец date (дата выполнения части работ) в work_progress, если его нет.
-- Выполнить в pgAdmin: если таблицы work_progress ещё нет — сначала создайте её через works_and_progress_create.sql.
-- Если таблица уже есть, но столбца date нет — выполните этот скрипт.
-- date = день, за который записан объём в daily_execution.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'work_progress' AND column_name = 'date'
    ) THEN
        ALTER TABLE work_progress ADD COLUMN date DATE;
        COMMENT ON COLUMN work_progress.date IS 'Дата выполнения (день, за который учтён объём в daily_execution)';
    END IF;
END $$;
