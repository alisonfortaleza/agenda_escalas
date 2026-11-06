@echo off
cd /d "%~dp0"
set APP_ENV=local
set SEED_DEMO=1
set BOOTSTRAP_LOCAL=1
python -m app.server
pause
