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
    can_assign_case,
    can_start_review,
    visible_requests_for,
)
from apps.communications.forms import (
    CommunicationFilterForm,
    InboundCommunicationForm,
    OutboundCommunicationForm,
    PortabilityDownloadForm,
    PortabilityGenerateForm,
)
from apps.communications.models import PortabilityExport, RequestCommunication
from apps.communications.services.notifications import (
    NotificationService,
    NotificationServiceError,
)
from apps.communications.services.query import (
    CommunicationPermissionError,
    CommunicationQueryService,
)
from apps.communications.services.portability import (
    PortabilityService,
    PortabilityServiceError,
)
from apps.core.services.crypto import CryptoError
from apps.subjects.services.subjects import SubjectService


def _json_form(form_class, request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse(
            {"error": "El cuerpo JSON no es válido."}, status=400
        )
    if not isinstance(data, dict):
        return None, JsonResponse(
            {"error": "El cuerpo JSON debe ser un objeto."}, status=400
        )
    form = form_class(data)
    if not form.is_valid():
        return None, JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    return form.cleaned_data, None


def _require_panel(user):
    if not can_access_case_panel(user):
        raise PermissionDenied


def _manageable_case(user, request_id):
    case = visible_requests_for(user, RightsRequest.objects.all()).filter(
        pk=request_id
    ).first()
    if case is None:
        raise Http404
    if not can_start_review(user, case):
        raise PermissionDenied
    return case


def _manageable_cases_with_recipient_email(user):
    cases = []
    queryset = (
        visible_requests_for(user)
        .select_related("right", "data_subject")
        .order_by("-received_at", "-id")
    )
    for case in queryset:
        if not can_start_review(user, case):
            continue
        recipient_email = ""
        try:
            recipient_email = SubjectService.decrypt(case.data_subject).email
        except CryptoError:
            recipient_email = ""
        case.subject_email = recipient_email
        cases.append(case)
    return cases


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def communication_panel(request):
    _require_panel(request.user)
    manageable_cases = _manageable_cases_with_recipient_email(request.user)
    if request.method == "POST":
        mode = request.POST.get("mode")
        form_class = (
            OutboundCommunicationForm
            if mode == "outbound"
            else InboundCommunicationForm
        )
        create_form = form_class(request.POST)
        if create_form.is_valid():
            data = create_form.cleaned_data
            case = _manageable_case(request.user, data["request_id"])
            try:
                if mode == "outbound":
                    NotificationService.queue_email(
                        request=case,
                        communication_type=data["communication_type"],
                        recipient=data["recipient"],
                        subject=data["subject"],
                        body=data["body"],
                        visible_to_subject=data["visible_to_subject"],
                        actor=request.user,
                    )
                else:
                    NotificationService.record_inbound(
                        request=case,
                        channel=data["channel"],
                        communication_type=data["communication_type"],
                        contact=data["contact"],
                        subject=data["subject"],
                        body=data["body"],
                        visible_to_subject=data["visible_to_subject"],
                        actor=request.user,
                    )
            except (NotificationServiceError, ValueError):
                create_form.add_error(
                    None, "No fue posible registrar la comunicación."
                )
            else:
                messages.success(request, "La comunicación fue registrada.")
                return redirect("communications:panel")
    else:
        mode = None
        create_form = None
    filter_form = CommunicationFilterForm(request.GET)
    if filter_form.is_valid():
        communication_list = CommunicationQueryService.list(
            user=request.user, filters=filter_form.cleaned_data
        )
    else:
        communication_list = None
    return render(
        request,
        "communications/panel.html",
        {
            "summary": CommunicationQueryService.summary(user=request.user),
            "communication_list": communication_list,
            "filter_form": filter_form,
            "manageable_cases": manageable_cases,
            "create_form": create_form,
            "create_mode": mode,
            "communication_types": RequestCommunication.CommunicationType.choices,
            "channels": RequestCommunication.Channel.choices,
        },
        status=400 if create_form is not None and create_form.errors else 200,
    )


@never_cache
@login_required
@require_GET
def communication_summary(request):
    _require_panel(request.user)
    try:
        payload = CommunicationQueryService.summary(user=request.user)
    except CommunicationPermissionError:
        raise PermissionDenied
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def communication_list(request):
    _require_panel(request.user)
    form = CommunicationFilterForm(request.GET)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    payload = CommunicationQueryService.list(
        user=request.user, filters=form.cleaned_data
    )
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def communication_detail(request, communication_id):
    _require_panel(request.user)
    try:
        payload = CommunicationQueryService.detail(
            user=request.user, communication_id=communication_id
        )
    except RequestCommunication.DoesNotExist:
        raise Http404
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_POST
def communication_create_outbound(request):
    _require_panel(request.user)
    data, error = _json_form(OutboundCommunicationForm, request)
    if error:
        return error
    case = _manageable_case(request.user, data["request_id"])
    try:
        communication = NotificationService.queue_email(
            request=case,
            communication_type=data["communication_type"],
            recipient=data["recipient"],
            subject=data["subject"],
            body=data["body"],
            visible_to_subject=data["visible_to_subject"],
            actor=request.user,
            idempotency_key=data.get("idempotency_key"),
        )
    except (NotificationServiceError, ValueError):
        return JsonResponse(
            {"error": "No fue posible registrar la comunicación."}, status=400
        )
    return JsonResponse({"id": str(communication.id)}, status=201)


@never_cache
@login_required
@require_POST
def communication_create_inbound(request):
    _require_panel(request.user)
    data, error = _json_form(InboundCommunicationForm, request)
    if error:
        return error
    case = _manageable_case(request.user, data["request_id"])
    try:
        communication = NotificationService.record_inbound(
            request=case,
            channel=data["channel"],
            communication_type=data["communication_type"],
            contact=data["contact"],
            subject=data["subject"],
            body=data["body"],
            visible_to_subject=data["visible_to_subject"],
            actor=request.user,
            idempotency_key=data.get("idempotency_key"),
        )
    except (NotificationServiceError, ValueError):
        return JsonResponse(
            {"error": "No fue posible registrar la comunicación."}, status=400
        )
    return JsonResponse({"id": str(communication.id)}, status=201)


def _portability_payload(item):
    return {
        "id": str(item.id),
        "request_id": str(item.request_id),
        "reference_number": item.request.reference_number,
        "export_format": item.export_format,
        "generated_at": item.generated_at,
        "expires_at": item.expires_at,
        "downloaded_at": item.downloaded_at,
        "revoked_at": item.revoked_at,
        "available": (
            item.revoked_at is None and item.downloaded_at is None
        ),
    }


@never_cache
@login_required
@require_GET
def portability_export_list(request):
    _require_panel(request.user)
    queryset = PortabilityExport.objects.filter(
        request__in=visible_requests_for(request.user)
    ).select_related("request").order_by("-generated_at", "-id")
    return JsonResponse(
        {"results": [_portability_payload(item) for item in queryset]},
        json_dumps_params={"ensure_ascii": False},
    )


@never_cache
@login_required
@require_POST
def portability_generate(request):
    if not can_assign_case(request.user):
        raise PermissionDenied
    data, error = _json_form(PortabilityGenerateForm, request)
    if error:
        return error
    case = _manageable_case(request.user, data["request_id"])
    try:
        generated = PortabilityService.generate(
            request=case,
            export_format=data["export_format"],
            actor=request.user,
        )
    except (PortabilityServiceError, ValueError):
        return JsonResponse(
            {"error": "No fue posible generar la exportación de portabilidad."},
            status=409,
        )
    payload = _portability_payload(generated.export)
    payload["download_token"] = generated.download_token
    return JsonResponse(payload, status=201)


@never_cache
@require_POST
def portability_download(request):
    form = PortabilityDownloadForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"error": "La exportación o el código no son válidos."}, status=400
        )
    export = PortabilityExport.objects.filter(
        pk=form.cleaned_data["export_id"]
    ).first()
    if export is None:
        raise Http404
    try:
        download = PortabilityService.download(
            export=export, token=form.cleaned_data["token"]
        )
    except PortabilityServiceError:
        raise Http404
    response = HttpResponse(download.content, content_type=download.content_type)
    response["Content-Disposition"] = content_disposition_header(
        True, download.filename
    )
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
@require_POST
def portability_revoke(request, export_id):
    if not can_assign_case(request.user):
        raise PermissionDenied
    export = PortabilityExport.objects.filter(
        pk=export_id,
        request__in=visible_requests_for(request.user),
    ).first()
    if export is None:
        raise Http404
    try:
        export = PortabilityService.revoke(export=export, actor=request.user)
    except PortabilityServiceError:
        return JsonResponse(
            {"error": "La exportación no puede revocarse."}, status=409
        )
    export = PortabilityExport.objects.select_related("request").get(pk=export.pk)
    return JsonResponse(_portability_payload(export))
