-- Добавить столбец system_subsection в works: подраздел инженерных систем (электрика, вентиляция и т.д.).
-- Выполнить в pgAdmin после резервного копирования БД.
-- Поле заполняется только для работ с category = 'Инженерные системы'.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'works' AND column_name = 'system_subsection'
    ) THEN
        ALTER TABLE works
            ADD COLUMN system_subsection VARCHAR(100);
        COMMENT ON COLUMN works.system_subsection IS
            'Подраздел инженерных систем (электрика, вентиляция, сантехника и т.п.) для группировки и расчёта процентов по подгруппам.';
    END IF;
END $$;

