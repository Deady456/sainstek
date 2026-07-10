@echo off
cd /d "%~dp0"
if "%1"=="" (
  echo Penggunaan:
  echo   narasi.bat "teks langsung" [output.mp3]
  echo   narasi.bat @naskah.txt [output.mp3]
  pause
  exit /b
)
.\.venv\Scripts\python -m src.narasi %*
pause
