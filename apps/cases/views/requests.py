from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
)
from django.http import (
    HttpResponseBadRequest,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from apps.accounts.decorators import (
    sensitive_reauthentication_required,
)
from apps.cases.forms.requests import (
    RequestAssignForm,
    RequestClarificationForm,
    RequestClarificationReceiveForm,
    RequestCreateForm,
    RequestExtensionForm,
    RequestResolutionForm,
)
from apps.cases.models import (
    RequestClarification,
    RightsRequest,
)
from apps.cases.policies import (
    can_access_case_panel,
    can_assign_case,
    can_create_case,
    can_start_review,
    can_view_sensitive_case_data,
    visible_requests_for,
)
from apps.cases.services.cases import (
    CasePermissionError,
    CaseWorkflowError,
    CaseWorkflowService,
)
from apps.cases.services.deadlines import (
    DeadlineServiceError,
)
from apps.cases.services.intake import (
    CaseIntakeError,
    CaseIntakeService,
)
from apps.cases.services.resolutions import (
    ResolutionService,
    ResolutionServiceError,
)
from apps.subjects.services.subjects import (
    RepresentativeService,
    SubjectServiceError,
)


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


def _visible_case_or_404(
    *,
    user,
    request_id,
) -> RightsRequest:
    queryset = (
        visible_requests_for(
            user,
            _case_queryset(),
        )
    )

    return get_object_or_404(
        queryset,
        pk=request_id,
    )


@login_required
@require_GET
def request_list(request):
    if not can_access_case_panel(
        request.user
    ):
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
        {
            "cases": cases,
            "can_create": (
                can_create_case(
                    request.user
                )
            ),
        },
    )


@login_required
@require_http_methods(
    ["GET", "POST"]
)
def request_create(request):
    if not can_create_case(
        request.user
    ):
        raise PermissionDenied

    if request.method == "POST":
        form = RequestCreateForm(
            request.POST
        )

        if form.is_valid():
            cleaned = form.cleaned_data

            try:
                case = (
                    CaseIntakeService
                    .create_administrative_request(
                        subject_type=(
                            cleaned[
                                "subject_type"
                            ]
                        ),
                        document_type=(
                            cleaned[
                                "document_type"
                            ]
                        ),
                        document_number=(
                            cleaned[
                                "document_number"
                            ]
                        ),
                        full_name=(
                            cleaned[
                                "full_name"
                            ]
                        ),
                        email=(
                            cleaned["email"]
                        ),
                        phone=(
                            cleaned.get(
                                "phone"
                            )
                        ),
                        right=(
                            cleaned["right"]
                        ),
                        request_details=(
                            cleaned[
                                "request_details"
                            ]
                        ),
                        source_channel=(
                            cleaned[
                                "source_channel"
                            ]
                        ),
                        actor=request.user,
                        representative_name=(
                            cleaned.get(
                                "representative_name"
                            )
                        ),
                        representative_document_type=(
                            cleaned.get(
                                "representative_document_type"
                            )
                        ),
                        representative_document_number=(
                            cleaned.get(
                                "representative_document_number"
                            )
                        ),
                        representative_email=(
                            cleaned.get(
                                "representative_email"
                            )
                        ),
                    )
                )
            except (
                CaseIntakeError,
                CaseWorkflowError,
                SubjectServiceError,
                ValueError,
            ):
                form.add_error(
                    None,
                    (
                        "No fue posible registrar "
                        "la solicitud. Verifique "
                        "los datos del titular, "
                        "representante y derecho."
                    ),
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = RequestCreateForm()

    return render(
        request,
        "cases/request_form.html",
        {
            "form": form,
        },
    )


@login_required
@require_GET
def request_detail(
    request,
    request_id,
):
    if not can_access_case_panel(
        request.user
    ):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    sensitive_data = (
        can_view_sensitive_case_data(
            request.user,
            case,
        )
    )

    subject_snapshot = None
    request_details = None
    representative_pii = None

    if sensitive_data:
        subject_snapshot = (
            CaseWorkflowService
            .decrypt_subject_snapshot(
                case
            )
        )

        request_details = (
            CaseWorkflowService
            .decrypt_request_details(
                case
            )
        )

        if (
            case.representative
            is not None
        ):
            representative_pii = (
                RepresentativeService
                .decrypt(
                    case.representative
                )
            )

    return render(
        request,
        "cases/request_detail.html",
        {
            "case": case,
            "sensitive_data": (
                sensitive_data
            ),
            "subject_snapshot": (
                subject_snapshot
            ),
            "request_details": (
                request_details
            ),
            "representative_pii": (
                representative_pii
            ),
            "can_assign": (
                can_assign_case(
                    request.user
                )
            ),
            "can_start_review": (
                can_start_review(
                    request.user,
                    case,
                )
                and case.status
                == RightsRequest
                .Status
                .RECEIVED
            ),
        },
    )


@login_required
@require_http_methods(
    ["GET", "POST"]
)
def request_assign(
    request,
    request_id,
):
    if not can_assign_case(
        request.user
    ):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if request.method == "POST":
        form = RequestAssignForm(
            request.POST
        )

        if form.is_valid():
            try:
                CaseWorkflowService.assign(
                    request=case,
                    assignee=(
                        form.cleaned_data[
                            "assignee"
                        ]
                    ),
                    actor=request.user,
                )
            except CaseWorkflowError:
                form.add_error(
                    None,
                    (
                        "No fue posible "
                        "asignar el expediente."
                    ),
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = RequestAssignForm(
            initial={
                "assignee": (
                    case.assigned_to_id
                ),
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
def request_start_review(
    request,
    request_id,
):
    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if not can_start_review(
        request.user,
        case,
    ):
        raise PermissionDenied

    try:
        CaseWorkflowService.transition(
            request=case,
            target_status=(
                RightsRequest
                .Status
                .UNDER_REVIEW
            ),
            actor=request.user,
        )
    except CaseWorkflowError:
        return HttpResponseBadRequest(
            (
                "No fue posible iniciar "
                "la revisión."
            )
        )

    return redirect(
        "cases:request_detail",
        request_id=case.pk,
    )


@login_required
@require_http_methods(
    ["GET", "POST"]
)
def request_clarification_create(
    request,
    request_id,
):
    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if request.method == "POST":
        form = RequestClarificationForm(
            request.POST
        )

        if form.is_valid():
            try:
                (
                    CaseWorkflowService
                    .request_clarification(
                        request=case,
                        message=(
                            form.cleaned_data[
                                "message"
                            ]
                        ),
                        clarification_due_at=(
                            form.cleaned_data.get(
                                "clarification_due_at"
                            )
                        ),
                        legal_basis=(
                            form.cleaned_data.get(
                                "legal_basis"
                            )
                        ),
                        actor=request.user,
                    )
                )
            except CasePermissionError:
                raise PermissionDenied
            except (
                CaseWorkflowError,
                DeadlineServiceError,
                ValueError,
            ):
                form.add_error(
                    None,
                    (
                        "No fue posible solicitar "
                        "la aclaración. Verifique "
                        "el estado del expediente, "
                        "el plazo y la base jurídica."
                    ),
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = RequestClarificationForm()

    return render(
        request,
        (
            "cases/"
            "request_clarification_form.html"
        ),
        {
            "case": case,
            "form": form,
        },
    )


@login_required
@require_http_methods(
    ["GET", "POST"]
)
def request_clarification_receive(
    request,
    request_id,
    clarification_id,
):
    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    clarification = get_object_or_404(
        (
            RequestClarification
            .objects
            .select_related("request")
        ),
        pk=clarification_id,
        request_id=case.pk,
    )

    if request.method == "POST":
        form = (
            RequestClarificationReceiveForm(
                request.POST
            )
        )

        if form.is_valid():
            try:
                (
                    CaseWorkflowService
                    .receive_clarification(
                        clarification=(
                            clarification
                        ),
                        response_message=(
                            form.cleaned_data[
                                "response_message"
                            ]
                        ),
                        actor=request.user,
                    )
                )
            except CasePermissionError:
                raise PermissionDenied
            except (
                CaseWorkflowError,
                DeadlineServiceError,
                ValueError,
            ):
                form.add_error(
                    None,
                    (
                        "No fue posible registrar "
                        "la respuesta de la "
                        "aclaración. Verifique "
                        "el estado actual."
                    ),
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = (
            RequestClarificationReceiveForm()
        )

    return render(
        request,
        (
            "cases/"
            "request_clarification_receive.html"
        ),
        {
            "case": case,
            "clarification": clarification,
            "form": form,
        },
    )


@login_required
@require_http_methods(
    ["GET", "POST"]
)
def request_extension(
    request,
    request_id,
):
    # La matriz baseline permite extensiones a los
    # mismos roles administrativos que pueden asignar:
    # ADMIN, DPD y RESPONSABLE. La validación de dominio
    # se mantiene además dentro de CaseWorkflowService.
    if not can_assign_case(
        request.user
    ):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if request.method == "POST":
        form = RequestExtensionForm(
            request.POST
        )

        if form.is_valid():
            try:
                (
                    CaseWorkflowService
                    .apply_extension(
                        request=case,
                        reason=(
                            form.cleaned_data[
                                "reason"
                            ]
                        ),
                        actor=request.user,
                    )
                )
            except CasePermissionError:
                raise PermissionDenied
            except (
                CaseWorkflowError,
                DeadlineServiceError,
                ValueError,
            ):
                form.add_error(
                    None,
                    (
                        "No fue posible aplicar "
                        "la extensión. Verifique "
                        "el estado del expediente, "
                        "la regla del derecho y "
                        "el plazo activo."
                    ),
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = RequestExtensionForm()

    return render(
        request,
        "cases/request_extension_form.html",
        {
            "case": case,
            "form": form,
        },
    )


@login_required
@sensitive_reauthentication_required
@require_http_methods(
    ["GET", "POST"]
)
def request_resolution(
    request,
    request_id,
):
    # Resolución es una acción administrativa sensible.
    if not can_assign_case(
        request.user
    ):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    if request.method == "POST":
        form = RequestResolutionForm(
            request.POST
        )

        if form.is_valid():
            try:
                ResolutionService.resolve(
                    request=case,
                    resolution_type=(
                        form.cleaned_data[
                            "resolution_type"
                        ]
                    ),
                    details=(
                        form.cleaned_data[
                            "details"
                        ]
                    ),
                    outcome_reason=(
                        form.cleaned_data.get(
                            "outcome_reason"
                        )
                    ),
                    legal_basis=(
                        form.cleaned_data.get(
                            "legal_basis"
                        )
                    ),
                    actor=request.user,
                )
            except CasePermissionError:
                raise PermissionDenied
            except (
                ResolutionServiceError,
                CaseWorkflowError,
                DeadlineServiceError,
                ValueError,
            ):
                form.add_error(
                    None,
                    (
                        "No fue posible registrar "
                        "la resolución. Verifique "
                        "el estado del expediente, "
                        "el tipo de resolución y "
                        "la causal seleccionada."
                    ),
                )
            else:
                return redirect(
                    "cases:request_detail",
                    request_id=case.pk,
                )
    else:
        form = RequestResolutionForm()

    return render(
        request,
        "cases/request_resolution_form.html",
        {
            "case": case,
            "form": form,
        },
    )


@login_required
@require_POST
def request_mark_responded(
    request,
    request_id,
):
    if not can_assign_case(
        request.user
    ):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    try:
        ResolutionService.mark_responded(
            request=case,
            actor=request.user,
        )
    except CasePermissionError:
        raise PermissionDenied
    except (
        ResolutionServiceError,
        CaseWorkflowError,
        DeadlineServiceError,
        ValueError,
    ):
        return HttpResponseBadRequest(
            (
                "No fue posible marcar "
                "el expediente como respondido."
            )
        )

    return redirect(
        "cases:request_detail",
        request_id=case.pk,
    )


@login_required
@sensitive_reauthentication_required
@require_POST
def request_close(
    request,
    request_id,
):
    if not can_assign_case(
        request.user
    ):
        raise PermissionDenied

    case = _visible_case_or_404(
        user=request.user,
        request_id=request_id,
    )

    try:
        ResolutionService.close(
            request=case,
            actor=request.user,
        )
    except CasePermissionError:
        raise PermissionDenied
    except (
        ResolutionServiceError,
        CaseWorkflowError,
        DeadlineServiceError,
        ValueError,
    ):
        return HttpResponseBadRequest(
            (
                "No fue posible cerrar "
                "el expediente."
            )
        )

    return redirect(
        "cases:request_detail",
        request_id=case.pk,
    )
