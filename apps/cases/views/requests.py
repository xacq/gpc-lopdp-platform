from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from apps.cases.forms.requests import RequestAssignForm
from apps.cases.models import RightsRequest
from apps.cases.policies import (
    can_access_case_panel,
    can_assign_case,
    can_start_review,
    can_view_sensitive_case_data,
    visible_requests_for,
)
from apps.cases.services.cases import (
    CaseWorkflowError,
    CaseWorkflowService,
)
from apps.subjects.services.subjects import RepresentativeService


def _case_queryset():
    return (
        RightsRequest.objects
        .select_related(
            "right",
            "assigned_to",
            "representative",
        )
        .prefetch_related(
            "status_history",
            "deadlines",
            "clarifications",
        )
    )


def _visible_case_or_404(*, user, request_id) -> RightsRequest:
    queryset = visible_requests_for(
        user,
        _case_queryset(),
    )

    return get_object_or_404(
        queryset,
        pk=request_id,
    )


@login_required
@require_GET
def request_list(request):
    if not can_access_case_panel(request.user):
        raise PermissionDenied

    cases = (
        visible_requests_for(
            request.user,
            _case_queryset(),
        )
        .order_by(
            "-received_at",
            "-created_at",
        )
    )

    return render(
        request,
        "cases/request_list.html",
        {"cases": cases},
    )


@login_required
@require_GET
def request_detail(request, request_id):
    if not can_access_case_panel(request.user):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    sensitive_data = can_view_sensitive_case_data(
        request.user,
        case,
    )

    subject_snapshot = None
    request_details = None
    representative_pii = None

    if sensitive_data:
        subject_snapshot = (
            CaseWorkflowService
            .decrypt_subject_snapshot(case)
        )
        request_details = (
            CaseWorkflowService
            .decrypt_request_details(case)
        )
        if case.representative is not None:
            representative_pii = (
                RepresentativeService
                .decrypt(case.representative)
            )

    return render(
        request,
        "cases/request_detail.html",
        {
            "case": case,
            "sensitive_data": sensitive_data,
            "subject_snapshot": subject_snapshot,
            "request_details": request_details,
            "representative_pii": representative_pii,
            "can_assign": can_assign_case(request.user),
            "can_start_review": (
                can_start_review(request.user, case)
                and case.status
                == RightsRequest.Status.RECEIVED
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def request_assign(request, request_id):
    if not can_assign_case(request.user):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if request.method == "POST":
        form = RequestAssignForm(request.POST)

        if form.is_valid():
            try:
                CaseWorkflowService.assign(
                    request=case,
                    assignee=form.cleaned_data["assignee"],
                    actor=request.user,
                )
            except CaseWorkflowError:
                form.add_error(
                    None,
                    "No fue posible asignar el expediente.",
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = RequestAssignForm(
            initial={
                "assignee": case.assigned_to_id,
            }
        )

    return render(
        request,
        "cases/request_assign.html",
        {
            "case": case,
            "form": form,
        },
    )


@login_required
@require_POST
def request_start_review(request, request_id):
    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if not can_start_review(request.user, case):
        raise PermissionDenied

    try:
        CaseWorkflowService.transition(
            request=case,
            target_status=RightsRequest.Status.UNDER_REVIEW,
            actor=request.user,
        )
    except CaseWorkflowError:
        return HttpResponseBadRequest(
            "No fue posible iniciar la revisión."
        )

    return redirect(
        "cases:request_detail",
        request_id=case.pk,
    )
