@echo off
rem pt.bat : run a panicCreationKit tool with the portable Python (runtime\python)
rem   pt <tool> [args...]   e.g.  pt mkscene samples\layer1\scene4.toml
rem   pt                    lists the tools
setlocal
set "PY=%~dp0runtime\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0tools\pt.py" %*
exit /b %ERRORLEVEL%
