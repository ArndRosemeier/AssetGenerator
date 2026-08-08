@echo off
REM Export Character Studio humans (MPFB body + face morphs + MakeHuman eyes).
setlocal
set "ROOT=%~dp0..\.."
if not defined CITY_ROOT set "CITY_ROOT=%ROOT%\..\City"
set "BLENDER=%CITY_ROOT%\tools\vendor\blender\blender-4.2.9-windows-x64\blender.exe"
set "SCRIPT=%ROOT%\tools\character_studio\blender_export_humans.py"

if not exist "%BLENDER%" (
  echo ERROR: vendored Blender 4.2 not found at:
  echo   %BLENDER%
  echo Set CITY_ROOT to a City checkout that ran: python tools\download_blender_mpfb.py ^&^& python tools\extract_vendor.py
  exit /b 2
)

echo Exporting Character Studio humans via "%BLENDER%"
"%BLENDER%" --background --python "%SCRIPT%"
exit /b %ERRORLEVEL%
