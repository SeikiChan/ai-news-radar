@echo off
cd /d "%~dp0"
set "PYTHONPATH=%CD%;%PYTHONPATH%"

REM --- Stop any already-running AI News Radar server first ---------------------
REM A running server holds the old code in memory and its background scheduler
REM keeps writing scan output. Launching again without stopping it would run
REM duplicate instances writing to the same data files. Kill every Python
REM process whose command line belongs to this project before starting fresh.
echo Stopping any existing AI News Radar server...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -match 'abnormal_news_radar' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

REM Give the OS a moment to release the listening port (8765) before rebinding.
timeout /t 2 /nobreak >nul

echo Starting AI News Radar server on http://127.0.0.1:8765/ ...
start "AI News Radar Server" /min python -c "from src.abnormal_news_radar.web import serve; serve(port=8765)"
timeout /t 8 /nobreak >nul
start "" "http://127.0.0.1:8765/"
