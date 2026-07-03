@echo off
REM ============================================================================
REM  Vision Zero Houston - street-imagery feature extraction (one-click)
REM
REM  What this does, in order:
REM    1. Installs uv (a tiny Python manager) if missing - no admin needed
REM    2. Installs Python 3.12 + all packages into a local .venv-gpu folder
REM    3. Asks for the Mapillary access token on first run (saved locally)
REM    4. Runs the full extraction: plan -> download -> GPU inference -> output
REM
REM  Safe to re-run: every stage resumes where it left off.
REM  Output when finished: data\processed\houston_streetview_features.parquet
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo.
echo === Vision Zero street-imagery extraction ===
echo.

REM -- 1. ensure uv ------------------------------------------------------------
where uv >nul 2>nul
if errorlevel 1 (
    echo [setup] Installing uv (Python manager)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
    echo [error] uv did not install. Check your internet connection and rerun.
    pause & exit /b 1
)

REM -- 2. python + packages (local to this folder) ------------------------------
if not exist .venv-gpu (
    echo [setup] Creating Python 3.12 environment...
    uv venv --python 3.12 .venv-gpu || (echo [error] venv failed & pause & exit /b 1)
)
echo [setup] Installing packages (first run downloads ~4 GB incl. CUDA torch)...
uv pip install --python .venv-gpu -r requirements-extraction.txt || (
    echo [error] package install failed & pause & exit /b 1)

REM -- 3. token ------------------------------------------------------------------
if not exist data\external\.mapillary_token (
    echo.
    echo [token] Paste the Mapillary ACCESS TOKEN (starts with MLY^|...)
    echo         Dashboard ^> Developers ^> your app ^> Access Token ^> View
    set /p MTOKEN="token: "
    if not exist data\external mkdir data\external
    <nul set /p=!MTOKEN!> data\external\.mapillary_token
    echo [token] saved to data\external\.mapillary_token (never committed)
)

REM -- 4. run ---------------------------------------------------------------------
echo.
echo [run] Starting extraction (arterials + collectors scope).
echo       Stages resume automatically if interrupted. Keep the PC awake.
echo.
.venv-gpu\Scripts\python.exe src\extract_streetview_features.py --stage all --scope arterials
echo.
echo === finished ===
echo Output: data\processed\houston_streetview_features.parquet
echo Next: commit and push that file (or copy it back), and the model refit
echo runs on the other machine.
pause
