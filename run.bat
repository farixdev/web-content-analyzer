@echo off
cd /d "%~dp0"
title Mindcob Web Content Analyzer

echo ========================================================
echo        Mindcob Web Content Analyzer & Intelligence
echo ========================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo Starting Web Dashboard on http://127.0.0.1:5050 ...
    py app.py %*
    pause
    goto :end
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo Starting Web Dashboard on http://127.0.0.1:5050 ...
    python app.py %*
    pause
    goto :end
)

echo [ERROR] Python was not found on your system!
echo Please install Python 3 from https://www.python.org/
echo.
pause
exit /b 1

:end
