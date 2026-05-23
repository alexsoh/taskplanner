@echo off
setlocal

cd /d "%~dp0"

echo === TaskPlanner Service Uninstaller ===
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

%PYTHON% service.py stop
%PYTHON% service.py remove

echo.
echo TaskPlanner service removed.
echo.
pause
