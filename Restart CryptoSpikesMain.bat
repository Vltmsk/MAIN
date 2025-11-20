@echo off
REM Batch script to restart CryptoSpikesMain service
REM This script stops and starts the CryptoSpikesMain Windows service

set SERVICE_NAME=CryptoSpikesMain
set LOG_FILE=C:\onlyWS\restart_main.log

REM Logging function
echo [%date% %time%] Starting service restart... >> "%LOG_FILE%"
echo [%date% %time%] Starting service restart...

REM Check if service exists
sc query "%SERVICE_NAME%" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: Service %SERVICE_NAME% not found >> "%LOG_FILE%"
    echo ERROR: Service %SERVICE_NAME% not found
    pause
    exit /b 1
)

REM Stop the service
echo [%date% %time%] Stopping service %SERVICE_NAME%... >> "%LOG_FILE%"
echo Stopping service %SERVICE_NAME%...
net stop "%SERVICE_NAME%"

if errorlevel 1 (
    echo [%date% %time%] WARNING: Failed to stop service or service was already stopped >> "%LOG_FILE%"
    echo WARNING: Failed to stop service or service was already stopped
) else (
    echo [%date% %time%] Service %SERVICE_NAME% stopped successfully >> "%LOG_FILE%"
    echo Service %SERVICE_NAME% stopped successfully
)

REM Wait for service to fully stop
echo [%date% %time%] Waiting for service to fully stop... >> "%LOG_FILE%"
timeout /t 3 /nobreak >nul

REM Start the service
echo [%date% %time%] Starting service %SERVICE_NAME%... >> "%LOG_FILE%"
echo Starting service %SERVICE_NAME%...
net start "%SERVICE_NAME%"

if errorlevel 1 (
    echo [%date% %time%] ERROR: Failed to start service %SERVICE_NAME% >> "%LOG_FILE%"
    echo ERROR: Failed to start service %SERVICE_NAME%
    pause
    exit /b 1
) else (
    echo [%date% %time%] Service %SERVICE_NAME% started successfully >> "%LOG_FILE%"
    echo Service %SERVICE_NAME% started successfully
)

REM Wait a moment and check service status
timeout /t 2 /nobreak >nul
sc query "%SERVICE_NAME%" | find "RUNNING" >nul
if errorlevel 1 (
    echo [%date% %time%] WARNING: Service status check failed or service is not running >> "%LOG_FILE%"
    echo WARNING: Service status check failed or service is not running
) else (
    echo [%date% %time%] Service %SERVICE_NAME% is running >> "%LOG_FILE%"
    echo Service %SERVICE_NAME% is running
)

echo [%date% %time%] Restart completed! >> "%LOG_FILE%"
echo Restart completed!
pause

