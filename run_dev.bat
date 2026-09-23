@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ==========================================
echo    AI Lab (FastAPI + Next.js) starting...
echo ==========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv was not found.
    pause
    exit /b 1
)

where npm > nul 2> nul
if errorlevel 1 (
    echo [ERROR] Node.js is not installed. Install the LTS version from https://nodejs.org
    pause
    exit /b 1
)

start "AI Lab API :8000" cmd /k venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
start "Streamlit (legacy) :8501" cmd /k venv\Scripts\python.exe -m streamlit run app.py --server.headless true

cd web
if not exist "node_modules" call npm install
if not exist ".env.local" copy .env.example .env.local > nul
npm run dev
