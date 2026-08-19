import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.cases.forms.assignments import (
    AssignmentHistoryFilterForm,
    AssignmentListFilterForm,
)
from apps.cases.policies import can_assign_case
from apps.cases.services.assignments import (
    AssignmentPermissionError,
    AssignmentService,
    AssignmentValidationError,
)
from apps.cases.services.cases import CaseWorkflowError
from apps.legal_content.models import RightCatalog


def _errors(form):
    return JsonResponse(
        {"errors": form.errors.get_json_data()},
        status=400,
        json_dumps_params={"ensure_ascii": False},
    )


def _require_assignment_access(request):
    if not can_assign_case(request.user):
        raise PermissionDenied


@never_cache
@login_required
@require_GET
def assignment_index(request):
    _require_assignment_access(request)
    form = AssignmentListFilterForm(request.GET)
    if not form.is_valid():
        return render(
            request,
            "cases/assignment_index.html",
            {"filter_form": form, "summary": None, "assignment_list": None},
            status=400,
        )
    try:
        summary = AssignmentService.summary(user=request.user)
        assignment_list = AssignmentService.list_requests(
            user=request.user,
            filters=form.cleaned_data,
        )
    except AssignmentPermissionError:
        raise PermissionDenied
    return render(
        request,
        "cases/assignment_index.html",
        {
            "filter_form": form,
            "summary": summary,
            "assignment_list": assignment_list,
            "rights": RightCatalog.objects.filter(is_active=True).order_by(
                "name"
            ),
        },
    )


@never_cache
@login_required
@require_GET
def assignment_summary(request):
    _require_assignment_access(request)
    try:
        payload = AssignmentService.summary(user=request.user)
    except AssignmentPermissionError:
        raise PermissionDenied
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def assignment_request_list(request):
    _require_assignment_access(request)
    form = AssignmentListFilterForm(request.GET)
    if not form.is_valid():
        return _errors(form)
    payload = AssignmentService.list_requests(
        user=request.user,
        filters=form.cleaned_data,
    )
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def assignment_history(request):
    _require_assignment_access(request)
    form = AssignmentHistoryFilterForm(request.GET)
    if not form.is_valid():
        return _errors(form)
    payload = AssignmentService.history(
        user=request.user,
        filters=form.cleaned_data,
    )
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_POST
def assignment_apply(request):
    _require_assignment_access(request)
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "El cuerpo JSON no es válido."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "El cuerpo JSON debe ser un objeto."}, status=400
        )
    try:
        payload = AssignmentService.assign_many(
            user=request.user,
            request_ids=data.get("request_ids"),
            assignee_id=data.get("assignee_id"),
        )
    except AssignmentPermissionError:
        raise PermissionDenied
    except AssignmentValidationError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    except CaseWorkflowError:
        return JsonResponse(
            {"error": "No fue posible completar la asignación solicitada."},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
