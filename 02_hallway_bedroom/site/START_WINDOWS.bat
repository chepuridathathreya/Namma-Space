@echo off
cd /d "%~dp0"
start "" "http://localhost:8764/index.html"
py -3 -m http.server 8764 || python -m http.server 8764
