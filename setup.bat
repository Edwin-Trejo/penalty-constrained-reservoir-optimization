@echo off
echo ============================================================
echo  Reservoir Release Optimizer - First-Time Setup
echo ============================================================
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8 or higher
    echo        from https://www.python.org/downloads/
    echo        Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv myenv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo Activating virtual environment...
call myenv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Setup complete!
echo.
echo  To run the app:
echo    1. Double-click run.bat
echo    OR
echo    1. Open a terminal in this folder
echo    2. Run:  myenv\Scripts\activate
echo    3. Run:  streamlit run app.py
echo ============================================================
pause
