@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PLAYWRIGHT_BROWSERS_PATH=%~dp0runtime\browsers
set PATH=%~dp0.tools\gh\bin;%PATH%
echo NAU CEA News - First installation and two-voice check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 goto failed
"%~dp0.venv\Scripts\python.exe" -m pipeline.desktop
if errorlevel 1 goto failed

goto end
:failed
echo A step failed. Keep this window and check the printed error and logs.
:end
pause
