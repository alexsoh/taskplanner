@echo off
REM Windows setup script runner — runs setup.ps1

echo Running TaskPlanner setup...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"

if errorlevel 1 (
    echo.
    echo Setup failed with error code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo Setup completed successfully!
pause
