@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Drone Video Platform
cd /d "%~dp0"
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV=%BACKEND%\.venv"
set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%"

echo ============================================================
echo   Drone Video Platform - Downloader + Trimmer (aplikasi web lokal)
echo   Menu utama: Drone Video Downloader / Drone Video Trimmer.
echo   Semua analisis AI dan pemrosesan video berjalan di komputer ini.
echo ============================================================
echo.

rem ---------------------------------------------------------- 1. Python
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set "PY=py -3")
if not defined PY (
  where python >nul 2>&1 && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set "PY=python")
)
if not defined PY (
  echo [GAGAL] Python 3.10 atau lebih baru tidak ditemukan.
  echo         Unduh dari https://www.python.org/downloads/ dan centang "Add python.exe to PATH".
  goto :fail
)
for /f "delims=" %%v in ('%PY% -c "import platform; print(platform.python_version())"') do set "PYVER=%%v"
echo [OK] Python %PYVER%

rem ---------------------------------------------------------- 2. Node.js
where node >nul 2>&1
if errorlevel 1 (
  if exist "%FRONTEND%\dist\index.html" (
    echo [INFO] Node.js tidak ditemukan, memakai frontend yang sudah di-build.
    set "NO_NODE=1"
  ) else (
    echo [GAGAL] Node.js tidak ditemukan. Unduh versi LTS dari https://nodejs.org/
    goto :fail
  )
) else (
  for /f "delims=" %%v in ('node --version') do echo [OK] Node.js %%v
)

rem ---------------------------------------------------------- 3. FFmpeg
if exist "%ROOT%tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%ROOT%tools\ffmpeg\bin;%PATH%"
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [GAGAL] FFmpeg tidak ditemukan.
  echo         Unduh build Windows dari https://www.gyan.dev/ffmpeg/builds/ ^(ffmpeg-release-essentials.zip^),
  echo         lalu ekstrak sehingga ada file tools\ffmpeg\bin\ffmpeg.exe di folder aplikasi ini,
  echo         atau tambahkan folder bin FFmpeg ke PATH.
  goto :fail
)
where ffprobe >nul 2>&1
if errorlevel 1 (
  echo [GAGAL] FFprobe tidak ditemukan ^(biasanya satu paket dengan FFmpeg^).
  goto :fail
)
echo [OK] FFmpeg ditemukan

rem ---------------------------------------------------------- 4. Virtual environment
rem Virtual environment terikat ke lokasi Python di PC tempat ia dibuat. Bila folder aplikasi
rem disalin dari PC lain, .venv lama tidak bisa dipakai -> dibuat ulang otomatis.
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" goto :make_venv
"%VPY%" -c "import sys" >nul 2>&1
if not errorlevel 1 goto :venv_ok
echo [INFO] Virtual environment Python berasal dari komputer lain / rusak. Membuat ulang...
rmdir /s /q "%VENV%" >nul 2>&1
if exist "%BACKEND%\.deps_installed" del /q "%BACKEND%\.deps_installed" >nul 2>&1
:make_venv
echo [..] Membuat virtual environment Python...
%PY% -m venv "%VENV%" || goto :fail
if exist "%BACKEND%\.deps_installed" del /q "%BACKEND%\.deps_installed" >nul 2>&1
:venv_ok

rem ---------------------------------------------------------- 5. Dependensi Python
set "NEED_PIP=1"
if exist "%BACKEND%\.deps_installed" (
  fc /b "%BACKEND%\requirements.txt" "%BACKEND%\.deps_installed" >nul 2>&1 && set "NEED_PIP=0"
)
if "%NEED_PIP%"=="1" (
  echo [..] Menginstal dependensi Python ^(pertama kali memerlukan internet^)...
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r "%BACKEND%\requirements.txt" || (
    echo [GAGAL] Instalasi dependensi Python gagal. Periksa koneksi internet lalu jalankan ulang.
    goto :fail
  )
  copy /y "%BACKEND%\requirements.txt" "%BACKEND%\.deps_installed" >nul
) else (
  echo [OK] Dependensi Python sudah terpasang
)

rem ---------------------------------------------------------- 6. Dependensi & build frontend
if not defined NO_NODE (
  if not exist "%FRONTEND%\node_modules" (
    echo [..] Menginstal dependensi frontend ^(pertama kali memerlukan internet^)...
    pushd "%FRONTEND%"
    call npm install --no-audit --no-fund || (popd & echo [GAGAL] npm install gagal. & goto :fail)
    popd
  ) else (
    echo [OK] Dependensi frontend sudah terpasang
  )
  set "NEED_BUILD=1"
  if exist "%FRONTEND%\dist\index.html" (
    powershell -NoProfile -Command "$d=(Get-Item '%FRONTEND%\dist\index.html').LastWriteTime; $n=Get-ChildItem '%FRONTEND%\src','%FRONTEND%\index.html','%FRONTEND%\downloader','%FRONTEND%\trimmer','%FRONTEND%\package.json','%FRONTEND%\vite.config.ts' -Recurse -File | Where-Object { $_.LastWriteTime -gt $d }; if ($n) { exit 1 } else { exit 0 }" && set "NEED_BUILD=0"
  )
  if "!NEED_BUILD!"=="1" (
    echo [..] Membangun frontend...
    pushd "%FRONTEND%"
    call npm run build || (popd & echo [GAGAL] Build frontend gagal. & goto :fail)
    popd
  ) else (
    echo [OK] Frontend sudah terbaru
  )
)

rem ---------------------------------------------------------- 7. Database & direktori
echo [..] Menyiapkan database dan direktori data...
pushd "%BACKEND%"
"%VPY%" -m app.main --init-db || (popd & echo [GAGAL] Database tidak dapat disiapkan. & goto :fail)
popd

rem ---------------------------------------------------------- 8. Port
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] Port %PORT% sudah dipakai. Kemungkinan aplikasi sudah berjalan - membuka browser.
  start "" "%URL%"
  goto :end
)

rem ---------------------------------------------------------- 9. Jalankan backend + buka browser
echo [..] Menjalankan server di %URL%
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++){ try { Invoke-WebRequest -UseBasicParsing '%URL%/api/health' -TimeoutSec 2 | Out-Null; Start-Process '%URL%'; break } catch { Start-Sleep -Milliseconds 500 } }"
echo.
echo   Aplikasi berjalan. Biarkan jendela ini terbuka selama bekerja.
echo   Tutup jendela ini ^(atau tekan Ctrl+C^) untuk menghentikan aplikasi.
echo.
pushd "%BACKEND%"
"%VPY%" -m app.main --host 127.0.0.1 --port %PORT%
popd
goto :end

:fail
echo.
echo Aplikasi belum dapat dijalankan. Perbaiki masalah di atas lalu jalankan start.bat lagi.
pause
exit /b 1

:end
endlocal
