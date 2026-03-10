-- Добавить столбец category в works: фиксированный раздел работ.
-- Выполнить в pgAdmin после резервного копирования БД.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'works' AND column_name = 'category'
    ) THEN
        ALTER TABLE works
            ADD COLUMN category VARCHAR(50);
        COMMENT ON COLUMN works.category IS
            'Раздел работ: Демонтажные работы / Общестроительные работы / Инженерные системы.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_name = 'works' AND constraint_name = 'chk_works_category'
    ) THEN
        ALTER TABLE works
            ADD CONSTRAINT chk_works_category
            CHECK (
                category IS NULL OR
                category IN (
                    'Демонтажные работы',
                    'Общестроительные работы',
                    'Инженерные системы'
                )
            );
    END IF;
END $$;

-- Индекс для быстрых выборок и сортировки по разделу внутри корпуса
CREATE INDEX IF NOT EXISTS idx_works_category
    ON works (building_id, category, name);

-- Дополнительный индекс по разделу и наименованию для сводной таблицы по объекту
CREATE INDEX IF NOT EXISTS idx_works_category_name
    ON works (category, name);

