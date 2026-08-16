@echo off
setlocal
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "ROOT=%HERE%\..\.."
cd /d "%ROOT%"
if not exist "assets\monsters\quaternius\big\Orc.glb" (
  echo Fetching Quaternius Ultimate Monsters...
  python tools\fetch_quaternius_monsters.py
  if errorlevel 1 exit /b 1
)
cargo run -p monster_pack --release %*
exit /b %ERRORLEVEL%
