@echo off
cd /d "%~dp0"
echo Launching native Brush 3D Gaussian Splat viewer on RTX 5070...
"tools\brush\brush_app.exe" --with-viewer "scan\splat\apartment_splat.ply"
