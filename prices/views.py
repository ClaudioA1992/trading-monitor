from django.http import JsonResponse
from django.shortcuts import render

from .services import QuoteServiceError, get_market_quotes


def index(request):
    return render(request, "prices/index.html")


def quotes_api(request):
    try:
        data = get_market_quotes(force_refresh=False)
        return JsonResponse({"ok": True, **data})
    except QuoteServiceError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )
