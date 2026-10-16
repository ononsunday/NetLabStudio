@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pytest -q
set "NETLAB_EXIT=%errorlevel%"
pause
exit /b %NETLAB_EXIT%
