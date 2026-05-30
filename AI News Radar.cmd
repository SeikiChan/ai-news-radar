@echo off
cd /d "%~dp0"
set "PYTHONPATH=%CD%;%PYTHONPATH%"
start "AI News Radar Server" /min python -c "from src.abnormal_news_radar.web import serve; serve(port=8765)"
timeout /t 8 /nobreak >nul
start "" "http://127.0.0.1:8765/"
