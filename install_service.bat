@echo off
setlocal

cd /d "%~dp0"

echo === TaskPlanner Service Installer ===
echo.
echo This must be run as Administrator.
echo.

:: Resolve Python executable: portable first, then embedded, then system
if exist "python\python.exe" (
    set "PYTHON=python\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Using Python: %PYTHON%
echo.

%PYTHON% -m pip install -q pywin32 2>nul

%PYTHON% service.py install
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install service.
    pause
    exit /b 1
)

%PYTHON% service.py start
if %ERRORLEVEL% NEQ 0 (
    echo Failed to start service.
    pause
    exit /b 1
)

echo.
echo TaskPlanner service installed and started.
echo Web UI available at http://localhost:8200
echo.
pause
