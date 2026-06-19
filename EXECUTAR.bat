@echo off
setlocal
title AccessView - Executar
cd /d "%~dp0"

echo ==================================
echo           ACCESSVIEW
echo ==================================
echo.

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado.
    echo Preparando automaticamente...
    echo.
    call "%~dp0PREPARAR-AMBIENTE.bat" --no-pause
    if errorlevel 1 goto :prepare_error
)

if not exist "%~dp0app.py" (
    echo ERRO: O arquivo app.py nao foi encontrado.
    echo Verifique se o BAT esta na pasta principal do projeto.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0config.json" (
    echo ERRO: O arquivo config.json nao foi encontrado.
    echo Copie config.example.json para config.json e configure o servidor.
    echo.
    pause
    exit /b 1
)

echo Python utilizado:
"%~dp0venv\Scripts\python.exe" -c "import sys; print(sys.executable)"
echo.

echo Verificando dependencias...
"%~dp0venv\Scripts\python.exe" -c "import smbclient; from PIL import Image"

if errorlevel 1 (
    echo Dependencias ausentes ou incompletas.
    echo Tentando reparar automaticamente...
    echo.
    call "%~dp0PREPARAR-AMBIENTE.bat" --no-pause
    if errorlevel 1 goto :prepare_error

    "%~dp0venv\Scripts\python.exe" -c "import smbclient; from PIL import Image"
    if errorlevel 1 goto :dependency_error
)

echo Dependencias verificadas.
echo.
echo Iniciando o aplicativo...
"%~dp0venv\Scripts\python.exe" "%~dp0app.py"
set "EXITCODE=%ERRORLEVEL%"

echo.
echo Processo finalizado com codigo: %EXITCODE%
pause
exit /b %EXITCODE%

:prepare_error
echo.
echo ERRO: Nao foi possivel preparar o ambiente virtual.
echo Execute PREPARAR-AMBIENTE.bat e confira a mensagem apresentada.
echo.
pause
exit /b 1

:dependency_error
echo.
echo ERRO: O modulo smbclient ainda nao esta disponivel.
echo O pacote responsavel por esse modulo e o smbprotocol.
echo.
echo Tente executar manualmente:
echo venv\Scripts\python.exe -m pip install smbprotocol Pillow
echo.
pause
exit /b 1
