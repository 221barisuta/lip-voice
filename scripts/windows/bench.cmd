@echo off
rem Day 0 check: face detection rate, fps, noise and SNR (about 40 seconds).
set PYTHONUTF8=1
set "LV_ROOT=%~dp0"
"%LV_ROOT%venv\Scripts\lipvoice.exe" --home "%LV_ROOT%data" --profile patient bench
echo.
pause
