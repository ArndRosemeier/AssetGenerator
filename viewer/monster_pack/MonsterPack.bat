@echo off
setlocal
REM The library viewer replaced the monster-only window.
call "%~dp0..\lab\Lab.bat" %*
exit /b %ERRORLEVEL%
