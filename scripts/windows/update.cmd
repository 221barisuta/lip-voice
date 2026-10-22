@echo off
rem Update LipVoice code only (small). Put this file and lipvoice-*.whl in the same folder, then double-click.
set "LV_ROOT=C:\LipVoice\"
if not exist "%LV_ROOT%venv\Scripts\python.exe" (
  echo LipVoice is not installed in %LV_ROOT%
  pause
  exit /b 1
)
set FOUND=0
for %%f in ("%~dp0lipvoice-*.whl") do (
  set FOUND=1
  "%LV_ROOT%venv\Scripts\python.exe" -m pip install --no-index --no-deps --force-reinstall "%%~ff"
)
rem also refresh the helper scripts (run / bench / cameras / train)
for %%c in (run.cmd bench.cmd cameras.cmd train.cmd) do if exist "%~dp0%%c" copy /Y "%~dp0%%c" "%LV_ROOT%%%c" >nul
if "%FOUND%"=="0" echo No lipvoice-*.whl next to update.cmd
"%LV_ROOT%venv\Scripts\lipvoice.exe" --version 2>nul
echo.
echo Done. Please start LipVoice again.
pause
