@echo off
title Digital NTTF Auto Solver
cd /d "%~dp0"
echo ===================================================
echo             DIGITAL NTTF AUTO SOLVER
echo ===================================================
echo.
echo Installing requirements...
pip install -r requirements.txt
playwright install chromium
echo.
echo Starting Full Automation...
python main.py
echo.
echo Automation process finished.
pause
