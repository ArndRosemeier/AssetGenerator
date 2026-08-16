@echo off
setlocal
REM %~dp0 always ends with \, which breaks "--path \"...\"" (\" eats the quote).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PROJECT=%ROOT%"
set "GODOT=%ROOT%\..\..\City\tools\godot\Godot_v4.6-voxel_win64.exe"
if defined GODOT_BIN if exist "%GODOT_BIN%" set "GODOT=%GODOT_BIN%"
if not exist "%GODOT%" (
  echo ERROR: Godot 4.6 not found at:
  echo   %GODOT%
  echo Set GODOT_BIN to your Godot_v4.6*_win64.exe
  exit /b 1
)
python "%ROOT%\..\tools\sync_character_studio_assets.py" --link-only
if errorlevel 1 exit /b 1
if not exist "%ROOT%\..\assets\humans\wardrobe.json" (
  echo Exporting modular human GLBs with MPFB ^(first run, takes a few minutes^)...
  python "%ROOT%\..\tools\sync_character_studio_assets.py"
  if errorlevel 1 exit /b 1
)
REM class_name scripts only resolve after Godot has imported the project once.
if not exist "%PROJECT%\.godot\global_script_class_cache.cfg" (
  echo Importing Godot project ^(first run^)...
  "%GODOT%" --path "%PROJECT%" --headless --import
  if errorlevel 1 exit /b 1
)
echo Launching Character Studio
"%GODOT%" --path "%PROJECT%" %*
exit /b %ERRORLEVEL%
