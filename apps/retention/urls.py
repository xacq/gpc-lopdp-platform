from django.urls import path

from apps.retention.views import (
    retention_panel,
    retention_event_approve,
    retention_event_list,
    retention_event_reject,
    retention_event_retry,
    retention_summary,
)


app_name = "retention"


urlpatterns = [
    path("", retention_panel, name="panel"),
    path("summary/", retention_summary, name="summary"),
    path("events/", retention_event_list, name="event_list"),
    path("events/<uuid:event_id>/approve/", retention_event_approve, name="approve"),
    path("events/<uuid:event_id>/reject/", retention_event_reject, name="reject"),
    path("events/<uuid:event_id>/retry/", retention_event_retry, name="retry"),
]
