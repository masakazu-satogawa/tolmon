@echo off
rem Prepare the demo: move saved answers to dataackup and register the fictional patients.
cd /d "%~dp0"
python -X utf8 tools\demo.py reset --seed
echo.
pause
