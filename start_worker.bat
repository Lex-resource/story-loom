@echo off
setlocal
title Novel Assistant - Background Worker
set "PYTHON_EXE=python"
pushd "%~dp0"
echo Starting Background Writer Worker...
"%PYTHON_EXE%" worker.py
popd
pause
endlocal
