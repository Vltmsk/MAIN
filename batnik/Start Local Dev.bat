@echo off
chcp 65001 >nul
echo ========================================
echo   Запуск локальной разработки
echo   Crypto Spikes Web Interface
echo ========================================
echo.

REM Получаем путь к директории скрипта и переходим в корень проекта
cd /d "%~dp0\.."
set "WEB_DIR=%CD%\WEB"

echo [1/2] Проверка зависимостей...
cd /d "%WEB_DIR%"
if not exist "node_modules" (
    echo Установка зависимостей Node.js...
    call npm install
    if errorlevel 1 (
        echo ОШИБКА: Не удалось установить зависимости
        pause
        exit /b 1
    )
) else (
    echo Зависимости уже установлены
)
echo.

echo [2/2] Запуск Next.js dev сервера...
echo.
echo ========================================
echo   Веб-интерфейс будет доступен по адресу:
echo   http://localhost:3000
echo.
echo   Убедитесь, что API сервер запущен на:
echo   http://localhost:8001
echo.
echo   Для остановки нажмите Ctrl+C
echo ========================================
echo.

REM Убеждаемся, что мы в правильной директории
cd /d "%WEB_DIR%"
call npm run dev

pause

