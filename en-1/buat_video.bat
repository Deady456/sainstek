@echo off
cd /d "%~dp0"
.\.venv\Scripts\python -m src.pipeline --no-upload
pause
