@echo off
rem Start Tolmon so that tablets on the same Wi-Fi can open it (for device testing).
rem The address for the tablet is printed in this window. Close this window to stop.
cd /d "%~dp0"
python -X utf8 run.py --lan
echo.
echo The server has stopped.
pause
