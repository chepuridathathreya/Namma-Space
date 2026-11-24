@echo off
setlocal
cd /d "%~dp0"
title NammaSpace STEP 4 - tag places
where python >nul 2>&1 && (set "PY=python") || (set "PY=py -3")
%PY% ..\..\src\pipeline\step4_tag_places.py %*
echo.
pause
