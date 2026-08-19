from django.urls import path

from apps.communications.views import (
    communication_create_inbound,
    communication_create_outbound,
    communication_detail,
    communication_list,
    communication_summary,
)


app_name = "communications"


urlpatterns = [
    path("summary/", communication_summary, name="summary"),
    path("", communication_list, name="list"),
    path("<uuid:communication_id>/", communication_detail, name="detail"),
    path("outbound/", communication_create_outbound, name="create_outbound"),
    path("inbound/", communication_create_inbound, name="create_inbound"),
]
