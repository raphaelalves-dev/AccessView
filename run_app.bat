@echo off
setlocal
cd /d "%~dp0"

call "%~dp0EXECUTAR.bat"
exit /b %ERRORLEVEL%
