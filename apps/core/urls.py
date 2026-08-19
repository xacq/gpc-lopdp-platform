from django.urls import path

from apps.core.views import contact, dashboard_summary, home, rights


app_name = "core"


urlpatterns = [
    path("", home, name="home"),
    path("dashboard/summary/", dashboard_summary, name="dashboard_summary"),
    path("derechos/", rights, name="rights"),
    path("contacto/", contact, name="contact"),
]
