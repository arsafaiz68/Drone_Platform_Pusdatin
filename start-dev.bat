@echo off
rem Mode pengembangan: backend (port 8000) + Vite dev server dengan hot reload (port 5173).
rem Jalankan start.bat sekali terlebih dahulu agar dependensi terpasang.
cd /d "%~dp0"
if exist "tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%~dp0tools\ffmpeg\bin;%PATH%"
start "DVP Backend" cmd /k "cd /d backend && .venv\Scripts\python.exe -m app.main --port 8000"
start "DVP Frontend" cmd /k "cd /d frontend && npm run dev"
timeout /t 4 >nul
start "" http://localhost:5173
