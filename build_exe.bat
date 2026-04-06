@echo off
setlocal

cd /d "%~dp0"

echo [1/4] Preparando entorno...

if not exist ".venv" (
  py -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo [2/4] Limpiando archivos temporales...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist BTCWidget.spec del /q BTCWidget.spec
if exist __pycache__ rmdir /s /q __pycache__
for /r %%f in (*.pyc) do del /q "%%f" >nul 2>&1

echo [3/4] Compilando EXE (puede tardar varios minutos, no cierres esta ventana)...
python -m PyInstaller --noconfirm --windowed --name "BTCWidget" ^
  --log-level WARN ^
  --add-data "static;static" ^
  --add-data "prices/templates;prices/templates" ^
  --add-data "prices;prices" ^
  --add-data "btc_widget;btc_widget" ^
  "desktop_widget.py"

if errorlevel 1 (
  echo.
  echo ERROR: fallo la compilacion del EXE.
  pause
  exit /b 1
)

echo [4/4] Limpieza final...
if exist build rmdir /s /q build
if exist BTCWidget.spec del /q BTCWidget.spec
if exist __pycache__ rmdir /s /q __pycache__
for /r %%f in (*.pyc) do del /q "%%f" >nul 2>&1

if not exist "dist\BTCWidget\BTCWidget.exe" (
  echo.
  echo ERROR: no se encontro dist\BTCWidget\BTCWidget.exe
  pause
  exit /b 1
)

echo.
echo Build completo. Ejecutable en: dist\BTCWidget\BTCWidget.exe
pause
