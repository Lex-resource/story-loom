@echo off
setlocal
title Novel Assistant - Backend API Server
pushd "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
if not "%NOVEL_DB_MIGRATED%"=="1" (
    call "%~dp0migrate_db.bat"
    if errorlevel 1 (
        echo Database migration failed. Backend was not started.
        popd
        pause
        exit /b 1
    )
)
set "API_INTERNAL_URL=http://127.0.0.1:8000"
echo Starting FastAPI Backend Server on port 8000...
"%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
popd
pause
endlocal
