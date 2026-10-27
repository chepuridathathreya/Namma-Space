@echo off
cd /d "%~dp0"
start "" "http://localhost:8762/index.html"
py -3 -m http.server 8762 || python -m http.server 8762
