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
from apps.core.manuals import (
    MANUALS,
    get_manual,
    read_manual_markdown,
    render_manual_markdown,
)
from apps.legal_content.models import RightCatalog
from apps.organization.defaults import (
    VINESA_SYSTEM_SETTINGS,
)
from apps.organization.models import SystemSetting


PUBLIC_RIGHT_CODES = (
    "ACCESS",
    "RECTIFICATION_UPDATE",
    "ELIMINATION",
    "OPPOSITION",
)
PUBLIC_RIGHT_ORDER = {
    code: index for index, code in enumerate(PUBLIC_RIGHT_CODES)
}

PRELIMINARY_RIGHTS = (
    {
        "name": "Acceso",
        "description": (
            "Conocer qué datos suyos tiene la organización, "
            "para qué los usa y con quién los comparte."
        ),
        "legal_reference": "LOPDP, art. 19",
    },
    {
        "name": "Rectificación",
        "description": (
            "Solicitar la corrección de datos incorrectos, "
            "incompletos o desactualizados."
        ),
        "legal_reference": "LOPDP, art. 20",
    },
    {
        "name": "Eliminación",
        "description": (
            "Pedir la eliminación de sus datos cuando ya no sean "
            "necesarios o el tratamiento carezca de base legal."
        ),
        "legal_reference": "LOPDP, art. 21",
    },
    {
        "name": "Oposición",
        "description": (
            "Oponerse al tratamiento de sus datos, especialmente "
            "para fines de mercadotecnia directa."
        ),
        "legal_reference": "LOPDP, art. 22",
    },
)

PROVISIONAL_DPD_NAME = "María Elena Terán"


def _public_rights():
    rights = RightCatalog.objects.filter(
        code__in=PUBLIC_RIGHT_CODES,
        is_active=True,
    )
    return sorted(
        rights,
        key=lambda right: PUBLIC_RIGHT_ORDER.get(right.code, 99),
    )


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
def manuals(request):
    if not can_access_case_panel(request.user):
        raise PermissionDenied
    current_manual = get_manual(request.GET.get("manual"))
    manual_markdown = read_manual_markdown(current_manual)
    return render(
        request,
        "core/manuals.html",
        {
            "manuals": MANUALS,
            "current_manual": current_manual,
            "manual_html": render_manual_markdown(manual_markdown),
        },
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
    rights = _public_rights()
    return render(
        request,
        "core/home.html",
        {"rights": rights or PRELIMINARY_RIGHTS},
    )


@require_GET
def rights(request):
    rights = _public_rights()
    return render(
        request,
        "core/rights.html",
        {
            "rights": rights,
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
            "provisional_dpd_name": PROVISIONAL_DPD_NAME,
        },
    )
