from django.http import JsonResponse
from django.http import HttpRequest
from django.shortcuts import render

from .i18n import get_language, tr
from .services import QuoteServiceError, get_market_quotes


def _ui_text_payload() -> dict[str, object]:
    language = get_language()
    ui_keys = [
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
    return {
        "language": language,
        "ui_text": {key: tr(key, language) for key in ui_keys},
    }


def index(request: HttpRequest):
    return render(request, "prices/index.html")


def quotes_api(request: HttpRequest):
    try:
        data = get_market_quotes(force_refresh=False)
        return JsonResponse({"ok": True, **data})
    except QuoteServiceError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(exc),
                **_ui_text_payload(),
            },
            status=502,
        )


def ui_text_api(request: HttpRequest):
    return JsonResponse({"ok": True, **_ui_text_payload()})
