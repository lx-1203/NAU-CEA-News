@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo NJAU-CEA News - Check online architecture and skill updates
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -X utf8 -B scripts\check_updates.py --apply
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" -UpdateOnly
)
if errorlevel 1 echo Online update failed. Existing files were preserved. Check the error above.
pause
