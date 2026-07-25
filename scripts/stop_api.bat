@echo off
setlocal EnableExtensions
REM Stop ONLY the process listening on 127.0.0.1:3811 (PXYORDERFLOW API).
REM Does not touch quant, copy-trade, Caddy, or other ports.

set "OF_PORT=3811"
echo [OF] Looking for listeners on port %OF_PORT% ...

set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%OF_PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo [OF] Killing PID %%P on port %OF_PORT%
  taskkill /PID %%P /F >nul 2>&1
  if errorlevel 1 (
    echo [OF] taskkill failed for PID %%P — check privileges / ownership
  ) else (
    echo [OF] PID %%P stopped
  )
)

if not defined FOUND (
  echo [OF] No LISTENING process on port %OF_PORT%
)

endlocal
