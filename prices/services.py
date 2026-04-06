from __future__ import annotations

import os
import statistics
import threading
import time
from collections import deque
from decimal import Decimal, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from .i18n import get_language, tr

COINGECKO_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT_SECONDS = 10
CACHE_TTL_SECONDS = 0.0
HISTORY_24H_CACHE_TTL_SECONDS = 300.0
SPOT_CACHE_TTL_SECONDS = 0.0
DEFAULT_RETRY_AFTER_SECONDS = 30
MAX_UPSTREAM_CALLS_PER_MINUTE = 10

_cached_result: dict[str, Any] | None = None
_cached_at: float = 0.0
_next_allowed_request_at: float = 0.0
_history_24h_cache: dict[str, list[tuple[int, Decimal]]] = {}
_history_24h_cached_at: float = 0.0
_spot_cache: dict[str, Decimal] | None = None
_spot_cached_at: float = 0.0
_next_allowed_spot_request_at: float = 0.0
_upstream_call_lock = threading.Lock()
_upstream_call_timestamps: deque[float] = deque()


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
    now = time.time()
    with _upstream_call_lock:
        while _upstream_call_timestamps and (now - _upstream_call_timestamps[0]) >= 60.0:
            _upstream_call_timestamps.popleft()
        if len(_upstream_call_timestamps) >= MAX_UPSTREAM_CALLS_PER_MINUTE:
            raise QuoteServiceError("Limite local de llamadas por minuto alcanzado.")
        _upstream_call_timestamps.append(now)

    response = requests.get(
        url,
        params=params,
        headers=_coingecko_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _fetch_coin_series(
    coin_id: str,
    vs_currency: str,
    days: int,
    interval: str,
) -> list[tuple[int, Decimal]]:
    payload = _fetch_json(
        f"{COINGECKO_URL}/coins/{coin_id}/market_chart",
        {
            "vs_currency": vs_currency,
            "days": days,
            "interval": interval,
        },
    )
    prices = payload.get("prices", [])
    if not prices:
        raise QuoteServiceError(f"Sin serie para {coin_id.upper()}/{vs_currency.upper()}.")

    series: list[tuple[int, Decimal]] = []
    for point in prices:
        if len(point) < 2:
            continue
        series.append((int(point[0]), _decimal(point[1])))

    if len(series) < 3:
        raise QuoteServiceError(f"Serie insuficiente para {coin_id.upper()}/{vs_currency.upper()}.")
    return series


def _get_cached_or_fetch_24h(now: float) -> dict[str, list[tuple[int, Decimal]]]:
    global _history_24h_cache, _history_24h_cached_at

    if _history_24h_cache and (now - _history_24h_cached_at) < HISTORY_24H_CACHE_TTL_SECONDS:
        return _history_24h_cache

    history = {
        "btc_usd": _fetch_coin_series("bitcoin", "usd", 1, "hourly"),
        "btc_eur": _fetch_coin_series("bitcoin", "eur", 1, "hourly"),
        "btc_xau": _fetch_coin_series("bitcoin", "xau", 1, "hourly"),
        "btc_xag": _fetch_coin_series("bitcoin", "xag", 1, "hourly"),
        "eth_usd": _fetch_coin_series("ethereum", "usd", 1, "hourly"),
    }
    _history_24h_cache = history
    _history_24h_cached_at = now
    return history


def _get_cached_or_fetch_spot(now: float) -> dict[str, Decimal]:
    global _spot_cache, _spot_cached_at, _next_allowed_spot_request_at

    if _spot_cache and (now - _spot_cached_at) < SPOT_CACHE_TTL_SECONDS:
        return _spot_cache

    if now < _next_allowed_spot_request_at:
        wait_seconds = max(int(_next_allowed_spot_request_at - now), 1)
        raise QuoteServiceError(f"Spot en backoff local ({wait_seconds}s).")

    try:
        payload = _fetch_json(
            f"{COINGECKO_URL}/simple/price",
            {
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd,eur,xau,xag",
            },
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            retry_after_seconds = _parse_retry_after_seconds(
                exc.response.headers.get("Retry-After"),
                now,
            )
            if retry_after_seconds is None:
                retry_after_seconds = DEFAULT_RETRY_AFTER_SECONDS
            _next_allowed_spot_request_at = now + retry_after_seconds
        raise

    btc = payload.get("bitcoin", {})
    eth = payload.get("ethereum", {})

    spot: dict[str, Decimal] = {}

    mapping = {
        "btc_usd": btc.get("usd"),
        "btc_eur": btc.get("eur"),
        "btc_xau": btc.get("xau"),
        "btc_xag": btc.get("xag"),
        "eth_usd": eth.get("usd"),
    }

    for key, raw in mapping.items():
        if raw is None:
            continue
        try:
            value = _decimal(raw)
        except (ValueError, TypeError, ArithmeticError):
            continue
        if value > 0:
            spot[key] = value

    if not spot:
        raise QuoteServiceError("Sin precios spot validos en CoinGecko.")

    _spot_cache = spot
    _spot_cached_at = now
    _next_allowed_spot_request_at = 0.0
    return spot


def _inject_latest_point(series: list[tuple[int, Decimal]], latest_price: Decimal, now: float) -> list[tuple[int, Decimal]]:
    if not series:
        return series
    updated = list(series)
    updated[-1] = (int(now * 1000), latest_price)
    return updated


def _derive_cross_series(
    numerator: list[tuple[int, Decimal]],
    denominator: list[tuple[int, Decimal]],
) -> list[tuple[int, Decimal]]:
    length = min(len(numerator), len(denominator))
    out: list[tuple[int, Decimal]] = []
    for idx in range(length):
        den = denominator[idx][1]
        if den == 0:
            continue
        out.append((numerator[idx][0], numerator[idx][1] / den))
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
    series_24h: list[tuple[int, Decimal]],
    decimals: int,
    use_currency_prefix: bool,
    language: str,
) -> dict[str, Any]:
    prices_24h = [p for _, p in series_24h]

    current = prices_24h[-1]
    prev_1h = prices_24h[-2]
    prev_24h = prices_24h[0]

    high_24h = max(prices_24h)
    low_24h = min(prices_24h)
    sma_6h = sum(prices_24h[-6:], Decimal("0")) / Decimal(str(min(6, len(prices_24h))))
    rsi = _rsi_14(prices_24h)
    volatility = _volatility_24h_pct(prices_24h)

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
                "label": tr("idx_high_24h", language),
                "value": f"{_round(high_24h, decimals):,.{decimals}f}",
                "currency": use_currency_prefix,
            },
            {
                "label": tr("idx_low_24h", language),
                "value": f"{_round(low_24h, decimals):,.{decimals}f}",
                "currency": use_currency_prefix,
            },
            {
                "label": tr("idx_sma_6h", language),
                "value": f"{_round(sma_6h, decimals):,.{decimals}f}",
                "currency": use_currency_prefix,
            },
            {
                "label": tr("idx_rsi_14h", language),
                "value": f"{_round(rsi, 1):,.1f}",
                "currency": False,
            },
            {
                "label": tr("idx_vol_24h", language),
                "value": f"{_round(volatility, 2):,.2f}%",
                "currency": False,
            },
        ],
    }


def _build_ui_text(language: str) -> dict[str, str]:
    keys = [
        "app_title",
        "app_subtitle",
        "indices_title",
        "compact_on",
        "compact_off",
        "status_loading",
        "status_updated",
        "status_cache",
        "status_waiting",
        "status_retry_in",
        "status_no_data",
        "lbl_1h",
        "lbl_24h",
    ]
    return {key: tr(key, language) for key in keys}


def _build_degraded_result(language: str, now: float, retry_after_seconds: int) -> dict[str, Any]:
    # Safe fallback when CoinGecko throttles before any warm cache exists.
    def _asset(symbol: str, display: str, price: float, decimals: int, currency: bool) -> dict[str, Any]:
        value_text = f"{price:,.{decimals}f}"
        return {
            "symbol": symbol,
            "price": price,
            "display": display,
            "change_1h_pct": 0.0,
            "change_24h_pct": 0.0,
            "indices": [
                {"label": tr("idx_high_24h", language), "value": value_text, "currency": currency},
                {"label": tr("idx_low_24h", language), "value": value_text, "currency": currency},
                {"label": tr("idx_sma_6h", language), "value": value_text, "currency": currency},
                {"label": tr("idx_rsi_14h", language), "value": "50.0", "currency": False},
                {"label": tr("idx_vol_24h", language), "value": "0.00%", "currency": False},
            ],
        }

    btc_usd = 0.0
    eth_usd = 0.0
    btc_eur = 0.0
    btc_xau = 0.0
    btc_xag = 0.0

    if _spot_cache:
        btc_usd = float(_spot_cache.get("btc_usd", _decimal(0)))
        eth_usd = float(_spot_cache.get("eth_usd", _decimal(0)))
        btc_eur = float(_spot_cache.get("btc_eur", _decimal(0)))
        btc_xau = float(_spot_cache.get("btc_xau", _decimal(0)))
        btc_xag = float(_spot_cache.get("btc_xag", _decimal(0)))

    eur_usd = (btc_usd / btc_eur) if btc_eur else 0.0
    xau_usd = (btc_usd / btc_xau) if btc_xau else 0.0
    xag_usd = (btc_usd / btc_xag) if btc_xag else 0.0
    eth_btc = (eth_usd / btc_usd) if btc_usd else 0.0
    xau_xag = (xau_usd / xag_usd) if xag_usd else 0.0

    assets = {
        "BTC/USD": _asset("BTC/USD", f"${btc_usd:,.2f}" if btc_usd else "$--", btc_usd, 2, True),
        "ETH/USD": _asset("ETH/USD", f"${eth_usd:,.2f}" if eth_usd else "$--", eth_usd, 2, True),
        "EUR/USD": _asset("EUR/USD", f"{eur_usd:,.5f}" if eur_usd else "--", eur_usd, 5, False),
        "XAU/USD": _asset("XAU/USD", f"${xau_usd:,.2f}" if xau_usd else "$--", xau_usd, 2, True),
        "XAG/USD": _asset("XAG/USD", f"${xag_usd:,.3f}" if xag_usd else "$--", xag_usd, 3, True),
    }

    return {
        "updated_at": int(now),
        "stale": True,
        "retry_after_seconds": max(retry_after_seconds, 1),
        "language": language,
        "ui_text": _build_ui_text(language),
        "assets": assets,
        "ticker": [
            {"label": "BTC/USD", "value": assets["BTC/USD"]["display"], "change_24h_pct": 0.0},
            {"label": "EUR/USD", "value": assets["EUR/USD"]["display"], "change_24h_pct": 0.0},
            {"label": "ETH/USD", "value": assets["ETH/USD"]["display"], "change_24h_pct": 0.0},
            {"label": "BTC/EUR", "value": f"€{btc_eur:,.2f}" if btc_eur else "--", "change_24h_pct": 0.0},
            {"label": "ETH/BTC", "value": f"{eth_btc:,.5f}" if eth_btc else "--", "change_24h_pct": 0.0},
            {"label": "BTC/XAU", "value": f"{btc_xau:,.3f}" if btc_xau else "--", "change_24h_pct": 0.0},
            {"label": "BTC/XAG", "value": f"{btc_xag:,.3f}" if btc_xag else "--", "change_24h_pct": 0.0},
            {"label": "XAU/XAG", "value": f"{xau_xag:,.2f}" if xau_xag else "--", "change_24h_pct": 0.0},
        ],
    }


def get_market_quotes(force_refresh: bool = False) -> dict[str, Any]:
    global _cached_result, _cached_at, _next_allowed_request_at

    language = get_language()
    now = time.time()

    if not force_refresh and _cached_result and (now - _cached_at) < CACHE_TTL_SECONDS:
        print("[quotes] fast cache hit", flush=True)
        fast_copy = dict(_cached_result)
        fast_copy["language"] = language
        fast_copy["ui_text"] = _build_ui_text(language)
        return fast_copy

    if not force_refresh and _cached_result and now < _next_allowed_request_at:
        wait_seconds = max(int(_next_allowed_request_at - now), 1)
        print(f"[quotes] backoff active, retry in {wait_seconds}s", flush=True)
        stale_result = dict(_cached_result)
        stale_result["stale"] = True
        stale_result["retry_after_seconds"] = wait_seconds
        stale_result["language"] = language
        stale_result["ui_text"] = _build_ui_text(language)
        return stale_result

    try:
        history_24h = _get_cached_or_fetch_24h(now)

        spot: dict[str, Decimal] = {}
        try:
            spot = _get_cached_or_fetch_spot(now)
        except (requests.RequestException, QuoteServiceError, ValueError, TypeError) as spot_exc:
            print(f"[quotes] spot unavailable, fallback to history: {spot_exc}", flush=True)

        def _latest_series(key: str) -> list[tuple[int, Decimal]]:
            base = history_24h[key]
            latest = spot.get(key)
            if latest is None or latest <= 0:
                return base
            return _inject_latest_point(base, latest, now)

        btc_usd_24h = _latest_series("btc_usd")
        eth_usd_24h = _latest_series("eth_usd")
        btc_eur_24h = _latest_series("btc_eur")
        btc_xau_24h = _latest_series("btc_xau")
        btc_xag_24h = _latest_series("btc_xag")

        eur_usd_24h = _derive_cross_series(btc_usd_24h, btc_eur_24h)
        xau_usd_24h = _derive_cross_series(btc_usd_24h, btc_xau_24h)
        xag_usd_24h = _derive_cross_series(btc_usd_24h, btc_xag_24h)

        assets: dict[str, dict[str, Any]] = {
            "BTC/USD": _build_asset_payload("BTC/USD", btc_usd_24h, 2, True, language),
            "ETH/USD": _build_asset_payload("ETH/USD", eth_usd_24h, 2, True, language),
            "EUR/USD": _build_asset_payload("EUR/USD", eur_usd_24h, 5, False, language),
            "XAU/USD": _build_asset_payload("XAU/USD", xau_usd_24h, 2, True, language),
            "XAG/USD": _build_asset_payload("XAG/USD", xag_usd_24h, 3, True, language),
        }

        btc_eur = btc_eur_24h[-1][1]
        btc_xau = btc_xau_24h[-1][1]
        btc_xag = btc_xag_24h[-1][1]
        eth_btc = assets["ETH/USD"]["price"] / assets["BTC/USD"]["price"]
        gold_silver_ratio = assets["XAU/USD"]["price"] / assets["XAG/USD"]["price"]

        result: dict[str, Any] = {
            "updated_at": int(now),
            "stale": False,
            "retry_after_seconds": 0,
            "language": language,
            "ui_text": _build_ui_text(language),
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
        print("[quotes] live data refreshed", flush=True)
        _next_allowed_request_at = 0.0
    except (requests.RequestException, QuoteServiceError, ValueError, TypeError, ZeroDivisionError) as exc:
        retry_after_seconds: int | None = None
        if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 429:
            retry_after_seconds = _parse_retry_after_seconds(
                exc.response.headers.get("Retry-After"),
                now,
            )
            if retry_after_seconds is None:
                retry_after_seconds = DEFAULT_RETRY_AFTER_SECONDS
            _next_allowed_request_at = now + retry_after_seconds
        elif _next_allowed_request_at <= now:
            retry_after_seconds = DEFAULT_RETRY_AFTER_SECONDS
            _next_allowed_request_at = now + retry_after_seconds

        if _cached_result:
            print(f"[quotes] upstream error, serving stale cache: {exc}", flush=True)
            stale_result = dict(_cached_result)
            stale_result["stale"] = True
            if retry_after_seconds is not None:
                stale_result["retry_after_seconds"] = retry_after_seconds
            elif _next_allowed_request_at > now:
                stale_result["retry_after_seconds"] = max(int(_next_allowed_request_at - now), 1)
            stale_result["language"] = language
            stale_result["ui_text"] = _build_ui_text(language)
            return stale_result
        wait_seconds = max(int(_next_allowed_request_at - now), 1)
        print(f"[quotes] upstream error without cache, serving degraded fallback: {exc}", flush=True)
        fallback_result = _build_degraded_result(language, now, wait_seconds)
        _cached_result = dict(fallback_result)
        _cached_at = now
        return fallback_result

    _cached_result = result
    _cached_at = now
    return result
