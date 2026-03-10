-- Добавить столбец initial_executed в works (объём, учтённый до ежедневного учёта; итог = initial_executed + sum(work_progress)).
-- Выполнить в pgAdmin, если таблица works уже была создана без этого столбца.
-- Пока колонки нет, приложение подгружает работы сырым SQL (без initial_executed); после выполнения этого скрипта используется только ORM.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'works' AND column_name = 'initial_executed'
    ) THEN
        ALTER TABLE works ADD COLUMN initial_executed FLOAT;
        COMMENT ON COLUMN works.initial_executed IS 'Объём, учтённый до ежедневного учёта (импорт/ручной ввод). Итог выполненного = initial_executed + sum(work_progress.daily_execution)';
    END IF;
END $$;
