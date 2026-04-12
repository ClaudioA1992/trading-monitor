from django.urls import path

from .views import index, quotes_api, ui_text_api

urlpatterns = [
    path("", index, name="index"),
    path("api/quotes/", quotes_api, name="quotes_api"),
    path("api/ui-text/", ui_text_api, name="ui_text_api"),
]
