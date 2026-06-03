@echo off
echo Starting Reservoir Release Optimizer...

REM Activate virtual environment if it exists
if exist myenv\Scripts\activate.bat (
    call myenv\Scripts\activate.bat
) else (
    echo Warning: Virtual environment not found. Trying system Python.
    echo          Run setup.bat first if you see import errors.
)

streamlit run app.py
pause
