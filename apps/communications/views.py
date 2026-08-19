import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.cases.models import RightsRequest
from apps.cases.policies import (
    can_access_case_panel,
    can_start_review,
    visible_requests_for,
)
from apps.communications.forms import (
    CommunicationFilterForm,
    InboundCommunicationForm,
    OutboundCommunicationForm,
)
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import (
    NotificationService,
    NotificationServiceError,
)
from apps.communications.services.query import (
    CommunicationPermissionError,
    CommunicationQueryService,
)


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
