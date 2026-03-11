@echo off
setlocal ENABLEDELAYEDEXPANSION
REM Переходим в папку скрипта (корень репозитория)
cd /d "%~dp0"
echo === StroyBase: автоустановка и запуск ===
REM --- 1. Проверка наличия Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH. Установите Python 3.10+ и перезапустите скрипт.
    pause
    exit /b 1
)
REM --- 2. Создание виртуального окружения (если ещё нет) ---
if not exist "venv\Scripts\python.exe" (
    echo Создаём виртуальное окружение venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
) else (
    echo Виртуальное окружение venv уже существует.
)
REM --- 3. Активация виртуального окружения ---
call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать виртуальное окружение.
    pause
    exit /b 1
)
REM --- 4. Установка/обновление зависимостей ---
echo Обновляем pip...
python -m pip install --upgrade pip
echo Устанавливаем зависимости из requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Установка зависимостей завершилась с ошибкой.
    pause
    exit /b 1
)
REM --- 5. Переменные окружения для Flask и БД ---
REM При необходимости отредактируйте строку DATABASE_URL под свою БД.
if not defined DATABASE_URL (
    set "DATABASE_URL=postgresql://postgres:asdf1234@localhost:5432/StroyBase"
)
if not defined SECRET_KEY (
    set "SECRET_KEY=change-me-secret-key"
)
REM Flask будет использовать фабрику приложения create_app из пакета app
set "FLASK_APP=app:create_app"
set "FLASK_ENV=production"
REM --- 6. Применение миграций БД ---
echo Запускаем миграции БД: flask db upgrade ...
flask db upgrade
if errorlevel 1 (
    echo [ОШИБКА] flask db upgrade завершился с ошибкой.
    pause
    exit /b 1
)
REM --- 7. Запуск приложения ---
echo Запускаем приложение StroyBase на http://127.0.0.1:5000 ...
flask run --host=0.0.0.0 --port=5000
REM Если flask run завершился, даём увидеть вывод
echo Приложение остановлено.
pause
endlocal