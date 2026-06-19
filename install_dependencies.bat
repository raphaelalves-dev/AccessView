@echo off
setlocal
cd /d "%~dp0"

call "%~dp0PREPARAR-AMBIENTE.bat"
exit /b %ERRORLEVEL%
