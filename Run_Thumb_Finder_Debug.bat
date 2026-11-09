@echo off
setlocal
cd /d "%~dp0"
title Thumb Finder - Local Debug

set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
  set "PY_EXE=%CD%\.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=py"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_EXE=python"
  )
)

if not defined PY_EXE (
  echo Python was not found. Make py or python available in PATH.
  pause
  exit /b 1
)

echo Starting Thumb Finder using:
"%PY_EXE%" --version
"%PY_EXE%" -c "import PySide6, requests; print('Core dependencies: OK')" >nul 2>nul
if errorlevel 1 (
  echo Required core packages are missing from this Python environment.
  echo Install them once using this command:
  echo "%PY_EXE%" -m pip install -r requirements.txt
  pause
  exit /b 1
)

set PYTHONFAULTHANDLER=1
"%PY_EXE%" run_app.py
if errorlevel 1 (
  echo.
  echo Thumb Finder exited with an error. See:
  echo %USERPROFILE%\.thumb_finder\logs\thumb_finder.log
  pause
)
exit /b 0
