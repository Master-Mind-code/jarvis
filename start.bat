@echo off
REM Lanceur Orion pour Windows (double-clic ou ligne de commande)
cd /d "%~dp0"
python start.py %*
if errorlevel 1 pause
