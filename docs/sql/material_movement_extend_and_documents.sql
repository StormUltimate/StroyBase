-- Расширение таблицы material_movements и связь с документами (накладная, УПД, сертификаты).
-- Выполнить в pgAdmin после создания material_movements (см. комментарий в app/models.py).

-- Новые поля в material_movements (объём, длина, вес, бренд)
ALTER TABLE material_movements
  ADD COLUMN IF NOT EXISTS brand VARCHAR(255),
  ADD COLUMN IF NOT EXISTS volume_m3 NUMERIC(12, 4),
  ADD COLUMN IF NOT EXISTS length_m NUMERIC(12, 4),
  ADD COLUMN IF NOT EXISTS weight_kg NUMERIC(12, 4);

COMMENT ON COLUMN material_movements.brand IS 'Бренд / производитель материала';
COMMENT ON COLUMN material_movements.volume_m3 IS 'Объём, м³';
COMMENT ON COLUMN material_movements.length_m IS 'Длина, м';
COMMENT ON COLUMN material_movements.weight_kg IS 'Вес, кг';

-- Таблица связи «движение материала» ↔ «документ» (накладная, УПД, сертификат и т.д.)
CREATE TABLE IF NOT EXISTS movement_documents (
    movement_id INTEGER NOT NULL REFERENCES material_movements(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    doc_type VARCHAR(50),
    description TEXT,
    "order" INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (movement_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_movement_documents_movement ON movement_documents(movement_id);
CREATE INDEX IF NOT EXISTS idx_movement_documents_document ON movement_documents(document_id);

COMMENT ON TABLE movement_documents IS 'Привязка документов (накладная, УПД, сертификат) к записи о движении материала';
COMMENT ON COLUMN movement_documents.doc_type IS 'invoice=накладная, upd=УПД, certificate=сертификат, other=другое';
