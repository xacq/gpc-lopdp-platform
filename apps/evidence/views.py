import json

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.cases.models import RightsRequest
from apps.cases.policies import (
    can_access_case_panel,
    can_start_review,
    can_view_sensitive_case_data,
    visible_requests_for,
)
from apps.evidence.forms import (
    AttachmentFilterForm,
    IdentityVerificationCreateForm,
    IdentityVerificationFilterForm,
)
from apps.evidence.models import IdentityVerification, RequestAttachment
from apps.evidence.services.attachments import (
    AttachmentService,
    AttachmentServiceError,
)
from apps.evidence.services.identity import (
    IdentityVerificationError,
    IdentityVerificationService,
)


def _visible_case(user, request_id):
    case = visible_requests_for(user).filter(pk=request_id).first()
    if case is None:
        raise Http404
    return case


def _form_errors(form):
    return JsonResponse(
        {"errors": form.errors.get_json_data()},
        status=400,
        json_dumps_params={"ensure_ascii": False},
    )


def _json_form(form_class, request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "El cuerpo JSON no es válido."}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse(
            {"error": "El cuerpo JSON debe ser un objeto."}, status=400
        )
    form = form_class(data)
    if not form.is_valid():
        return None, _form_errors(form)
    return form.cleaned_data, None


def _identity_payload(item, user):
    may_read = can_view_sensitive_case_data(user, item.request)
    notes = None
    if may_read:
        notes = IdentityVerificationService.decrypt_notes(
            verification=item, actor=user
        )
    return {
        "id": str(item.id),
        "request_id": str(item.request_id),
        "verification_method": {
            "code": item.verification_method,
            "label": item.get_verification_method_display(),
        },
        "result": {"code": item.result, "label": item.get_result_display()},
        "validation_metadata": item.validation_metadata if may_read else None,
        "validation_notes": notes,
        "verified_by": (
            {"id": str(item.verified_by_id), "name": item.verified_by.full_name}
            if item.verified_by_id
            else None
        ),
        "verified_at": item.verified_at,
        "created_at": item.created_at,
        "can_view_sensitive": may_read,
    }


def _attachment_payload(item, *, may_read):
    return {
        "id": str(item.id),
        "attachment_type": {
            "code": item.attachment_type,
            "label": item.get_attachment_type_display(),
        },
        "visibility": item.visibility,
        "filename": AttachmentService.decrypt_filename(item) if may_read else None,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "malware_scan_status": {
            "code": item.malware_scan_status,
            "label": item.get_malware_scan_status_display(),
        },
        "uploaded_at": item.uploaded_at,
        "can_download": may_read,
    }


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def evidence_case_panel(request, request_id):
    if not can_access_case_panel(request.user):
        raise PermissionDenied
    case = _visible_case(request.user, request_id)
    can_record = can_start_review(request.user, case)
    form = None
    if request.method == "POST":
        if not can_record:
            raise PermissionDenied
        data = request.POST.copy()
        data["request_id"] = str(case.id)
        form = IdentityVerificationCreateForm(data)
        if form.is_valid():
            try:
                IdentityVerificationService.record(
                    request=case,
                    verification_method=form.cleaned_data["verification_method"],
                    result=form.cleaned_data["result"],
                    actor=request.user,
                    validation_notes=form.cleaned_data.get("validation_notes"),
                )
            except (IdentityVerificationError, ValueError, TypeError):
                form.add_error(None, "No fue posible registrar la verificación.")
            else:
                messages.success(request, "La verificación fue registrada.")
                return redirect("evidence:case_panel", request_id=case.id)
    identities = IdentityVerification.objects.filter(request=case).select_related(
        "request", "verified_by"
    ).order_by("-created_at", "-id")
    may_read = can_view_sensitive_case_data(request.user, case)
    attachments = RequestAttachment.objects.filter(
        request=case, deleted_at__isnull=True
    ).select_related("uploaded_by").order_by("-uploaded_at", "-id")
    return render(
        request,
        "evidence/case_panel.html",
        {
            "case": case,
            "can_record": can_record,
            "form": form,
            "identities": [_identity_payload(item, request.user) for item in identities],
            "attachments": [
                _attachment_payload(item, may_read=may_read) for item in attachments
            ],
            "verification_methods": IdentityVerification.VerificationMethod.choices,
            "verification_results": IdentityVerification.Result.choices,
        },
        status=400 if form is not None and form.errors else 200,
    )


@never_cache
@login_required
@require_GET
def identity_verification_list(request):
    if not can_access_case_panel(request.user):
        raise PermissionDenied
    form = IdentityVerificationFilterForm(request.GET)
    if not form.is_valid():
        return _form_errors(form)
    case = _visible_case(request.user, form.cleaned_data["request_id"])
    items = IdentityVerification.objects.filter(request=case).select_related(
        "request", "verified_by"
    ).order_by("-created_at", "-id")
    return JsonResponse(
        {"results": [_identity_payload(item, request.user) for item in items]},
        json_dumps_params={"ensure_ascii": False},
    )


@never_cache
@login_required
@require_POST
def identity_verification_create(request):
    if not can_access_case_panel(request.user):
        raise PermissionDenied
    data, error = _json_form(IdentityVerificationCreateForm, request)
    if error:
        return error
    case = _visible_case(request.user, data["request_id"])
    if not can_start_review(request.user, case):
        raise PermissionDenied
    try:
        verification = IdentityVerificationService.record(
            request=case,
            verification_method=data["verification_method"],
            result=data["result"],
            actor=request.user,
            validation_notes=data.get("validation_notes"),
        )
    except (IdentityVerificationError, ValueError, TypeError):
        return JsonResponse(
            {"error": "No fue posible registrar la verificación."}, status=409
        )
    verification = IdentityVerification.objects.select_related(
        "request", "verified_by"
    ).get(pk=verification.pk)
    return JsonResponse(_identity_payload(verification, request.user), status=201)


@never_cache
@login_required
@require_GET
def attachment_list(request):
    if not can_access_case_panel(request.user):
        raise PermissionDenied
    form = AttachmentFilterForm(request.GET)
    if not form.is_valid():
        return _form_errors(form)
    case = _visible_case(request.user, form.cleaned_data["request_id"])
    may_read = can_view_sensitive_case_data(request.user, case)
    items = RequestAttachment.objects.filter(
        request=case, deleted_at__isnull=True
    ).select_related("uploaded_by").order_by("-uploaded_at", "-id")
    return JsonResponse(
        {
            "results": [
                _attachment_payload(item, may_read=may_read)
                for item in items
            ]
        },
        json_dumps_params={"ensure_ascii": False},
    )


@never_cache
@login_required
@require_GET
def attachment_download(request, attachment_id):
    attachment = RequestAttachment.objects.select_related("request").filter(
        pk=attachment_id, deleted_at__isnull=True
    ).first()
    if attachment is None:
        raise Http404
    case = _visible_case(request.user, attachment.request_id)
    if not can_view_sensitive_case_data(request.user, case):
        raise PermissionDenied
    try:
        download = AttachmentService.download(
            attachment=attachment, actor=request.user
        )
    except AttachmentServiceError:
        raise Http404
    response = HttpResponse(download.content, content_type=download.mime_type)
    response["Content-Disposition"] = content_disposition_header(
        True, download.filename
    )
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
