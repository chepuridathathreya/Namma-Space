@echo off
setlocal
cd /d "%~dp0"
title NammaSpace STEP 3 - finish and open website
where python >/dev/null 2>&1 && (set "PY=python") || (set "PY=py -3")
%PY% scripts\step3_finish.py %*
echo.
pause
