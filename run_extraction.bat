@echo off
REM ============================================================================
REM  Vision Zero Houston - street-imagery feature extraction - one click
REM
REM  1. Installs uv - a tiny Python manager - if missing. No admin needed.
REM  2. Installs Python 3.12 + all packages into a local .venv-gpu folder.
REM  3. Asks for the Mapillary access token on first run - saved locally.
REM  4. Runs the full extraction: plan, download, GPU inference, output.
REM
REM  Safe to re-run: every stage resumes where it left off.
REM  Output when finished: data\processed\houston_streetview_features.parquet
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo.
echo === Vision Zero street-imagery extraction ===
echo.

REM ---- 1. ensure uv ----------------------------------------------------------
where uv >nul 2>nul
if %errorlevel%==0 goto haveuv
echo [setup] Installing uv - the Python manager...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if %errorlevel%==0 goto haveuv
echo [error] uv did not install. Check the internet connection and re-run.
pause
exit /b 1
:haveuv

REM ---- 2. python + packages - local to this folder ---------------------------
if exist .venv-gpu goto havevenv
echo [setup] Creating the Python 3.12 environment...
uv venv --python 3.12 .venv-gpu
if errorlevel 1 goto fail
:havevenv
echo [setup] Installing packages. First run downloads about 4 GB incl. CUDA torch...
uv pip install --python .venv-gpu --index-strategy unsafe-best-match -r requirements-extraction.txt
if errorlevel 1 goto fail

REM ---- 3. token ----------------------------------------------------------------
if exist data\external\.mapillary_token goto havetoken
echo.
echo [token] Paste the Mapillary ACCESS TOKEN. It starts with MLY then a vertical bar.
echo         Find it: Mapillary Dashboard - Developers - your app - Access Token - View
set /p MTOKEN=token:
if not exist data\external mkdir data\external
<nul set /p=!MTOKEN!> data\external\.mapillary_token
echo [token] Saved to data\external\.mapillary_token - never committed to git.
:havetoken

REM ---- 4. run --------------------------------------------------------------------
echo.
echo [run] Starting extraction - arterials + collectors scope.
echo       Stages resume automatically if interrupted. Keep the PC awake.
echo.
.venv-gpu\Scripts\python.exe src\extract_streetview_features.py --stage all --scope arterials
echo.
echo === finished ===
echo Output: data\processed\houston_streetview_features.parquet
echo Next: commit and push that file - the model refit runs on the other machine.
pause
exit /b 0

:fail
echo [error] Setup failed - see the message above, then re-run this file.
pause
exit /b 1
