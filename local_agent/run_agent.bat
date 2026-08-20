@echo off
title Digital NTTF Local Visible Chrome Agent
cd /d "%~dp0"

echo ======================================================================
echo                 DIGITAL NTTF LOCAL VISIBLE CHROME AGENT
echo ======================================================================
echo.
echo 1. Checking Python dependencies...
python -m pip install -r requirements.txt
python -m playwright install chromium

echo.
echo ----------------------------------------------------------------------
echo Enter the web server URL:
echo.
echo Example for Render Cloud deployment:
echo https://your-app.onrender.com
echo.
echo Example for Local server:
echo http://localhost:3000
echo ----------------------------------------------------------------------
set /p SERVER_URL="Server URL (Press Enter for http://localhost:3000): "
if "%SERVER_URL%"=="" set SERVER_URL=http://localhost:3000

echo.
echo Starting Local Agent connected to %SERVER_URL%...
echo When you click START AUTOMATION in the web UI, Google Chrome will appear on this screen.
echo.

python agent.py --server "%SERVER_URL%"

pause
