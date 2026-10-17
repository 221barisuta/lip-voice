@echo off
rem Start LipVoice. Data and profile are explicit so that no other folder is created by mistake.
set PYTHONUTF8=1
set "LV_ROOT=%~dp0"
"%LV_ROOT%venv\Scripts\lipvoice.exe" --home "%LV_ROOT%data" --profile patient run --open
if errorlevel 1 (
  echo.
  echo LipVoice stopped with an error. Please take a photo of this window.
  pause
)
