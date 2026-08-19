import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.audit.forms import AuditEventFilterForm, AuditIntegrityForm
from apps.audit.policies import can_read_audit
from apps.audit.services.audit import AuditChainIntegrityError, AuditService
from apps.audit.services.query import (
    AuditQueryPermissionError,
    AuditQueryService,
)


def _validated_filters(request):
    if not can_read_audit(request.user):
        raise PermissionDenied
    form = AuditEventFilterForm(request.GET)
    if not form.is_valid():
        return None, JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    return form.cleaned_data, None


@never_cache
@login_required
@require_GET
def audit_event_list(request):
    filters, error = _validated_filters(request)
    if error is not None:
        return error
    try:
        payload = AuditQueryService.search(user=request.user, filters=filters)
    except AuditQueryPermissionError:
        raise PermissionDenied
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def audit_event_detail(request, event_id):
    if not can_read_audit(request.user):
        raise PermissionDenied
    try:
        payload = AuditQueryService.detail(
            user=request.user,
            event_id=event_id,
        )
    except AuditQueryPermissionError:
        raise PermissionDenied
    if payload is None:
        return JsonResponse({"detail": "No encontrado."}, status=404)
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@never_cache
@login_required
@require_GET
def audit_export_csv(request):
    filters, error = _validated_filters(request)
    if error is not None:
        return error
    try:
        events, export_limit = AuditQueryService.export(
            user=request.user,
            filters=filters,
        )
    except AuditQueryPermissionError:
        raise PermissionDenied
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="auditoria.csv"'
    response["X-Export-Limit"] = str(export_limit)
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        (
            "Fecha y hora",
            "Actor",
            "Acción",
            "Entidad",
            "ID entidad",
            "Origen",
            "Correlation ID",
            "Cadena",
            "Posición",
        )
    )
    for event in events:
        writer.writerow(
            (
                event["created_at"].isoformat(),
                event["actor"]["name"],
                event["action"],
                event["entity_type"],
                event["entity_pk"],
                event["source"],
                event["correlation_id"],
                event["chain_scope"],
                event["chain_position"],
            )
        )
    return response


@never_cache
@login_required
@require_GET
def audit_integrity(request):
    if not can_read_audit(request.user):
        raise PermissionDenied
    form = AuditIntegrityForm(request.GET)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    chain_scope = form.cleaned_data["chain_scope"]
    try:
        result = AuditService.verify_chain(chain_scope=chain_scope)
    except AuditChainIntegrityError as exc:
        return JsonResponse(
            {
                "valid": False,
                "chain_scope": exc.chain_scope,
                "chain_position": exc.chain_position,
            },
            status=409,
        )
    return JsonResponse(
        {
            "valid": True,
            "chain_scope": result.chain_scope,
            "checked_entries": result.checked_entries,
        }
    )
