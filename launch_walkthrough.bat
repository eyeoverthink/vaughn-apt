@echo off
cd /d "%~dp0"
echo Starting local server for Apartment 3D Walkthrough...
start "" http://localhost:8765/web/
python -m http.server 8765
