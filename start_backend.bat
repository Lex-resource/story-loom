@echo off
setlocal
title Novel Assistant - Backend API Server
set "PYTHON_EXE=python"
pushd "%~dp0"
if not "%NOVEL_DB_MIGRATED%"=="1" (
    call "%~dp0migrate_db.bat"
    if errorlevel 1 (
        echo Database migration failed. Backend was not started.
        popd
        pause
        exit /b 1
    )
)
echo Starting FastAPI Backend Server on port 8000...
"%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
popd
pause
endlocal
