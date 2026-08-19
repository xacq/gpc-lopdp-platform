from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.cases.policies import can_assign_case
from apps.retention.forms import RetentionEventFilterForm
from apps.retention.models import DataDisposalEvent
from apps.retention.services.query import (
    RetentionQueryPermissionError,
    RetentionQueryService,
)
from apps.retention.services.retention import (
    RetentionService,
    RetentionServiceError,
)


def _require_manager(user):
    if not can_assign_case(user):
        raise PermissionDenied


def _event(event_id):
    try:
        return DataDisposalEvent.objects.get(pk=event_id)
    except DataDisposalEvent.DoesNotExist:
        raise Http404


@never_cache
@login_required
@require_GET
def retention_summary(request):
    _require_manager(request.user)
    try:
        payload = RetentionQueryService.summary(user=request.user)
    except RetentionQueryPermissionError:
        raise PermissionDenied
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def retention_event_list(request):
    _require_manager(request.user)
    form = RetentionEventFilterForm(request.GET)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    payload = RetentionQueryService.list(
        user=request.user, filters=form.cleaned_data
    )
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


def _transition(request, event_id, operation):
    _require_manager(request.user)
    try:
        changed = operation(event=_event(event_id), actor=request.user)
    except RetentionServiceError:
        return JsonResponse(
            {"error": "La transición solicitada no es válida."}, status=409
        )
    return JsonResponse(RetentionQueryService.serialize(changed))


@never_cache
@login_required
@require_POST
def retention_event_approve(request, event_id):
    return _transition(request, event_id, RetentionService.approve)


@never_cache
@login_required
@require_POST
def retention_event_reject(request, event_id):
    return _transition(request, event_id, RetentionService.reject)


@never_cache
@login_required
@require_POST
def retention_event_retry(request, event_id):
    return _transition(request, event_id, RetentionService.retry_failed)
