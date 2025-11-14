@echo off
REM Скрипт для первоначальной настройки Git репозитория (Windows)
REM Запустите этот скрипт на вашем локальном ПК после создания репозитория на GitHub

echo Настройка Git репозитория...
echo.

REM Проверка, инициализирован ли Git
if not exist ".git" (
    echo Инициализация Git репозитория...
    git init
) else (
    echo Git репозиторий уже инициализирован
)

REM Добавление всех файлов
echo Добавление файлов...
git add .

REM Первый коммит
echo Создание первого коммита...
git commit -m "Initial commit: проект готов к деплою"

REM Запрос информации о репозитории
echo.
echo Введите URL вашего GitHub репозитория:
echo Например: https://github.com/username/repository-name.git
set /p repo_url=

REM Добавление remote
echo Добавление remote репозитория...
git remote remove origin 2>nul
git remote add origin %repo_url%

REM Переименование ветки в main
git branch -M main

REM Отправка в GitHub
echo Отправка кода в GitHub...
echo Если будет запрошен пароль, используйте Personal Access Token (не пароль от GitHub)
git push -u origin main

echo.
echo Готово! Код загружен в GitHub.
echo.
echo Следующие шаги:
echo 1. Скопируйте URL вашего репозитория: %repo_url%
echo 2. На сервере Vultr выполните: git clone %repo_url% onlyWS
echo 3. Следуйте инструкциям в DEPLOY_WINDOWS.md
pause

