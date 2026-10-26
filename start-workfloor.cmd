@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3.12 or newer is required. Install it or make it available on PATH.
        exit /b 1
    )
    py -3 app.py %*
) else (
    python app.py %*
)
set "WORKFLOOR_EXIT=%ERRORLEVEL%"
if not "%WORKFLOOR_EXIT%"=="0" (
    echo Workfloor could not start. See the message above and README.md.
    if "%~1"=="" pause
)
exit /b %WORKFLOOR_EXIT%
