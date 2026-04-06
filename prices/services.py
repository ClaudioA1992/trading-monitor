from __future__ import annotations

import os
import statistics
import time
from decimal import Decimal, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
from typing import Any

import requests

COINGECKO_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT_SECONDS = 10
CACHE_TTL_SECONDS = 5.0
HISTORY_CACHE_TTL_SECONDS = 300.0

_cached_result: dict[str, Any] | None = None
_cached_at: float = 0.0
_next_allowed_request_at: float = 0.0
_history_cache: dict[str, list[tuple[int, Decimal]]] = {}
_history_cached_at: float = 0.0


class QuoteServiceError(Exception):
    pass


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _round(value: Decimal, places: int) -> Decimal:
    quant = Decimal("1") if places == 0 else Decimal(f"1e-{places}")
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def _coingecko_headers() -> dict[str, str]:
    api_key = os.getenv("COINGECKO_API_KEY", "").strip()
    if not api_key:
        return {}
    return {"x-cg-demo-api-key": api_key}


def _extract_rate(data: dict[str, Any], code: str) -> Decimal:
    try:
        return _decimal(data["rates"][code]["value"])
    except KeyError as exc:
        raise QuoteServiceError(f"No se encontro la tasa '{code}' en CoinGecko.") from exc


def _parse_retry_after_seconds(retry_after_value: str | None, now_ts: float) -> int | None:
    if not retry_after_value:
        return None

    value = retry_after_value.strip()
    if not value:
        return None

    if value.isdigit():
        return max(int(value), 0)

    try:
        dt = parsedate_to_datetime(value)
        return max(int(dt.timestamp() - now_ts), 0)
    except (TypeError, ValueError, OverflowError):
        return None


def _fetch_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers=_coingecko_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    return response.json()


def _fetch_coin_hourly_series(coin_id: str, vs_currency: str) -> list[tuple[int, Decimal]]:
    payload = _fetch_json(
        f"{COINGECKO_URL}/coins/{coin_id}/market_chart",
        {
            "vs_currency": vs_currency,
            "days": 1,
            "interval": "hourly",
        },
    )
    prices = payload.get("prices", [])
    if not prices:
        raise QuoteServiceError(
            f"Sin serie horaria para {coin_id.upper()}/{vs_currency.upper()}."
        )

    series: list[tuple[int, Decimal]] = []
    for point in prices:
        if len(point) < 2:
            continue
        ts_ms = int(point[0])
        price = _decimal(point[1])
        series.append((ts_ms, price))

    if len(series) < 3:
        raise QuoteServiceError(
            f"Serie insuficiente para {coin_id.upper()}/{vs_currency.upper()}."
        )
    return series


def _get_cached_or_fetch_history(now: float) -> dict[str, list[tuple[int, Decimal]]]:
    global _history_cached_at, _history_cache

    if _history_cache and (now - _history_cached_at) < HISTORY_CACHE_TTL_SECONDS:
        return _history_cache

    history = {
        "btc_usd": _fetch_coin_hourly_series("bitcoin", "usd"),
        "btc_eur": _fetch_coin_hourly_series("bitcoin", "eur"),
        "btc_xau": _fetch_coin_hourly_series("bitcoin", "xau"),
        "btc_xag": _fetch_coin_hourly_series("bitcoin", "xag"),
        "eth_usd": _fetch_coin_hourly_series("ethereum", "usd"),
    }
    _history_cache = history
    _history_cached_at = now
    return history


def _derive_cross_series(
    numerator: list[tuple[int, Decimal]],
    denominator: list[tuple[int, Decimal]],
) -> list[tuple[int, Decimal]]:
    length = min(len(numerator), len(denominator))
    out: list[tuple[int, Decimal]] = []
    for idx in range(length):
        ts = numerator[idx][0]
        den = denominator[idx][1]
        if den == 0:
            continue
        out.append((ts, numerator[idx][1] / den))
    if len(out) < 3:
        raise QuoteServiceError("No se pudo construir una serie derivada suficiente.")
    return out


def _pct_change(current: Decimal, past: Decimal) -> Decimal:
    if past == 0:
        return Decimal("0")
    return ((current - past) / past) * Decimal("100")


def _rsi_14(prices: list[Decimal]) -> Decimal:
    if len(prices) < 15:
        return Decimal("50")

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-14:]

    gains = sum((d for d in recent if d > 0), Decimal("0"))
    losses = -sum((d for d in recent if d < 0), Decimal("0"))

    avg_gain = gains / Decimal("14")
    avg_loss = losses / Decimal("14")
    if avg_loss == 0:
        return Decimal("100")

    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def _volatility_24h_pct(prices: list[Decimal]) -> Decimal:
    if len(prices) < 3:
        return Decimal("0")

    returns: list[float] = []
    for idx in range(1, len(prices)):
        previous = prices[idx - 1]
        current = prices[idx]
        if previous == 0:
            continue
        returns.append(float((current - previous) / previous))

    if len(returns) < 2:
        return Decimal("0")
    return _decimal(statistics.pstdev(returns) * 100)


def _build_asset_payload(
    symbol: str,
    series: list[tuple[int, Decimal]],
    decimals: int,
    use_currency_prefix: bool,
) -> dict[str, Any]:
    prices = [p for _, p in series]
    current = prices[-1]
    prev_1h = prices[-2]
    prev_24h = prices[0]

    high_24h = max(prices)
    low_24h = min(prices)
    sma_6h = sum(prices[-6:], Decimal("0")) / Decimal(str(min(6, len(prices))))
    rsi = _rsi_14(prices)
    volatility = _volatility_24h_pct(prices)

    price_text = f"{_round(current, decimals):,.{decimals}f}"
    display = f"${price_text}" if use_currency_prefix else price_text

    return {
        "symbol": symbol,
        "price": float(_round(current, decimals)),
        "display": display,
        "change_1h_pct": float(_round(_pct_change(current, prev_1h), 2)),
        "change_24h_pct": float(_round(_pct_change(current, prev_24h), 2)),
        "indices": [
            {
                "label": "Max 24h",
                "value": f"{_round(high_24h, decimals):,.{decimals}f}",
                "currency": use_currency_prefix,
            },
            {
                "label": "Min 24h",
                "value": f"{_round(low_24h, decimals):,.{decimals}f}",
                "currency": use_currency_prefix,
            },
            {
                "label": "SMA 6h",
                "value": f"{_round(sma_6h, decimals):,.{decimals}f}",
                "currency": use_currency_prefix,
            },
            {
                "label": "RSI 14h",
                "value": f"{_round(rsi, 1):,.1f}",
                "currency": False,
            },
            {
                "label": "Vol 24h",
                "value": f"{_round(volatility, 2):,.2f}%",
                "currency": False,
            },
        ],
    }


def get_market_quotes(force_refresh: bool = False) -> dict[str, Any]:
    global _cached_result, _cached_at, _next_allowed_request_at

    now = time.time()
    if not force_refresh and _cached_result and (now - _cached_at) < CACHE_TTL_SECONDS:
        return _cached_result

    if not force_refresh and _cached_result and now < _next_allowed_request_at:
        wait_seconds = max(int(_next_allowed_request_at - now), 1)
        stale_result = dict(_cached_result)
        stale_result["stale"] = True
        stale_result["stale_reason"] = (
            "Rate limit activo; reutilizando cache hasta el proximo intento permitido."
        )
        stale_result["retry_after_seconds"] = wait_seconds
        return stale_result

    try:
        history = _get_cached_or_fetch_history(now)

        btc_usd_series = history["btc_usd"]
        eth_usd_series = history["eth_usd"]
        eur_usd_series = _derive_cross_series(history["btc_usd"], history["btc_eur"])
        xau_usd_series = _derive_cross_series(history["btc_usd"], history["btc_xau"])
        xag_usd_series = _derive_cross_series(history["btc_usd"], history["btc_xag"])

        assets = {
            "BTC/USD": _build_asset_payload("BTC/USD", btc_usd_series, 2, True),
            "ETH/USD": _build_asset_payload("ETH/USD", eth_usd_series, 2, True),
            "EUR/USD": _build_asset_payload("EUR/USD", eur_usd_series, 5, False),
            "XAU/USD": _build_asset_payload("XAU/USD", xau_usd_series, 2, True),
            "XAG/USD": _build_asset_payload("XAG/USD", xag_usd_series, 3, True),
        }

        btc_eur = history["btc_eur"][-1][1]
        btc_xau = history["btc_xau"][-1][1]
        btc_xag = history["btc_xag"][-1][1]
        eth_btc = assets["ETH/USD"]["price"] / assets["BTC/USD"]["price"]
        gold_silver_ratio = assets["XAU/USD"]["price"] / assets["XAG/USD"]["price"]

        result = {
            "updated_at": int(now),
            "stale": False,
            "retry_after_seconds": 0,
            "assets": assets,
            "ticker": [
                {
                    "label": "BTC/USD",
                    "value": assets["BTC/USD"]["display"],
                    "change_24h_pct": assets["BTC/USD"]["change_24h_pct"],
                },
                {
                    "label": "EUR/USD",
                    "value": assets["EUR/USD"]["display"],
                    "change_24h_pct": assets["EUR/USD"]["change_24h_pct"],
                },
                {
                    "label": "ETH/USD",
                    "value": assets["ETH/USD"]["display"],
                    "change_24h_pct": assets["ETH/USD"]["change_24h_pct"],
                },
                {
                    "label": "BTC/EUR",
                    "value": f"€{_round(btc_eur, 2):,.2f}",
                    "change_24h_pct": 0.0,
                },
                {
                    "label": "ETH/BTC",
                    "value": f"{_round(_decimal(eth_btc), 5):,.5f}",
                    "change_24h_pct": 0.0,
                },
                {
                    "label": "BTC/XAU",
                    "value": f"{_round(btc_xau, 3):,.3f}",
                    "change_24h_pct": 0.0,
                },
                {
                    "label": "BTC/XAG",
                    "value": f"{_round(btc_xag, 3):,.3f}",
                    "change_24h_pct": 0.0,
                },
                {
                    "label": "XAU/XAG",
                    "value": f"{_round(_decimal(gold_silver_ratio), 2):,.2f}",
                    "change_24h_pct": 0.0,
                },
            ],
        }
        _next_allowed_request_at = 0.0
    except (requests.RequestException, QuoteServiceError, ValueError, TypeError, ZeroDivisionError) as exc:
        retry_after_seconds: int | None = None
        if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 429:
            retry_after_seconds = _parse_retry_after_seconds(
                exc.response.headers.get("Retry-After"),
                now,
            )
            if retry_after_seconds is None:
                retry_after_seconds = 5
            _next_allowed_request_at = now + retry_after_seconds

        if _cached_result:
            stale_result = dict(_cached_result)
            stale_result["stale"] = True
            stale_result["stale_reason"] = "CoinGecko sin respuesta temporal, mostrando ultimo valor."
            if retry_after_seconds is not None:
                stale_result["retry_after_seconds"] = retry_after_seconds
            elif _next_allowed_request_at > now:
                stale_result["retry_after_seconds"] = max(int(_next_allowed_request_at - now), 1)
            return stale_result
        raise QuoteServiceError("Fallo al consultar CoinGecko.") from exc

    _cached_result = result
    _cached_at = now
    return result
