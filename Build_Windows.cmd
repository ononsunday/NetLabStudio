@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm NetLabStudio.spec
if errorlevel 1 (
    echo Build failed. Review the output above.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\package_release.py
if errorlevel 1 exit /b 1
echo Built: dist\NetLabStudio\NetLabStudio.exe and releases\
pause
