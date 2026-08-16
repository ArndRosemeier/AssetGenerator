@echo off
setlocal
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "ROOT=%HERE%\..\.."
cd /d "%ROOT%"
cargo run -p lab --release %*
exit /b %ERRORLEVEL%
