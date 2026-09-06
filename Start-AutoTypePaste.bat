@echo off
setlocal

cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :missing_venv

".venv\Scripts\python.exe" -m autotype
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" exit /b 0

echo.
echo AutoTypePaste stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:missing_venv
echo Python virtual environment was not found.
echo Expected: .venv\Scripts\python.exe
pause
exit /b 3
