@echo off
setlocal EnableExtensions
title AccessView - Gerar Pacote de Atualizacao
cd /d "%~dp0"

set "PYTHON=%~dp0venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    call "%~dp0PREPARAR-AMBIENTE.bat" --no-pause
    if errorlevel 1 goto :error
)

echo Gerando os executaveis da versao atual...
call "%~dp0build_exe.bat" --no-pause
if errorlevel 1 goto :error

if not exist "%~dp0dist\AccessView\AccessViewUpdater.exe" (
    echo ERRO: AccessViewUpdater.exe nao foi encontrado.
    goto :error
)

echo Gerando pacote ZIP de atualizacao...
"%PYTHON%" "%~dp0create_update_package.py" ^
  --source "%~dp0dist\AccessView" ^
  --output "%~dp0ATUALIZACOES" ^
  --app-source "%~dp0app.py" ^
  --minimum-version "0.10.0" ^
  --version-subdir

if errorlevel 1 goto :error

echo.
echo Pacote de atualizacao criado na pasta:
echo %~dp0ATUALIZACOES
echo.
if /i not "%~1"=="--no-pause" pause
exit /b 0

:error
echo.
echo Falha ao gerar o pacote de atualizacao.
if /i not "%~1"=="--no-pause" pause
exit /b 1
