@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title NJAU-CEA Fixed Voice Pack
echo NJAU-CEA Fixed Voice Pack - XiaoXu and XiaoHe
where powershell.exe >nul 2>nul
if errorlevel 1 goto missing
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable.ps1" %*
set "PACK_EXIT=%ERRORLEVEL%"
if "%PACK_EXIT%"=="0" goto done
echo Voice activation failed. Read the message above and README.md.
goto end
:missing
set "PACK_EXIT=1"
echo Windows PowerShell is required.
goto end
:done
echo Voice pack activation completed.
:end
echo Press any key to close this window.
if not defined NJAU_VOICEPACK_NO_PAUSE pause >nul
exit /b %PACK_EXIT%
