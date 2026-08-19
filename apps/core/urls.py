from django.urls import path

from apps.core.views import (
    contact,
    dashboard,
    dashboard_summary,
    home,
    report_export_csv,
    reports,
    report_summary,
    rights,
)


app_name = "core"


urlpatterns = [
    path("", home, name="home"),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/summary/", dashboard_summary, name="dashboard_summary"),
    path("reports/summary/", report_summary, name="report_summary"),
    path("reports/", reports, name="reports"),
    path("reports/export.csv", report_export_csv, name="report_export_csv"),
    path("derechos/", rights, name="rights"),
    path("contacto/", contact, name="contact"),
]
