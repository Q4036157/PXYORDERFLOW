@echo off
setlocal
REM PXYORDERFLOW API — isolated process, bind 127.0.0.1:3811 only
cd /d "%~dp0..\backend"
set OF_BIND_HOST=127.0.0.1
set OF_HTTP_PORT=3811
set OF_MD_MODE=mock
set OF_TRADE_MODE=mock
set OF_TRADING=1
if exist "C:\Python312\python.exe" (
  "C:\Python312\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 3811
) else (
  python -m uvicorn app.main:app --host 127.0.0.1 --port 3811
)
