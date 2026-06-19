@echo off
setlocal EnableExtensions
title AccessView - Gerar EXE
cd /d "%~dp0"

set "APP_NAME=AccessView"
set "ICON_FILE=AccessView.ico"
set "LOGO_FILE=AccessView.png"
set "PYTHON=%~dp0venv\Scripts\python.exe"

echo ==================================
echo       ACCESSVIEW - GERAR EXE
echo ==================================
echo.

if not exist "%PYTHON%" (
    echo Ambiente virtual nao encontrado.
    echo Preparando automaticamente...
    echo.
    call "%~dp0PREPARAR-AMBIENTE.bat" --no-pause
    if errorlevel 1 goto :error
)

echo Verificando dependencias de compilacao...
"%PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :error
echo.

if not exist "%~dp0app.py" goto :missing_app
if not exist "%~dp0updater.py" goto :missing_updater
if not exist "%~dp0%ICON_FILE%" goto :missing_icon
if not exist "%~dp0%LOGO_FILE%" goto :missing_logo

echo Limpando compilacoes anteriores...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo Gerando executavel...
"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name "%APP_NAME%" ^
  --icon "%~dp0%ICON_FILE%" ^
  --add-data "%~dp0%ICON_FILE%;." ^
  --add-data "%~dp0%LOGO_FILE%;." ^
  --collect-all smbprotocol ^
  --collect-all spnego ^
  "%~dp0app.py"

if errorlevel 1 goto :error

"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --uac-admin ^
  --name "AccessViewUpdater" ^
  --icon "%~dp0%ICON_FILE%" ^
  --distpath "%~dp0build\updater-dist" ^
  --workpath "%~dp0build\updater-work" ^
  --specpath "%~dp0build\updater-spec" ^
  "%~dp0updater.py"

if errorlevel 1 goto :error

if not exist "build\updater-dist\AccessViewUpdater.exe" goto :missing_updater_exe
copy /y "build\updater-dist\AccessViewUpdater.exe" "dist\%APP_NAME%\AccessViewUpdater.exe" >nul
copy /y "%ICON_FILE%" "dist\%APP_NAME%\%ICON_FILE%" >nul
copy /y "%LOGO_FILE%" "dist\%APP_NAME%\%LOGO_FILE%" >nul
if exist "config.json" copy /y "config.json" "dist\%APP_NAME%\config.json" >nul

echo.
echo EXE gerado com sucesso:
echo dist\%APP_NAME%\%APP_NAME%.exe
echo.
if /i not "%~1"=="--no-pause" pause
exit /b 0

:missing_app
echo ERRO: app.py nao encontrado.
goto :error

:missing_updater
echo ERRO: updater.py nao encontrado.
goto :error

:missing_updater_exe
echo ERRO: AccessViewUpdater.exe nao foi gerado.
goto :error

:missing_icon
echo ERRO: %ICON_FILE% nao encontrado.
goto :error

:missing_logo
echo ERRO: %LOGO_FILE% nao encontrado.
goto :error

:error
echo.
echo Falha ao gerar o executavel.
if /i not "%~1"=="--no-pause" pause
exit /b 1
