# Внесение вклада в StroyBase (RU)

Спасибо за интерес к проекту **StroyBase** — открытой платформе для ПТО строительных организаций.

Перед тем как отправлять изменения, пожалуйста, придерживайтесь следующих правил.

## 1. Обсуждение изменений

- Открывайте Issue в GitHub для багов, улучшений и новых функций.
- В описании указывайте:
  - какой раздел системы затрагивается (Проект, Корпус, Этаж, материалы, движение материалов, ГПР, учёт людей и т.д.);
  - ожидаемое поведение;
  - фактическое поведение;
  - шаги для воспроизведения (если это баг).

## 2. Оформление Pull Request

- Один PR — одна понятная задача (фикс бага, небольшое улучшение, изолированная новая фича).
- Заголовок PR — кратко и по делу на русском или английском.
- В описании PR:
  - **Что сделано** (1–3 пункта);
  - **Как проверить** (шаги, команды);
  - **Риски / обратная совместимость**, если есть.
- Все PR должны быть привязаны к Issue (если это не мелкая правка документации).

## 3. CHANGELOG

- После каждого **существенного изменения** обновляйте `CHANGELOG.md` в корне.
- Формат новой записи:

  ```text
  DD.MM.YYYY — Краткое название изменения

  - Что было сделано
  - Какие файлы изменены (кратко по блокам)
  - Краткий эффект для пользователя
  ```

- Новые записи добавляйте **вверху файла** (последние изменения — первыми).

## 4. Изменения схемы БД (миграции)

- **Структура БД управляется только через Alembic / Flask-Migrate.**
- Нельзя править структуру таблиц напрямую через pgAdmin (CREATE/ALTER TABLE для production‑схемы).
- Алгоритм:
  1. Обновить модели в `app/models.py` (все новые поля — `nullable=True`, если нет особой причины).
  2. Сгенерировать миграцию:

     ```bash
     flask db migrate -m "Краткое описание изменения схемы"
     ```

  3. Проверить миграцию (upgrade/downgrade) на тестовой БД.
  4. Применить:

     ```bash
     flask db upgrade
     ```

  5. Добавить файлы из `migrations/versions/*.py` в коммит.

## 5. Тесты

- Сейчас в репозитории может не быть автоматических тестов; при добавлении тестов используйте **pytest**.
- Структура по умолчанию:

  ```text
  tests/
    test_*.py
  ```

- Локальный запуск:

  ```bash
  pytest
  ```

- Если вы добавили тесты, обязательно описывайте, какие сценарии они покрывают, в описании PR.

## 6. Код‑стайл и линтеры

- Базовые инструменты:
  - **flake8** — статический анализ;
  - **black** — автоформатирование.
- Конфигурация:
  - `.flake8` — настройки для flake8 (max-line-length=88, игнор E203/W503 и т.д.);
  - `pyproject.toml` — настройки для black (line-length=88, Python 3.11).
- Перед отправкой PR:

  ```bash
  flake8 .
  black .
  ```

- В CI настроен запуск:
  - `flake8 .`
  - `black --check .`
  - `pytest` (если есть директория `tests/`).

## 7. UI и язык интерфейса

- Весь пользовательский интерфейс (страницы, кнопки, подписи, сообщения об ошибках) — **на русском языке**.
- Исключения: технические коды, названия библиотек и файлов.

## 8. Безопасность и данные

- Не добавляйте в репозиторий:
  - файлы `.env` и любые секреты (пароли, токены, ключи доступа);
  - реальные серверные URL и IP‑адреса продакшн‑систем;
  - персональные данные (ФИО, телефоны, e‑mail и т.п.).
- Если вы случайно закоммитили секрет — немедленно поменяйте его в вашей инфраструктуре и удалите/перепишите историю (git filter‑repo), затем откройте Issue.

---

# Contributing to StroyBase (EN)

Thanks for your interest in **StroyBase**, an open platform for construction site management (PTO).

Please follow these guidelines when contributing.

## 1. Discuss your changes first

- Open a GitHub Issue for bugs, improvements or new features.
- In the description, please include:
  - which part of the system is affected (Project, Building, Floor, materials, material movements, Gantt, workforce, daily work progress, etc.);
  - expected behavior;
  - actual behavior;
  - steps to reproduce (for bugs).

## 2. Pull Request guidelines

- One PR should address **one focused change** (bug fix, small enhancement, isolated feature).
- PR title should be short and descriptive (English or Russian).
- PR description should include:
  - **What was changed** (1–3 bullet points);
  - **How to test it** (steps and commands);
  - **Risks / breaking changes**, if any.
- Link the PR to an Issue when possible.

## 3. CHANGELOG

- For every **non‑trivial change**, update `CHANGELOG.md`.
- Use the Russian format:

  ```text
  DD.MM.YYYY — Short change title

  - What was done
  - Which files were changed (high level)
  - Short effect for the user
  ```

- New entries go to the **top** of the file.

## 4. Database schema changes (migrations)

- The database schema is managed **only via Alembic / Flask-Migrate**.
- Do **not** change production tables manually via pgAdmin (CREATE/ALTER TABLE).
- Typical workflow:
  1. Update models in `app/models.py` (new fields should generally be `nullable=True`).
  2. Generate a migration:

     ```bash
     flask db migrate -m "Short description of schema change"
     ```

  3. Review the generated migration.
  4. Apply:

     ```bash
     flask db upgrade
     ```

  5. Commit the new files under `migrations/versions/`.

## 5. Tests

- We use **pytest** for automated tests (once they appear).
- Suggested layout:

  ```text
  tests/
    test_*.py
  ```

- Run locally:

  ```bash
  pytest
  ```

## 6. Code style and linters

- Tools:
  - **flake8** for linting;
  - **black** for formatting.
- Config:
  - `.flake8` for flake8 settings (max line length 88, ignore E203/W503, etc.);
  - `pyproject.toml` for black settings (line length 88, Python 3.11).
- Before pushing:

  ```bash
  flake8 .
  black .
  ```

## 7. UI language

- All user‑facing text (templates, messages, labels) must be in **Russian**.
- English is fine in comments, docs and code identifiers.

## 8. Secrets and sensitive data

- Do **not** commit:
  - `.env` files or any secrets (passwords, API keys, tokens);
  - real production URLs/IPs;
  - personal data of real people.

If you discover a security issue, please open a private channel with the maintainer (or create a minimal public Issue without sensitive details) and avoid describing real infrastructure in detail.

