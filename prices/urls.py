from django.urls import path

from .views import index, quotes_api

urlpatterns = [
    path("", index, name="index"),
    path("api/quotes/", quotes_api, name="quotes_api"),
]
