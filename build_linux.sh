#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "[1/4] Preparando entorno..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[2/4] Limpiando archivos temporales..."
rm -rf build dist __pycache__
rm -f BTCWidget.spec
find . -name "*.pyc" -delete

echo "[3/4] Compilando binario Linux..."
python -m PyInstaller --noconfirm --windowed --name "BTCWidget" \
  --log-level WARN \
  --add-data "static:static" \
  --add-data "prices/templates:prices/templates" \
  --add-data "prices:prices" \
  --add-data "btc_widget:btc_widget" \
  "desktop_widget.py"

echo "[4/4] Limpieza final..."
rm -rf build __pycache__
rm -f BTCWidget.spec
find . -name "*.pyc" -delete

if [ ! -f "dist/BTCWidget/BTCWidget" ]; then
  echo "ERROR: no se encontro dist/BTCWidget/BTCWidget"
  exit 1
fi

echo
echo "Build completo. Binario en: dist/BTCWidget/BTCWidget"
