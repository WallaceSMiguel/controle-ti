@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente Python pela primeira vez...
    python -m venv .venv || goto erro
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto erro
)
".venv\Scripts\python.exe" run.py
pause
exit /b 0
:erro
echo.
echo Nao foi possivel preparar o ambiente. Verifique se o Python 3.10+ esta instalado
echo e marcado como "Add python.exe to PATH".
pause
exit /b 1
