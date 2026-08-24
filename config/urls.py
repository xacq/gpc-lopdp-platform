from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("legal/", include("apps.legal_content.urls")),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("cases/", include("apps.cases.urls")),
    path("assignments/", include("apps.cases.assignment_urls")),
    path("communications/", include("apps.communications.urls")),
    path("audit/", include("apps.audit.urls")),
    path("retention/", include("apps.retention.urls")),
    path("evidence/", include("apps.evidence.urls")),
    path("settings/", include("apps.organization.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
