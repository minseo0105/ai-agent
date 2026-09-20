@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ==========================================
echo        AI Workbench starting...
echo ==========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv was not found.
    echo.
    echo Please make sure run.bat is inside your ai-agent folder.
    echo Expected: venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

venv\Scripts\python.exe -m streamlit run app.py

echo.
echo Streamlit has stopped.
pause
