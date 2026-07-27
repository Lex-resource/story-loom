@echo off
setlocal
set "PYTHON_EXE=python"
pushd "%~dp0"
echo Migrating PostgreSQL database to the latest Alembic revision...
"%PYTHON_EXE%" scripts\migrate_db.py
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
