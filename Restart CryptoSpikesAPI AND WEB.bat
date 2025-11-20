@echo off
REM Batch script to restart CryptoSpikesAPI and CryptoSpikesWeb services
REM This script stops and starts CryptoSpikesAPI and CryptoSpikesWeb Windows services

setlocal enabledelayedexpansion
set LOG_FILE=C:\onlyWS\restart_api_web.log
set SERVICES[0]=CryptoSpikesAPI
set SERVICES[1]=CryptoSpikesWeb

REM Logging function
echo [%date% %time%] Starting restart of CryptoSpikesAPI and CryptoSpikesWeb... >> "%LOG_FILE%"
echo [%date% %time%] Starting restart of CryptoSpikesAPI and CryptoSpikesWeb...

REM Stop each service
for /L %%i in (0,1,1) do (
    call set SERVICE_NAME=%%SERVICES[%%i]%%
    
    REM Check if service exists
    sc query "!SERVICE_NAME!" >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] WARNING: Service !SERVICE_NAME! not found >> "%LOG_FILE%"
        echo WARNING: Service !SERVICE_NAME! not found
    ) else (
        REM Check if service is running
        sc query "!SERVICE_NAME!" | find "RUNNING" >nul
        if not errorlevel 1 (
            echo [%date% %time%] Stopping service !SERVICE_NAME!... >> "%LOG_FILE%"
            echo Stopping service !SERVICE_NAME!...
            net stop "!SERVICE_NAME!"
            
            if errorlevel 1 (
                echo [%date% %time%] WARNING: Failed to stop service or service was already stopped >> "%LOG_FILE%"
                echo WARNING: Failed to stop service or service was already stopped
            ) else (
                echo [%date% %time%] Service !SERVICE_NAME! stopped successfully >> "%LOG_FILE%"
                echo Service !SERVICE_NAME! stopped successfully
            )
        ) else (
            echo [%date% %time%] Service !SERVICE_NAME! is already stopped >> "%LOG_FILE%"
            echo Service !SERVICE_NAME! is already stopped
        )
    )
)

REM Wait for services to fully stop
echo [%date% %time%] Waiting for services to fully stop... >> "%LOG_FILE%"
echo Waiting for services to fully stop...
timeout /t 3 /nobreak >nul

REM Start each service
for /L %%i in (0,1,1) do (
    call set SERVICE_NAME=%%SERVICES[%%i]%%
    
    REM Check if service exists
    sc query "!SERVICE_NAME!" >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] WARNING: Service !SERVICE_NAME! not found >> "%LOG_FILE%"
        echo WARNING: Service !SERVICE_NAME! not found
    ) else (
        echo [%date% %time%] Starting service !SERVICE_NAME!... >> "%LOG_FILE%"
        echo Starting service !SERVICE_NAME!...
        net start "!SERVICE_NAME!"
        
        if errorlevel 1 (
            echo [%date% %time%] ERROR: Failed to start service !SERVICE_NAME! >> "%LOG_FILE%"
            echo ERROR: Failed to start service !SERVICE_NAME!
        ) else (
            echo [%date% %time%] Service !SERVICE_NAME! started successfully >> "%LOG_FILE%"
            echo Service !SERVICE_NAME! started successfully
        )
    )
    
    REM Wait a moment between service starts
    timeout /t 2 /nobreak >nul
)

REM Wait a moment and check services status
timeout /t 2 /nobreak >nul
echo [%date% %time%] Checking services status... >> "%LOG_FILE%"
echo Checking services status...

for /L %%i in (0,1,1) do (
    call set SERVICE_NAME=%%SERVICES[%%i]%%
    sc query "!SERVICE_NAME!" | find "RUNNING" >nul
    if errorlevel 1 (
        echo [%date% %time%] WARNING: Service !SERVICE_NAME! is not running >> "%LOG_FILE%"
        echo WARNING: Service !SERVICE_NAME! is not running
    ) else (
        echo [%date% %time%] Service !SERVICE_NAME! is running >> "%LOG_FILE%"
        echo Service !SERVICE_NAME! is running
    )
)

echo [%date% %time%] Restart completed! >> "%LOG_FILE%"
echo Restart completed!
pause

