@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv" (
  py -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt >nul

python desktop_widget.py
