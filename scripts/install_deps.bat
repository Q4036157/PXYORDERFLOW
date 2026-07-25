@echo off
setlocal
REM Install OF backend + frontend deps only. No service start.

cd /d "%~dp0..\backend"
if exist "C:\Python312\python.exe" (
  "C:\Python312\python.exe" -m pip install -r requirements.txt
) else (
  python -m pip install -r requirements.txt
)
if errorlevel 1 (
  echo [OF] pip install failed
  exit /b 1
)

cd /d "%~dp0..\frontend"
call npm install
if errorlevel 1 (
  echo [OF] npm install failed
  exit /b 1
)

echo [OF] deps ok
endlocal
