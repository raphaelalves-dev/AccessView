@echo off
setlocal EnableExtensions
title AccessView - Gerar EXE e Instalador
cd /d "%~dp0"

set "APP_NAME=AccessView"
set "PYTHON=%~dp0venv\Scripts\python.exe"
set "REQUIREMENTS=%~dp0requirements.txt"
set "LOG_FILE=%~dp0BUILD-RELEASE.log"
set "ISCC="
set "EXIT_CODE=1"

> "%LOG_FILE%" echo AccessView - Build iniciado em %date% %time%

echo ==========================================
echo    ACCESSVIEW - GERAR RELEASE COMPLETA
echo ==========================================
echo.
echo Pasta do projeto:
echo %~dp0
echo.
echo Um log sera salvo em:
echo %LOG_FILE%
echo.

call :CHECK_FILE "%~dp0app.py"
if errorlevel 1 goto :END

call :CHECK_FILE "%~dp0updater.py"
if errorlevel 1 goto :END

call :CHECK_FILE "%~dp0create_update_package.py"
if errorlevel 1 goto :END

call :CHECK_FILE "%~dp0AccessView.ico"
if errorlevel 1 goto :END

call :CHECK_FILE "%~dp0AccessView.png"
if errorlevel 1 goto :END

call :CHECK_FILE "%REQUIREMENTS%"
if errorlevel 1 goto :END

call :CHECK_FILE "%~dp0AccessView.iss"
if errorlevel 1 goto :END

if not exist "%PYTHON%" (
    echo [1/6] Criando ambiente virtual...
    >> "%LOG_FILE%" echo Criando ambiente virtual...

    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%~dp0venv" >> "%LOG_FILE%" 2>&1
    ) else (
        where python >nul 2>&1
        if errorlevel 1 (
            echo ERRO: Python nao foi encontrado.
            >> "%LOG_FILE%" echo ERRO: Python nao foi encontrado.
            echo Instale o Python 3.11 ou superior marcando Add Python to PATH.
            goto :END
        )
        python -m venv "%~dp0venv" >> "%LOG_FILE%" 2>&1
    )

    if errorlevel 1 (
        echo ERRO: Nao foi possivel criar a venv.
        goto :END
    )
) else (
    echo [1/6] Ambiente virtual encontrado.
)

echo [2/6] Instalando dependencias...
"%PYTHON%" -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERRO: Falha ao atualizar o pip.
    goto :END
)

"%PYTHON%" -m pip install -r "%REQUIREMENTS%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERRO: Falha ao instalar as dependencias.
    goto :END
)

echo [3/6] Limpando compilacoes anteriores...
if exist "%~dp0build" rmdir /s /q "%~dp0build" >> "%LOG_FILE%" 2>&1
if exist "%~dp0dist" rmdir /s /q "%~dp0dist" >> "%LOG_FILE%" 2>&1
if exist "%~dp0output" rmdir /s /q "%~dp0output" >> "%LOG_FILE%" 2>&1
if exist "%~dp0%APP_NAME%.spec" del /q "%~dp0%APP_NAME%.spec" >> "%LOG_FILE%" 2>&1

echo [4/6] Gerando os executaveis...
"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name "%APP_NAME%" ^
  --icon "%~dp0AccessView.ico" ^
  --add-data "%~dp0AccessView.ico;." ^
  --add-data "%~dp0AccessView.png;." ^
  --collect-all smbprotocol ^
  --collect-all spnego ^
  "%~dp0app.py" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERRO: O PyInstaller nao conseguiu gerar o executavel.
    goto :END
)

if not exist "%~dp0dist\%APP_NAME%\%APP_NAME%.exe" (
    echo ERRO: O EXE nao foi encontrado depois da compilacao.
    goto :END
)

"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --uac-admin ^
  --name "AccessViewUpdater" ^
  --icon "%~dp0AccessView.ico" ^
  --distpath "%~dp0build\updater-dist" ^
  --workpath "%~dp0build\updater-work" ^
  --specpath "%~dp0build\updater-spec" ^
  "%~dp0updater.py" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERRO: O PyInstaller nao conseguiu gerar o atualizador.
    goto :END
)

if not exist "%~dp0build\updater-dist\AccessViewUpdater.exe" (
    echo ERRO: AccessViewUpdater.exe nao foi encontrado.
    goto :END
)

copy /y "%~dp0build\updater-dist\AccessViewUpdater.exe" "%~dp0dist\%APP_NAME%\AccessViewUpdater.exe" >> "%LOG_FILE%" 2>&1
if exist "%~dp0config.json" copy /y "%~dp0config.json" "%~dp0dist\%APP_NAME%\config.json" >> "%LOG_FILE%" 2>&1
copy /y "%~dp0AccessView.ico" "%~dp0dist\%APP_NAME%\AccessView.ico" >> "%LOG_FILE%" 2>&1
copy /y "%~dp0AccessView.png" "%~dp0dist\%APP_NAME%\AccessView.png" >> "%LOG_FILE%" 2>&1

call :FIND_INNO
if not defined ISCC (
    echo ERRO: Inno Setup nao foi encontrado.
    echo Instale com:
    echo winget install --id JRSoftware.InnoSetup -e
    >> "%LOG_FILE%" echo ERRO: ISCC.exe nao encontrado.
    goto :END
)

echo [5/6] Gerando pacote de atualizacao...
"%PYTHON%" "%~dp0create_update_package.py" ^
  --source "%~dp0dist\%APP_NAME%" ^
  --output "%~dp0output" ^
  --app-source "%~dp0app.py" ^
  --minimum-version "0.10.0" ^
  --overwrite >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERRO: Nao foi possivel gerar o pacote de atualizacao.
    goto :END
)

if not exist "%~dp0output\AccessView-Update-v0.10.1.zip" (
    echo ERRO: O pacote ZIP de atualizacao nao foi encontrado.
    goto :END
)

echo [6/6] Gerando o instalador...
>> "%LOG_FILE%" echo ISCC encontrado em: %ISCC%
"%ISCC%" "%~dp0AccessView.iss" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERRO: O Inno Setup nao conseguiu gerar o instalador.
    goto :END
)

if not exist "%~dp0output\AccessView-Setup-v0.10.1.exe" (
    echo ERRO: O instalador nao foi encontrado depois da compilacao.
    goto :END
)

set "EXIT_CODE=0"
echo.
echo ==========================================
echo RELEASE GERADA COM SUCESSO
echo ==========================================
echo.
echo EXE:
echo %~dp0dist\AccessView\AccessView.exe
echo.
echo INSTALADOR:
echo %~dp0output\AccessView-Setup-v0.10.1.exe
echo.
echo ATUALIZACAO:
echo %~dp0output\AccessView-Update-v0.10.1.zip
echo.
goto :END

:CHECK_FILE
if exist "%~1" exit /b 0
echo ERRO: Arquivo obrigatorio nao encontrado:
echo %~1
>> "%LOG_FILE%" echo ERRO: Arquivo ausente: %~1
exit /b 1

:FIND_INNO
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if defined ISCC exit /b 0

if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC exit /b 0

if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC exit /b 0

for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do set "ISCC=%%I"
exit /b 0

:END
echo.
if "%EXIT_CODE%"=="0" (
    >> "%LOG_FILE%" echo Build concluido com sucesso em %date% %time%
) else (
    echo A compilacao falhou.
    echo Abra BUILD-RELEASE.log para ver o erro completo.
    >> "%LOG_FILE%" echo Build finalizado com erro em %date% %time%
)
echo.
echo Pressione qualquer tecla para fechar.
pause >nul
exit /b %EXIT_CODE%
