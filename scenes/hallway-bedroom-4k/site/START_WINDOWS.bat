@echo off
cd /d "%~dp0"
py -3 serve.py %* || python serve.py %*
pause
