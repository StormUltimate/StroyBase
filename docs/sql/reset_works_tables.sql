-- Очистка работ и ежедневного выполнения по одному проекту (перед повторным импортом).
-- Выполнить в pgAdmin. Замените 9 на нужный project_id.

DELETE FROM work_progress WHERE work_id IN (SELECT id FROM works WHERE project_id = 9);
DELETE FROM works WHERE project_id = 9;
