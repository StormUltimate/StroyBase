@echo off
cls
title  Console
echo Запуск консоли с активированной средой

call venv\Scripts\activate
echo Среда активирована. Теперь можно вставлять команды.
cmd
