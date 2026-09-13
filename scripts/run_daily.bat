@echo off
REM One scheduled scan. Registered with Task Scheduler by scripts\register_task.ps1.
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run these once in this folder:
  echo     py -m venv .venv
  echo     .venv\Scripts\pip install -r requirements.txt matplotlib pykrx
  exit /b 1
)

set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=monitor.config.json

if not exist "logs" mkdir logs
".venv\Scripts\python.exe" -m channel_monitor daily --config "%CONFIG%" >> "logs\daily.out.log" 2>&1
set RC=%ERRORLEVEL%
echo [%DATE% %TIME%] exit=%RC% >> "logs\daily.out.log"
exit /b %RC%
