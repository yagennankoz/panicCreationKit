@echo off
rem panicCreationKit setup: downloads Python (portable), Python packages, ffmpeg, run68x, HAS060X, HLK evolution, panic.x
rem Options: --samples (also prepare sample materials)  --force (download again)  --check (only check)
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup\bootstrap.ps1" %*
set RC=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %RC%
