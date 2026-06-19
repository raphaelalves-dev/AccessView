@echo off
setlocal
title AccessView - Preparar Ambiente
cd /d "%~dp0"

set "NO_PAUSE=0"
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

echo ==================================
echo        PREPARAR ACCESSVIEW
echo ==================================
echo.

if not exist "%~dp0requirements.txt" (
    echo ERRO: O arquivo requirements.txt nao foi encontrado.
    echo.
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

if not exist "%~dp0config.json" if exist "%~dp0config.example.json" (
    copy /y "%~dp0config.example.json" "%~dp0config.json" >nul
    echo config.json criado a partir de config.example.json.
    echo Revise o IP e os compartilhamentos antes de executar o aplicativo.
    echo.
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%~dp0venv"
    ) else (
        python -m venv "%~dp0venv"
    )

    if errorlevel 1 (
        echo.
        echo ERRO: Nao foi possivel criar a venv.
        echo Confirme se o Python esta instalado com o Python Launcher.
        echo.
        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
) else (
    echo Ambiente virtual ja existente.
)

echo.
echo Atualizando o pip...
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip

if errorlevel 1 goto :error

echo.
echo Instalando dependencias...
"%~dp0venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 goto :error

echo.
echo Ambiente preparado com sucesso.
echo Agora execute: EXECUTAR.bat
echo.
if "%NO_PAUSE%"=="0" pause
exit /b 0

:error
echo.
echo ERRO: Nao foi possivel instalar as dependencias.
echo Verifique a conexao com a internet e tente novamente.
echo.
if "%NO_PAUSE%"=="0" pause
exit /b 1
