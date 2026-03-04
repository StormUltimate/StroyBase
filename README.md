# StroyBase
StroyBase — открытая платформа для ПТО стройорганизаций | Open platform for construction site management (PTO digitization)
**Open-source web application for the PTO (Production and Technical Department) of a construction company.**

Web-приложение для отдела ПТО строительной компании: объекты, корпуса, этажи, фото, документы, техинформация, планы этажей и учёт материалов.

---

## English

### Description

StroyBase helps construction PTO teams manage projects in a three-level hierarchy (Project → Building → Floor), store photos and documents, track materials and equipment with certificates/passports, maintain technical information (areas, quantities, summaries), and link media to interactive floor plans.

### Features

- **Hierarchy:** Project (object) → Building (corpus) → Floor. Double sidebar navigation (global + contextual).
- **Photos & documents:** Upload at any level; gallery with filters (date, work type/tags); modal viewer; document tables with edit, open, download. Optional “document scan” flag for images. Photo editing: title, description, work types/tags, link to floor plan marker.
- **Floor plans:** Multiple background images per floor; place markers by click; link photos to markers; toggle “show all markers”; panel in media modal to open plan with highlighted marker.
- **Technical information (per floor):** Base characteristics (areas); quantities (areas, linear/cubic meters, units); materials table (plan/actual, price, category) with certificate attachment; equipment table with passport attachment. Inline upload of certificate/passport in modal — document is added and selected immediately. Aggregated summaries at building and project level.
- **Material movement:** Records (in/out/transfer) linked to project/building/floor; filters and list.
- **Workforce calendar:** Daily/night shift headcount and hours per project; modal per day with performer list; summary dashboard.
- **Schedules:** Work items linked to project/building/floor; filters; add from project dashboard.
- **Auth:** Login; optional roles. UI in Russian.

### Tech stack

- **Backend:** Flask, Blueprints, Flask-Login, Flask-WTF
- **ORM:** SQLAlchemy 2.x, Flask-SQLAlchemy
- **Database:** PostgreSQL (schema and data managed manually via pgAdmin; no Alembic migrations)
- **Frontend:** Jinja2, Bootstrap 5 (CDN), vanilla JS
- **Storage:** Local files in `static/media/projects/{project_id}/building_{building_id}/floor_{floor_id}/` with unique names and thumbnails

### Requirements

- Python 3.10+
- PostgreSQL
- See `requirements.txt` for Python dependencies

### Installation

1. Clone the repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```
3. Create a PostgreSQL database and set the connection string:
   ```bash
   set DATABASE_URL=postgresql://user:password@localhost:5432/StroyBase
   set SECRET_KEY=your-secret-key
   ```
   Or use `.env` with `python-dotenv` (see `app/config.py`: `DATABASE_URL`, `SECRET_KEY`).
4. Create tables and schema in pgAdmin (or run your SQL scripts). Optional scripts in the repo root (e.g. `sql_floor_quantities.sql`, `sql_floor_equipment.sql`, `sql_material_movements.sql`) can be run manually for extra tables.
5. Run the application:
   ```bash
   python run.py
   ```
   Or: `flask --app run run` (default: http://0.0.0.0:5000).

### Database

The database is maintained manually (pgAdmin or psql). No migration system is used. New tables/columns are introduced via SQL scripts; model fields are kept nullable where possible to avoid errors before schema updates.

### Project structure

```
StroyBase/
├── app/
│   ├── blueprints/     # auth, main, project, buildings, floors, admin, material_movement
│   ├── templates/      # Jinja2 (project, buildings, floors, shared, …)
│   ├── models.py       # SQLAlchemy models
│   ├── forms.py        # WTForms
│   ├── config.py
│   └── __init__.py     # create_app, Flask app
├── static/
│   └── media/          # uploaded files by project/building/floor
├── run.py              # entry point
├── requirements.txt
├── sql_*.sql           # optional manual schema scripts
└── CHANGELOG.md        # history of changes (Russian)
```

### License

Use and modify as needed. See repository for details.

---

## Русская версия

### Описание

StroyBase — веб-приложение для отдела ПТО строительной компании. Управление объектами в иерархии «Проект → Корпус → Этаж», хранение фото и документов, учёт материалов и оборудования с сертификатами и паспортами, ведение технической информации (площади, величины, сводки), привязка медиа к интерактивным планам этажей.

### Возможности

- **Иерархия:** Объект (проект) → Корпус → Этаж. Двойная боковая навигация (глобальное меню + контекстное).
- **Фото и документы:** Загрузка на любом уровне; галерея с фильтрами (дата, вид работ/теги); модальный просмотр; таблицы документов с редактированием, открытием, кнопкой «Сохранить на ПК». Редактирование фото: название, описание, виды работ/теги, привязка к маркеру на плане этажа.
- **Планы этажей:** Несколько фоновых изображений на этаж; добавление маркеров по клику; привязка фото к маркерам; переключатель «Отображать все маркеры»; в модалке просмотра — панель с мини-планом и ссылкой на полный план с подсветкой маркера.
- **Техническая информация (по этажу):** Базовые характеристики (площади); площади и величины (м², п.м, м³, шт); таблица материалов (план/факт, цена, категория) с привязкой сертификата; таблица оборудования с привязкой паспорта. Загрузка сертификата/паспорта в модальном окне без перехода на другую страницу — документ сразу добавляется в базу и подставляется в выпадающий список. Сводки по материалам на уровне корпуса и объекта.
- **Движение материалов:** Записи приход/расход/перемещение с привязкой к объекту/корпусу/этажу; фильтры и список.
- **Календарь исполнителей:** Учёт людей и часов по дням (дневная/ночная смена) по объекту; модальное окно по дню со списком исполнителей; сводный дашборд «Общая информация».
- **Графики работ:** Работы с привязкой к объекту/корпусу/этажу; фильтры; добавление с дашборда объекта.
- **Авторизация:** Вход, при необходимости роли. Интерфейс на русском языке.

### Стек

- **Сервер:** Flask, Blueprints, Flask-Login, Flask-WTF
- **ORM:** SQLAlchemy 2.x, Flask-SQLAlchemy
- **БД:** PostgreSQL (схема и данные ведутся вручную через pgAdmin; миграции Alembic не используются)
- **Фронт:** Jinja2, Bootstrap 5 (CDN), vanilla JS
- **Файлы:** Локально в `static/media/projects/{project_id}/building_{building_id}/floor_{floor_id}/` с уникальными именами и превью

### Требования

- Python 3.10+
- PostgreSQL
- Зависимости из `requirements.txt`

### Установка

1. Клонировать репозиторий.
2. Создать виртуальное окружение и установить зависимости:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```
3. Создать базу PostgreSQL и задать переменные окружения:
   ```bash
   set DATABASE_URL=postgresql://user:password@localhost:5432/StroyBase
   set SECRET_KEY=your-secret-key
   ```
   Либо использовать `.env` (см. `app/config.py`: `DATABASE_URL`, `SECRET_KEY`).
4. Создать таблицы и схему в pgAdmin (или выполнить свои SQL-скрипты). В корне репозитория лежат опциональные скрипты (`sql_floor_quantities.sql`, `sql_floor_equipment.sql`, `sql_material_movements.sql` и др.) для ручного создания дополнительных таблиц.
5. Запуск:
   ```bash
   python run.py
   ```
   Или: `flask --app run run` (по умолчанию http://0.0.0.0:5000).

### База данных

База данных ведётся вручную (pgAdmin или psql). Система миграций не используется. Новые таблицы и поля вводятся через SQL-скрипты; в моделях поля по возможности nullable, чтобы приложение не падало до обновления схемы.

### Структура проекта

```
StroyBase/
├── app/
│   ├── blueprints/     # auth, main, project, buildings, floors, admin, material_movement
│   ├── templates/      # Jinja2 (project, buildings, floors, shared, …)
│   ├── models.py       # модели SQLAlchemy
│   ├── forms.py        # формы WTForms
│   ├── config.py
│   └── __init__.py     # create_app, приложение Flask
├── static/
│   └── media/          # загруженные файлы по объекту/корпусу/этажу
├── run.py              # точка входа
├── requirements.txt
├── sql_*.sql           # опциональные скрипты схемы
└── CHANGELOG.md        # история изменений
```
