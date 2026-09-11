@echo off
setlocal
title Novel Assistant - Background Worker
pushd "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
echo Starting Background Writer Worker...
set "API_INTERNAL_URL=http://127.0.0.1:8000"
"%PYTHON_EXE%" worker.py
popd
pause
endlocal
