@echo off
rem Train the recognition model on this PC (DTW only: no torch needed, takes seconds). Close LipVoice first.
set PYTHONUTF8=1
set "LV_ROOT=%~dp0"
"%LV_ROOT%venv\Scripts\lipvoice.exe" --home "%LV_ROOT%data" --profile patient train --no-cnn
echo.
echo Done. Start LipVoice again, then open the "recognition (test)" tab.
pause
