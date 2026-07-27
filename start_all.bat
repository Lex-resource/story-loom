@echo off
setlocal
title Novel Assistant - Launcher
echo Starting all services (Backend, Worker, Frontend)...

call "%~dp0migrate_db.bat"
if errorlevel 1 (
    echo Database migration failed. Services were not started.
    pause
    exit /b 1
)

set "NOVEL_DB_MIGRATED=1"

echo Launching Backend Server...
start "" "%ComSpec%" /c call "%~dp0start_backend.bat"

echo Launching Background Worker...
start "" "%ComSpec%" /c call "%~dp0start_worker.bat"

echo Launching Frontend Server...
start "" "%ComSpec%" /c call "%~dp0start_frontend.bat"

echo All services launched!
endlocal
