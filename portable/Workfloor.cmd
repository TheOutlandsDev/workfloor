@echo off
setlocal
"%~dp0runtime\python.exe" -I -B -X utf8 "%~dp0launch.py" %*
set "workfloor_result=%errorlevel%"
if "%workfloor_result%"=="0" exit /b 0
echo.
echo Workfloor could not complete. Preserve your data and read START-HERE.txt.
if "%~1"=="" pause
exit /b %workfloor_result%
