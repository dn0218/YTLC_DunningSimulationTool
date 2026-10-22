@echo off
REM ============================================================
REM  probe_build.bat - build the diagnostic probe exe.
REM
REM  IMPORTANT: builds FROM THE SPEC FILE so that
REM  collect_submodules('cryptography') actually takes effect.
REM  (When PyInstaller is given a .py script it generates its
REM  own spec and IGNORES any existing probe_frozen.spec - that
REM  is why the crypto submodules were missing earlier.)
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [ERROR] .venv\Scripts\python.exe not found.
    exit /b 1
)

"%PY%" -m PyInstaller --noconfirm probe_frozen.spec
exit /b %ERRORLEVEL%
