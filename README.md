# BTC + Forex + Metales Widget (Django)

Widget de escritorio para Windows 10 hecho con Python + Django.

Muestra en vivo:
- BTC/USD
- ETH/USD
- EUR/USD
- XAU/USD (oro)
- XAG/USD (plata)

Fuente de datos: **CoinGecko API** (`/api/v3/coins/bitcoin/market_chart`).

## Requisitos

- Windows 10
- Python 3.10+
- WebView2 Runtime (normalmente ya instalado con Edge)

## Arranque rapido

1. Doble clic en `run_widget.bat`
2. Se abrirá una ventana compacta tipo widget sin bordes, sin minimizar/maximizar y sin redimensionar.
3. El servidor local quedará corriendo en `http://127.0.0.1:8765/`

Para cerrar el widget: `Alt + F4`.

## Modo user-friendly (sin programar)

- El widget crea un icono en la bandeja del sistema (zona de iconos pequenos, cerca del reloj).
- Desde ese icono puedes:
  - `Mostrar widget`
  - `Siempre al frente` (opcion nativa de Windows desde bandeja)
  - `Salir` (cierra app completa)

No necesitas abrir terminal para usarlo.

## Generar EXE para Windows

1. Doble clic en `build_exe.bat`
2. Al terminar, abre: `dist/BTCWidget/BTCWidget.exe`

Ese `.exe` incluye dependencias y no requiere instalar Python.

## Build para Linux

Si quieres binario Linux, debes compilar en Linux (build nativo):

1. `chmod +x build_linux.sh`
2. `./build_linux.sh`
3. Binario generado en: `dist/BTCWidget/BTCWidget`

Nota: Windows y Linux requieren builds separados.

`build_exe.bat` limpia automaticamente archivos temporales de build al finalizar:
- `build/`
- `BTCWidget.spec`
- `__pycache__/`
- `*.pyc`

## Modo desarrollo

Ejecuta `run_dev.bat` para correr la app en navegador durante desarrollo.

## API key (opcional)

Puedes usar una key demo/pro de CoinGecko como variable de entorno:

```powershell
$env:COINGECKO_API_KEY="tu_api_key"
```

Si existe, el proyecto la envía en el header `x-cg-demo-api-key`.

## Vista del widget

- Botones para seleccionar el activo principal (`BTC/USD`, `ETH/USD`, `EUR/USD`, `XAU/USD`, `XAG/USD`)
- Variacion intra hora (1h) e intra dia (24h)
- Tarjeta de indices relevantes por activo (Max/Min 24h, SMA 6h, RSI 14h, Vol 24h)
- Cinta deslizante tipo ticker con otros valores clave
- Refresco visual cada 5 segundos

## Notas de calculo

Las series se calculan con `market_chart` de Bitcoin en distintas divisas de referencia.
Los cruces se derivan asi:

- `EUR/USD = (BTC/USD) / (BTC/EUR)`
- `XAU/USD = (BTC/USD) / (BTC/XAU)`
- `XAG/USD = (BTC/USD) / (BTC/XAG)`

## Estructura

- `prices/services.py`: integración CoinGecko, cálculo de cruces e indicadores
- `prices/views.py`: endpoint JSON y vista principal
- `static/css/widget.css`: estilo del widget
- `static/js/widget.js`: selector de activos, ticker y refresco cada 5s
- `desktop_widget.py`: ventana de escritorio sin bordes (pywebview)

## Endpoint local

- `GET /api/quotes/`

Respuesta:

```json
{
  "ok": true,
  "updated_at": 1743800000,
  "stale": false,
  "retry_after_seconds": 0,
  "assets": {
    "BTC/USD": {
      "symbol": "BTC/USD",
      "display": "$67,890.12",
      "change_1h_pct": 0.21,
      "change_24h_pct": 1.86,
      "indices": []
    }
  },
  "ticker": []
}
```
