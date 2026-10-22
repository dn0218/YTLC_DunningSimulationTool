@echo off
REM ============================================================
REM  build_exe.bat - package the Dunning Simulation Tool with
REM  PyInstaller into a single .exe (spec 11).
REM
REM  IMPORTANT: builds with the project venv (.venv), NOT the
REM  system python - the machine has several interpreters and
REM  oracledb/paramiko must come from the venv or the exe will
REM  start with "No Oracle driver installed".
REM
REM  IMPORTANT: builds FROM THE SPEC FILE so that
REM  collect_submodules('cryptography') actually takes effect.
REM  (When PyInstaller is given a .py script it generates its
REM  own spec and IGNORES DunningSimulationTool.spec - that is
REM  exactly the DPY-3016 trap the probe build already hit.)
REM
REM  Output: dist\DunningSimulationTool.exe
REM  config.json is NOT bundled - it must sit next to the exe.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Create it first:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    goto :error
)
set "PY=.venv\Scripts\python.exe"

echo [1/5] Checking Python environment...
"%PY%" --version || goto :error

echo [2/5] Installing dependencies into venv...
"%PY%" -m pip install -r requirements.txt || goto :error

echo [3/5] Verifying Oracle driver imports in the build env...
"%PY%" -c "import oracledb; print('oracledb', oracledb.__version__, 'OK')" || goto :error
"%PY%" -c "import paramiko, requests; print('paramiko/requests OK')" || goto :error

echo [4/5] Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist\DunningSimulationTool.exe del /q dist\DunningSimulationTool.exe

echo [5/5] Running PyInstaller (spec mode)...
"%PY%" -m PyInstaller --noconfirm DunningSimulationTool.spec
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Build succeeded: dist\DunningSimulationTool.exe
echo  Copy config.json next to the exe before running it.
echo ============================================================
if not exist dist\config.json copy /y config.template.json dist\config.json
goto :eof

:error
echo.
echo BUILD FAILED - see messages above.
exit /b 1
