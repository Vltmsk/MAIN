@echo off
REM Batch script to run deploy.ps1
REM This script executes the PowerShell deployment script

set DEPLOY_SCRIPT=C:\onlyWS\deploy.ps1
set LOG_FILE=C:\onlyWS\run_deploy.log

REM Logging function
echo [%date% %time%] Starting deployment script... >> "%LOG_FILE%"
echo [%date% %time%] Starting deployment script...
echo.

REM Check if deploy.ps1 exists
if not exist "%DEPLOY_SCRIPT%" (
    echo [%date% %time%] ERROR: Deploy script not found at %DEPLOY_SCRIPT% >> "%LOG_FILE%"
    echo ERROR: Deploy script not found at %DEPLOY_SCRIPT%
    pause
    exit /b 1
)

REM Change to repository directory
cd /d C:\onlyWS

REM Run PowerShell script
echo [%date% %time%] Executing deploy.ps1... >> "%LOG_FILE%"
echo Executing deploy.ps1...
echo.

powershell.exe -ExecutionPolicy Bypass -File "%DEPLOY_SCRIPT%"

if errorlevel 1 (
    echo [%date% %time%] ERROR: Deployment script failed with error code %errorlevel% >> "%LOG_FILE%"
    echo.
    echo ERROR: Deployment script failed with error code %errorlevel%
    pause
    exit /b 1
) else (
    echo [%date% %time%] Deployment script completed successfully >> "%LOG_FILE%"
    echo.
    echo Deployment script completed successfully!
)

pause

