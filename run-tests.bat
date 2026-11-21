@echo off
rem Menjalankan seluruh pengujian otomatis (butuh FFmpeg). Jalankan start.bat sekali terlebih dahulu.
cd /d "%~dp0"
if exist "tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%~dp0tools\ffmpeg\bin;%PATH%"
backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements-dev.txt
backend\.venv\Scripts\python.exe -m pytest tests -v
pause
