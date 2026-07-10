@echo off
cd /d "%~dp0"
.\.venv\Scripts\python -m src.upload_latest %*
pause
