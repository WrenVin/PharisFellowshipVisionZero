@echo off
setlocal
cd /d %~dp0

if exist .venv-gpu\Scripts\python.exe goto run
echo The GPU environment .venv-gpu was not found.
echo Run run_extraction.bat first so the environment exists.
pause
exit /b 1

:run
echo Rendering the visual audit sample. This takes under a minute on the GPU.
.venv-gpu\Scripts\python.exe src\visualize_extraction_sample.py %*
echo.
echo Done. The gallery opened in your browser. Files are in reports\extraction_gallery
pause
