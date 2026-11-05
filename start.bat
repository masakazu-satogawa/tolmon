@echo off
rem Start the Tolmon server. Keep this window open while you use Tolmon.
cd /d "%~dp0"
python -X utf8 run.py
echo.
echo The server has stopped.
pause
