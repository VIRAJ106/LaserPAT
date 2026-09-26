@echo off
REM LaserPAT - FSOC Virtual Camera Tracking System
REM SIH 2026 Problem Statement #22169
REM 
REM This launcher script starts the LaserPAT application
REM 
REM Prerequisites:
REM - Python 3.10+ with all dependencies installed (see requirements in pyproject.toml)
REM - Run: pip install -e .

echo ======================================
echo   LaserPAT - FSOC Tracking System
echo   SIH 2026 - Problem Statement #22169
echo ======================================
echo.
echo Starting LaserPAT GUI...
echo.

REM Set PYTHONPATH to current directory
set PYTHONPATH=%~dp0

REM Launch the main application
python "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo ERROR: LaserPAT failed to start
    echo.
    echo Please ensure all dependencies are installed:
    echo   pip install -e .
    echo.
    pause
)
