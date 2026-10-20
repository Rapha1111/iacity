@echo off
REM Lance IACity sous Windows : crée un environnement virtuel, installe Flask, démarre le serveur.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || (echo Python 3 est requis : https://www.python.org/downloads/ & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --quiet -r requirements.txt
start "" http://127.0.0.1:5000
python app.py
pause
