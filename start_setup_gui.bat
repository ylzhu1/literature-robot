@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo Python was not found in PATH.
  echo Please install Python 3.10+ or edit run_setup_gui.ps1 to use a specific Python executable.
  pause
  exit /b 1
)

python -m literature_agent.gui
if %errorlevel% neq 0 (
  echo.
  echo Literature Agent Setup failed to start.
  pause
)
