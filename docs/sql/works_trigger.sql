-- ОПЦИОНАЛЬНО: триггер для автоматического обновления works.percent_complete при изменении work_progress.
-- Назначение: синхронизация колонки percent_complete для экспорта/отчётов; может дать прирост при частых запросах к works без пересчёта.
-- Основной источник истины для UI — пересчёт в представлениях (Flask); триггер не обязателен. Выполнять в pgAdmin при необходимости.

CREATE OR REPLACE FUNCTION update_work_percent_from_progress()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  v_work_id INTEGER;
  v_total   DOUBLE PRECISION;
  v_volume  DOUBLE PRECISION;
BEGIN
  v_work_id := COALESCE(NEW.work_id, OLD.work_id);
  IF v_work_id IS NULL THEN
    RETURN COALESCE(NEW, OLD);
  END IF;

  SELECT SUM(daily_execution), w.volume
    INTO v_total, v_volume
    FROM work_progress p
    JOIN works w ON w.id = p.work_id
   WHERE p.work_id = v_work_id
   GROUP BY w.volume;

  UPDATE works
     SET percent_complete = CASE
       WHEN (v_volume IS NULL OR v_volume <= 0) THEN NULL
       ELSE ROUND(COALESCE(v_total, 0) / NULLIF(v_volume, 0) * 100.0, 1)
     END
   WHERE id = v_work_id;

  RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS tr_work_progress_percent ON work_progress;
CREATE TRIGGER tr_work_progress_percent
  AFTER INSERT OR UPDATE OF daily_execution OR DELETE ON work_progress
  FOR EACH ROW
  EXECUTE PROCEDURE update_work_percent_from_progress();
