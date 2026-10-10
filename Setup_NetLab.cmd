@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.13 -m venv .venv
    if errorlevel 1 py -3.12 -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo Install Python 3.13 or 3.12 from python.org with the Python launcher enabled.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Read the error above.
    pause
    exit /b 1
)
echo Environment ready. Double-click Launch_NetLab.cmd.
pause
