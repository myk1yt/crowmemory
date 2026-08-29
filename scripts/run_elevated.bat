@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_crow_task.ps1" -CrowDir "%~dp0.."
pause
