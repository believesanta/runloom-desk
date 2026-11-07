@echo off
cd /d "%~dp0"
python -m runloom %*
if errorlevel 1 pause
