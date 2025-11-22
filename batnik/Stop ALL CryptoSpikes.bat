@echo off
REM Batch script to stop all CryptoSpikes services
REM This script stops CryptoSpikesMain, CryptoSpikesAPI, and CryptoSpikesWeb Windows services

setlocal enabledelayedexpansion
set LOG_FILE=C:\onlyWS\stop_all.log
set SERVICES[0]=CryptoSpikesMain
set SERVICES[1]=CryptoSpikesAPI
set SERVICES[2]=CryptoSpikesWeb

REM Logging function
echo [%date% %time%] Starting stop of all CryptoSpikes services... >> "%LOG_FILE%"
echo [%date% %time%] Starting stop of all CryptoSpikes services...

REM Stop each service
for /L %%i in (0,1,2) do (
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
                echo [%date% %time%] ERROR: Failed to stop service !SERVICE_NAME! >> "%LOG_FILE%"
                echo ERROR: Failed to stop service !SERVICE_NAME!
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

echo [%date% %time%] All services stop completed! >> "%LOG_FILE%"
echo All services stop completed!
pause

