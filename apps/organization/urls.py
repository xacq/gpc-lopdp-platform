from django.urls import path

from apps.organization.views import system_settings


app_name = "organization"

urlpatterns = [
    path("", system_settings, name="system_settings"),
]
