@echo off
cd /d "%~dp0"
echo Starting vaughn-apt Spatial Home OS Server on http://localhost:8765 ...
start "" http://localhost:8765/web/home_os.html
python scripts\home_os_server.py 8765
