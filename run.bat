@echo off
REM TruthLens - one-click start: creates .venv on first run, installs packages, starts the app.
cd /d "%~dp0"
if not exist "data\evidence_rules.csv" (echo [ERROR] data\evidence_rules.csv is missing. & pause & exit /b 1)
if not exist "model\fake_news_model.pkl" (echo [ERROR] model\ folder is missing the .pkl files. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv || (echo [ERROR] Python not found. Install it and tick "Add python.exe to PATH". & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo [ERROR] pip install failed. & pause & exit /b 1)
)
start "" /b cmd /c "timeout /t 6 >nul & start http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py
pause
