@echo off
rem Cria o ambiente virtual e instala as dependencias (rodar uma unica vez).
cd /d "%~dp0"
python -m venv .venv || goto :erro
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :erro
.venv\Scripts\python.exe gerar_amostras.py
echo.
echo Instalacao concluida. Use executar.bat para abrir o equalizador.
pause
exit /b 0
:erro
echo.
echo Falha na instalacao. Verifique se o Python 3.10+ esta instalado e no PATH.
pause
exit /b 1
