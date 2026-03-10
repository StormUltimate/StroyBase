# StroyBase

[![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/<your-org>/stroybase?sort=semver)](https://github.com/<your-org>/stroybase/releases)

Current version: **v0.9.0** — public beta

StroyBase — открытая платформа для ПТО стройорганизаций | Open platform for construction site management (PTO digitization).

Лицензия: MIT. При внесении изменений не добавляйте в код локальные пути, личные имена, датированные пометки и временные метки («ВРЕМЕННО», «для теста»). Полезные комментарии (логика, иерархия Проект → Корпус → Этаж) сохраняйте.

---

## Статус проекта

v0.9.0 — публичная бета. Основной функционал (объекты → корпуса → этажи, галерея, планы с маркерами, материалы план/факт, движение материалов, ГПР, ежедневный учёт людей) стабильно работает. Ждём обратную связь, багофиксы и pull request'ы!

## Обслуживание данных: скрипты очистки

Однократная очистка названий и дедупликация корпусов/этажей выполняется скриптом **`scripts/sanitize_building_floor_names.py`**: санитизация полей `name` в таблицах `buildings` и `floors`, объединение дубликатов по нормализованному имени с переназначением внешних ключей. Изменения необратимы; перед запуском рекомендуется снимок БД.

**Рекомендуемый порядок:**

1. Проверить план без записи в БД:
   ```bash
   python scripts/sanitize_building_floor_names.py --dry-run
   ```
2. При необходимости задать размер батча и отключить запрос подтверждения:
   ```bash
   python scripts/sanitize_building_floor_names.py --batch-size 100 --yes
   ```

**После запуска очистки:** проверьте выпадающие списки «Корпус» и «Этаж» в модальном окне «Движение материалов» (раздел «Движение материалов»): названия должны отображаться читаемо, без артефактов и дубликатов.

Подробнее: раздел **7. Data cleanup** в `docs/MODAL_MOVEMENT_TEMPLATE_DB_MAPPING.md`.

---

## План и график работ (ГПП + сводная таблица + works)

На дашборде проекта одна вкладка **«План и график работ»** объединяет:

1. **План производства (ГПП)** — диаграмма Gantt (задачи с периодом, типом: Подготовка/Демонтаж/Монтаж, зависимости). Рендеринг через [Mermaid.js](https://mermaid.js.org/). Кнопка «Добавить задачу в план», таблица задач плана с редактированием и удалением, масштаб Gantt («+», «−», «100%»).
2. **Сводная таблица фактического выполнения** — список работ по объекту (план/факт даты, % выполнения, статус), с фильтрами по корпусу, этажу, статусу и датам. Кнопка «Добавить работу в график» для учёта фактических сроков и процента выполнения.
3. **Сводка по объёмам работ (works)** — агрегаты по объекту и по корпусам: плановый объём, выполнено, % выполнения, отклонение (данные из таблиц `works` и `work_progress`). Фильтры «Период работ (от/до)» ограничивают учёт по датам выполнения.
4. **Детализация по корпусам** — по каждому корпусу таблица работ (наименование, объём, ед., плановая дата, выполнено, %). Раскрываемая строка показывает график ежедневного выполнения ([Chart.js](https://www.chartjs.org/)).

Шаблон **`app/templates/project/project_graphs.html`** — фрагмент с навигацией по якорям (#works-summary, #works-by-building). API **GET /project/&lt;id&gt;/works/&lt;work_id&gt;/progress** отдаёт данные для графика (опционально с параметрами from_date, to_date).

**Подготовка БД (устаревший подход):** ранее таблица `plan_tasks` создавалась по отдельному SQL‑скрипту, а таблицы `works` и `work_progress` — по `docs/sql/works_and_progress_create.sql`. Сейчас структура БД управляется миграциями (Flask-Migrate / Alembic); актуальные инструкции смотрите в разделе «Database migrations».

---

## Installation & Migrations / Установка и миграции БД

1. **Клонировать репозиторий и создать окружение**

   ```bash
   git clone https://github.com/<your-org>/stroybase.git
   cd stroybase
   python -m venv venv
   venv\Scripts\activate  # Windows
   # или
   source venv/bin/activate  # Linux/macOS
   pip install -r requirements.txt
   ```

2. **Настроить подключение к PostgreSQL**

   В переменных окружения или в `app/config.py` задайте `SQLALCHEMY_DATABASE_URI`, указывающую на вашу БД PostgreSQL (например `postgresql://user:password@localhost:5432/stroybase`).

3. **Инициализировать миграции (однократно для нового проекта)**

   ```bash
   flask db stamp head  # пометить существующую БД как актуальную (если нужно)
   ```

   В репозитории уже есть базовая миграция `migrations/versions/0001_initial_schema.py`, поэтому выполнять `flask db init` и `flask db migrate` с нуля не требуется.

4. **Применить схему БД (fresh install)**

   ```bash
   flask db upgrade
   ```

   После выполнения у вас будут созданы все таблицы, соответствующие моделям в `app/models.py` (проекты, корпуса, этажи, документы, планы, метки, материалы, движение материалов, работы, ежедневное выполнение, общий план, исполнители и т.д.).

5. **Дальнейшие изменения схемы**

   - Вносите изменения в модели SQLAlchemy (`app/models.py`).
   - Генерируйте новую миграцию:

     ```bash
     flask db migrate -m "Описание изменения схемы"
     flask db upgrade
     ```

   - Не редактируйте схему БД вручную через pgAdmin: все структурные изменения должны проходить через Alembic / Flask-Migrate.

## Поддержать проект
StroyBase развивается на энтузиазме как открытый проект под лицензией MIT.  
Ваша поддержка помогает оплачивать серверы для демо‑стендов, домен, а также время на сопровождение и развитие новых функций.
Криптовалютные пожертвования (USDT, только публичные кошельки):
| Площадка  | Сеть   | Адрес (пример)                                   |
|----------|--------|----------------------------------------------------|
| Bybit    | TRC20  | `TPUf9kUboU1V3nxD2iVzP4x1u4kcmsY16i`               |
| Bybit    | ERC20  | `0xd5cf1c5351129875620c40760bbac07771ff860a`       |
Пожертвования являются **добровольными и невозвратными** (donations are voluntary and non‑refundable).  
После перевода вы можете написать в GitHub Discussions или Issues — при желании мы добавим вас в список благодарностей.
---
## Support the project (EN)
StroyBase is developed as an open‑source project under the MIT license.  
Your support helps to cover demo servers, domain costs and maintenance / new feature development time.
Crypto donations (USDT, public wallets only):
| Platform | Network | Address (example)                                 |
|----------|---------|----------------------------------------------------|
| Bybit    | TRC20  | `TPUf9kUboU1V3nxD2iVzP4x1u4kcmsY16i`                |
| Bybit    | ERC20  | `0xd5cf1c5351129875620c40760bbac07771ff860a`        |
Donations are **voluntary and non‑refundable**.  
If you’d like to be mentioned, open a Discussion or Issue after your donation and we’ll add you to the acknowledgements list (if you agree to be public).