import csv

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.cases.services.dashboard import (
    CaseDashboardService,
    DashboardPermissionError,
)
from apps.cases.forms.reports import CaseReportFilterForm
from apps.cases.policies import can_access_case_panel, visible_requests_for
from apps.cases.services.reports import CaseReportService, ReportPermissionError
from apps.legal_content.models import RightCatalog
from apps.organization.defaults import (
    VINESA_PRIVACY_POLICY_URL,
    VINESA_SYSTEM_SETTINGS,
)
from apps.organization.models import SystemSetting


PRELIMINARY_RIGHTS = (
    {
        "name": "Acceso",
        "description": (
            "Solicitar información sobre los datos personales tratados y "
            "la forma en que se utilizan."
        ),
    },
    {
        "name": "Rectificación",
        "description": (
            "Solicitar la corrección de datos inexactos o incompletos."
        ),
    },
    {
        "name": "Eliminación",
        "description": (
            "Solicitar la supresión de datos cuando se cumplan las "
            "condiciones aplicables."
        ),
    },
    {
        "name": "Oposición",
        "description": (
            "Oponerse a determinados tratamientos en los casos previstos "
            "por la normativa."
        ),
    },
)

PROVISIONAL_DPD_NAME = "María Elena Terán"


@never_cache
@login_required
@require_GET
def dashboard_summary(request):
    try:
        snapshot = CaseDashboardService.snapshot(user=request.user)
    except DashboardPermissionError:
        raise PermissionDenied
    return JsonResponse(
        snapshot,
        json_dumps_params={"ensure_ascii": False},
    )


@never_cache
@login_required
@require_GET
def dashboard(request):
    try:
        snapshot = CaseDashboardService.snapshot(user=request.user)
    except DashboardPermissionError:
        raise PermissionDenied
    return render(request, "core/dashboard.html", {"dashboard": snapshot})


def _report_payload(request):
    if not can_access_case_panel(request.user):
        raise PermissionDenied
    form = CaseReportFilterForm(request.GET)
    if not form.is_valid():
        return None, JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    try:
        payload = CaseReportService.build(
            user=request.user,
            filters=form.cleaned_data,
        )
    except ReportPermissionError:
        raise PermissionDenied
    return payload, None


@never_cache
@login_required
@require_GET
def report_summary(request):
    payload, error = _report_payload(request)
    if error:
        return error
    return JsonResponse(
        payload,
        json_dumps_params={"ensure_ascii": False},
    )


def _report_page_context(request, *, report):
    visible_cases = visible_requests_for(request.user)
    return {
        "filter_form": CaseReportFilterForm(request.GET),
        "report": report,
        "rights": RightCatalog.objects.filter(is_active=True).order_by(
            "name"
        ),
        "assignees": get_user_model().objects.filter(
            is_active=True,
            assigned_requests__in=visible_cases,
        ).distinct().order_by("full_name", "email"),
    }


@never_cache
@login_required
@require_GET
def reports(request):
    payload, error = _report_payload(request)
    if error:
        return render(
            request,
            "core/reports.html",
            _report_page_context(request, report=None),
            status=400,
        )
    return render(
        request,
        "core/reports.html",
        _report_page_context(request, report=payload),
    )


@never_cache
@login_required
@require_GET
def report_export_csv(request):
    payload, error = _report_payload(request)
    if error:
        return error
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="reporte-expedientes.csv"'
    )
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        (
            "Código del derecho",
            "Derecho",
            "Total",
            "Finalizados",
            "En proceso",
            "Pendientes",
            "% finalización",
        )
    )
    for row in payload["by_right"]:
        writer.writerow(
            (
                row["code"],
                row["name"],
                row["total"],
                row["finalized"],
                row["in_process"],
                row["pending"],
                row["completion_percentage"],
            )
        )
    return response


@require_GET
def home(request):
    rights = list(
        RightCatalog.objects.filter(is_active=True).order_by("code")
    )
    return render(
        request,
        "core/home.html",
        {"rights": rights or PRELIMINARY_RIGHTS},
    )


@require_GET
def rights(request):
    return render(
        request,
        "core/rights.html",
        {
            "rights": RightCatalog.objects.filter(is_active=True).order_by(
                "code"
            ),
            "preliminary_rights": PRELIMINARY_RIGHTS,
        },
    )


@require_GET
def contact(request):
    return render(
        request,
        "core/contact.html",
        {
            "settings": SystemSetting.objects.first(),
            "provisional_settings": VINESA_SYSTEM_SETTINGS,
            "privacy_policy_url": VINESA_PRIVACY_POLICY_URL,
            "provisional_dpd_name": PROVISIONAL_DPD_NAME,
        },
    )
