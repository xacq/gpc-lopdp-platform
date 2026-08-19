from django.urls import path

from apps.audit.views import (
    audit_event_detail,
    audit_event_list,
    audit_export_csv,
    audit_integrity,
)


app_name = "audit"


urlpatterns = [
    path("events/", audit_event_list, name="event_list"),
    path("events/<int:event_id>/", audit_event_detail, name="event_detail"),
    path("export.csv", audit_export_csv, name="export_csv"),
    path("integrity/", audit_integrity, name="integrity"),
]
