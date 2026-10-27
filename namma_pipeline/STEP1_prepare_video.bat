@echo off
setlocal
cd /d "%~dp0"
title NammaSpace STEP 1 - prepare video
where python >/dev/null 2>&1 && (set "PY=python") || (set "PY=py -3")
%PY% scripts\step1_prepare.py %*
echo.
pause
