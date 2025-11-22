@echo off
REM Batch script to start all CryptoSpikes services
REM This script starts CryptoSpikesMain, CryptoSpikesAPI, and CryptoSpikesWeb Windows services

setlocal enabledelayedexpansion
set LOG_FILE=C:\onlyWS\start_all.log
set SERVICES[0]=CryptoSpikesMain
set SERVICES[1]=CryptoSpikesAPI
set SERVICES[2]=CryptoSpikesWeb

REM Logging function
echo [%date% %time%] Starting all CryptoSpikes services... >> "%LOG_FILE%"
echo [%date% %time%] Starting all CryptoSpikes services...

REM Start each service
for /L %%i in (0,1,2) do (
    call set SERVICE_NAME=%%SERVICES[%%i]%%
    
    REM Check if service exists
    sc query "!SERVICE_NAME!" >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] WARNING: Service !SERVICE_NAME! not found >> "%LOG_FILE%"
        echo WARNING: Service !SERVICE_NAME! not found
    ) else (
        REM Check if service is already running
        sc query "!SERVICE_NAME!" | find "RUNNING" >nul
        if errorlevel 1 (
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
        ) else (
            echo [%date% %time%] Service !SERVICE_NAME! is already running >> "%LOG_FILE%"
            echo Service !SERVICE_NAME! is already running
        )
    )
    
    REM Wait a moment between service starts
    timeout /t 2 /nobreak >nul
)

REM Wait a moment and check all services status
timeout /t 2 /nobreak >nul
echo [%date% %time%] Checking services status... >> "%LOG_FILE%"
echo Checking services status...

for /L %%i in (0,1,2) do (
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

echo [%date% %time%] All services start completed! >> "%LOG_FILE%"
echo All services start completed!
pause

