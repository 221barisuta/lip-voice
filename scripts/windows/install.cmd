@echo off
rem LipVoice installer launcher. Runs the PowerShell script without changing system policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1" %*
echo.
pause
