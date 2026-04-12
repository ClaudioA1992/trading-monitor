from __future__ import annotations

import json
import os
import threading
from pathlib import Path

TRANSLATIONS: dict[str, dict[str, str]] = {
    "es": {
        "app_title": "Monitor de Mercado",
        "app_subtitle": "Monitoreo en tiempo real",
        "indices_title": "Indices Relevantes",
        "tray_show": "Mostrar widget",
        "tray_exit": "Salir",
        "tray_language": "Idioma",
        "tray_always_on_top": "Siempre al frente",
        "tray_about": "Acerca de",
        "about_title": "Acerca de",
        "about_body": "Este widget usa CoinGecko API para cotizaciones de mercado.\n\nCreado por Claudio Torres, 2026.",
        "compact_on": "Compactar",
        "compact_off": "Expandir",
        "status_loading": "Actualizando...",
        "status_updated": "Actualizado",
        "status_cache": "Dato en cache",
        "status_waiting": "esperando CoinGecko...",
        "status_retry_in": "Reintento en {seconds}s.",
        "status_no_data": "Sin datos",
        "status_topmost_hint": "Menu en bandeja: Mostrar o Salir",
        "idx_high_24h": "Max 24h",
        "idx_low_24h": "Min 24h",
        "idx_sma_6h": "SMA 6h",
        "idx_rsi_14h": "RSI 14h",
        "idx_vol_24h": "Vol 24h",
        "lbl_1h": "1h",
        "lbl_24h": "24h",
        "lbl_30d": "30d",
    },
    "en": {
        "app_title": "Market Monitor",
        "app_subtitle": "Real-time market tracking",
        "indices_title": "Key Indices",
        "tray_show": "Show widget",
        "tray_exit": "Exit",
        "tray_language": "Language",
        "tray_always_on_top": "Always on top",
        "tray_about": "About",
        "about_title": "About",
        "about_body": "This widget uses CoinGecko API for market quotes.\n\nCreated by Claudio Torres, 2026.",
        "compact_on": "Compact",
        "compact_off": "Expand",
        "status_loading": "Updating...",
        "status_updated": "Updated",
        "status_cache": "Cached data",
        "status_waiting": "waiting for CoinGecko...",
        "status_retry_in": "Retry in {seconds}s.",
        "status_no_data": "No data",
        "status_topmost_hint": "Tray menu: Show or Exit",
        "idx_high_24h": "24h High",
        "idx_low_24h": "24h Low",
        "idx_sma_6h": "6h SMA",
        "idx_rsi_14h": "14h RSI",
        "idx_vol_24h": "24h Vol",
        "lbl_1h": "1h",
        "lbl_24h": "24h",
        "lbl_30d": "30d",
    },
    "pt": {
        "app_title": "Monitor de Mercado",
        "app_subtitle": "Monitoramento em tempo real",
        "indices_title": "Indices Principais",
        "tray_show": "Mostrar widget",
        "tray_exit": "Sair",
        "tray_language": "Idioma",
        "tray_always_on_top": "Sempre no topo",
        "tray_about": "Sobre",
        "about_title": "Sobre",
        "about_body": "Este widget usa a API CoinGecko para cotacoes de mercado.\n\nCriado por Claudio Torres, 2026.",
        "compact_on": "Compactar",
        "compact_off": "Expandir",
        "status_loading": "Atualizando...",
        "status_updated": "Atualizado",
        "status_cache": "Dado em cache",
        "status_waiting": "aguardando CoinGecko...",
        "status_retry_in": "Nova tentativa em {seconds}s.",
        "status_no_data": "Sem dados",
        "status_topmost_hint": "Menu da bandeja: Mostrar ou Sair",
        "idx_high_24h": "Max 24h",
        "idx_low_24h": "Min 24h",
        "idx_sma_6h": "SMA 6h",
        "idx_rsi_14h": "RSI 14h",
        "idx_vol_24h": "Vol 24h",
        "lbl_1h": "1h",
        "lbl_24h": "24h",
        "lbl_30d": "30d",
    },
    "fr": {
        "app_title": "Moniteur de Marche",
        "app_subtitle": "Suivi du marche en temps reel",
        "indices_title": "Indices Cles",
        "tray_show": "Afficher le widget",
        "tray_exit": "Quitter",
        "tray_language": "Langue",
        "tray_always_on_top": "Toujours au premier plan",
        "tray_about": "A propos",
        "about_title": "A propos",
        "about_body": "Ce widget utilise l'API CoinGecko pour les cotations du marche.\n\nCree par Claudio Torres, 2026.",
        "compact_on": "Compacter",
        "compact_off": "Etendre",
        "status_loading": "Mise a jour...",
        "status_updated": "Mis a jour",
        "status_cache": "Donnee en cache",
        "status_waiting": "en attente de CoinGecko...",
        "status_retry_in": "Nouvel essai dans {seconds}s.",
        "status_no_data": "Pas de donnees",
        "status_topmost_hint": "Menu de la zone: Afficher ou Quitter",
        "idx_high_24h": "Max 24h",
        "idx_low_24h": "Min 24h",
        "idx_sma_6h": "SMA 6h",
        "idx_rsi_14h": "RSI 14h",
        "idx_vol_24h": "Vol 24h",
        "lbl_1h": "1h",
        "lbl_24h": "24h",
        "lbl_30d": "30j",
    },
    "de": {
        "app_title": "Marktmonitor",
        "app_subtitle": "Marktbeobachtung in Echtzeit",
        "indices_title": "Wichtige Indizes",
        "tray_show": "Widget anzeigen",
        "tray_exit": "Beenden",
        "tray_language": "Sprache",
        "tray_always_on_top": "Immer im Vordergrund",
        "tray_about": "Info",
        "about_title": "Info",
        "about_body": "Dieses Widget nutzt die CoinGecko-API fur Marktpreise.\n\nErstellt von Claudio Torres, 2026.",
        "compact_on": "Kompakt",
        "compact_off": "Erweitern",
        "status_loading": "Aktualisiere...",
        "status_updated": "Aktualisiert",
        "status_cache": "Zwischengespeicherte Daten",
        "status_waiting": "warte auf CoinGecko...",
        "status_retry_in": "Neuer Versuch in {seconds}s.",
        "status_no_data": "Keine Daten",
        "status_topmost_hint": "Tray-Menue: Anzeigen oder Beenden",
        "idx_high_24h": "24h Hoch",
        "idx_low_24h": "24h Tief",
        "idx_sma_6h": "SMA 6h",
        "idx_rsi_14h": "RSI 14h",
        "idx_vol_24h": "Vol 24h",
        "lbl_1h": "1h",
        "lbl_24h": "24h",
        "lbl_30d": "30t",
    },
    "ja": {
        "app_title": "マーケットモニター",
        "app_subtitle": "リアルタイム市場モニタリング",
        "indices_title": "主要指数",
        "tray_show": "ウィジェットを表示",
        "tray_exit": "終了",
        "tray_language": "言語",
        "tray_always_on_top": "常に最前面",
        "tray_about": "このアプリについて",
        "about_title": "このアプリについて",
        "about_body": "このウィジェットは市場価格の取得にCoinGecko APIを使用しています。\n\n作成者: Claudio Torres, 2026.",
        "compact_on": "コンパクト",
        "compact_off": "展開",
        "status_loading": "更新中...",
        "status_updated": "更新済み",
        "status_cache": "キャッシュデータ",
        "status_waiting": "CoinGecko待機中...",
        "status_retry_in": "{seconds}秒後に再試行",
        "status_no_data": "データなし",
        "status_topmost_hint": "トレイメニュー: 表示 / 終了",
        "idx_high_24h": "24時間高値",
        "idx_low_24h": "24時間安値",
        "idx_sma_6h": "6時間SMA",
        "idx_rsi_14h": "14時間RSI",
        "idx_vol_24h": "24時間ボラ",
        "lbl_1h": "1時間",
        "lbl_24h": "24時間",
        "lbl_30d": "30日",
    },
    "zh": {
        "app_title": "市场监控",
        "app_subtitle": "实时市场追踪",
        "indices_title": "关键指标",
        "tray_show": "显示小组件",
        "tray_exit": "退出",
        "tray_language": "语言",
        "tray_always_on_top": "始终置顶",
        "tray_about": "关于",
        "about_title": "关于",
        "about_body": "此小组件使用 CoinGecko API 获取市场报价。\n\n创建者: Claudio Torres, 2026.",
        "compact_on": "紧凑",
        "compact_off": "展开",
        "status_loading": "正在更新...",
        "status_updated": "已更新",
        "status_cache": "缓存数据",
        "status_waiting": "等待 CoinGecko...",
        "status_retry_in": "{seconds}秒后重试",
        "status_no_data": "无数据",
        "status_topmost_hint": "托盘菜单: 显示 或 退出",
        "idx_high_24h": "24小时最高",
        "idx_low_24h": "24小时最低",
        "idx_sma_6h": "6小时SMA",
        "idx_rsi_14h": "14小时RSI",
        "idx_vol_24h": "24小时波动",
        "lbl_1h": "1小时",
        "lbl_24h": "24小时",
        "lbl_30d": "30天",
    },
}

_LANGUAGE_LOCK = threading.Lock()
_current_language = "es"


def _language_store_path() -> Path:
    # Persist in user profile so it survives app restarts and packaged runs.
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "BTCWidget" / "settings.json"
    return Path.home() / ".btc_widget_settings.json"


def _load_persisted_language() -> str | None:
    path = _language_store_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None

    code = str(payload.get("language", "")).strip().lower()
    if code in TRANSLATIONS:
        return code
    return None


def _persist_language(language_code: str) -> None:
    path = _language_store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"language": language_code}), encoding="utf-8")
    except OSError:
        # Persistence is best-effort; keep runtime language even if write fails.
        pass


_persisted = _load_persisted_language()
if _persisted is not None:
    _current_language = _persisted


def get_language() -> str:
    with _LANGUAGE_LOCK:
        return _current_language


def set_language(language_code: str) -> str:
    normalized = language_code.strip().lower()
    if normalized not in TRANSLATIONS:
        return get_language()

    global _current_language
    with _LANGUAGE_LOCK:
        _current_language = normalized
        _persist_language(_current_language)
        return _current_language


def tr(key: str, language_code: str | None = None) -> str:
    lang = language_code or get_language()
    table = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    if key in table:
        return table[key]
    return TRANSLATIONS["en"].get(key, key)
