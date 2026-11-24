@echo off
cd /d "%~dp0"
start "" "http://localhost:8766/index.html"
py -3 -m http.server 8766 || python -m http.server 8766
