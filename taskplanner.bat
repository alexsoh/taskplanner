@echo off
setlocal

cd /d "%~dp0"

:: Resolve Python executable: portable first, then system
if exist "python\python.exe" (
    set "PYTHON=python\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON=python"
    ) else (
        echo ERROR: Python not found.
        echo Run setup.ps1 first, or install Python and create a venv.
        pause
        exit /b 1
    )
)

echo.
echo === TaskPlanner ===
echo.
echo   Python: %PYTHON%
echo   Web UI: http://localhost:8200
echo   Press Ctrl+C to stop.
echo.

start "" "http://localhost:8200"
%PYTHON% -m uvicorn tp.main:app --host 0.0.0.0 --port 8200
