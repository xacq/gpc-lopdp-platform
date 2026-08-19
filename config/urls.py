"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("legal/", include("apps.legal_content.urls")),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("cases/", include("apps.cases.urls")),
    path("settings/", include("apps.organization.urls")),
]
