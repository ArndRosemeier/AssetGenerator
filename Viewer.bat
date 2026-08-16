@echo off
setlocal
cd /d "%~dp0"
cargo run -p lab --release %*
exit /b %ERRORLEVEL%
