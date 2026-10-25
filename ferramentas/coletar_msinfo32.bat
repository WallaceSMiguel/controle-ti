@echo off
chcp 65001 >nul
REM ============================================================
REM  Controle TI - coleta da configuracao deste computador
REM  Copie este arquivo para uma pasta compartilhada da rede e
REM  execute em cada computador. Ele grava NOME-DO-PC.nfo na
REM  mesma pasta. Depois importe os arquivos em:
REM  Equipamentos > Importar do msinfo32
REM ============================================================
set "DESTINO=%~dp0%COMPUTERNAME%.nfo"
echo Coletando a configuracao de %COMPUTERNAME%...
echo Isso pode levar de 30 segundos a 2 minutos.
start /wait "" msinfo32.exe /nfo "%DESTINO%"
if exist "%DESTINO%" (
    echo.
    echo Pronto: %DESTINO%
) else (
    echo.
    echo Nao foi possivel gerar o arquivo. Verifique se a pasta permite gravacao.
)
timeout /t 5 >nul
