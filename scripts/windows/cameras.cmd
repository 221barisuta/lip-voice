@echo off
rem List camera numbers (an IR camera may appear as a separate number).
set PYTHONUTF8=1
set "LV_ROOT=%~dp0"
powershell -NoProfile -Command "Get-PnpDevice -Class Camera,Image -ErrorAction SilentlyContinue | Select-Object Status,FriendlyName | Format-Table -AutoSize"
"%LV_ROOT%venv\Scripts\lipvoice.exe" --home "%LV_ROOT%data" --profile patient cameras
echo.
pause
