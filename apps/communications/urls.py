from django.urls import path

from apps.communications.views import (
    communication_panel,
    communication_create_inbound,
    communication_create_outbound,
    communication_detail,
    communication_list,
    communication_summary,
    portability_download,
    portability_export_list,
    portability_generate,
    portability_revoke,
)


app_name = "communications"


urlpatterns = [
    path("panel/", communication_panel, name="panel"),
    path("summary/", communication_summary, name="summary"),
    path("portability/", portability_export_list, name="portability_list"),
    path(
        "portability/generate/",
        portability_generate,
        name="portability_generate",
    ),
    path(
        "portability/download/",
        portability_download,
        name="portability_download",
    ),
    path(
        "portability/<uuid:export_id>/revoke/",
        portability_revoke,
        name="portability_revoke",
    ),
    path("", communication_list, name="list"),
    path("<uuid:communication_id>/", communication_detail, name="detail"),
    path("outbound/", communication_create_outbound, name="create_outbound"),
    path("inbound/", communication_create_inbound, name="create_inbound"),
]
