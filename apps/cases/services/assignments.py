from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.cases.policies import can_assign_case
from apps.cases.services.cases import CaseWorkflowService
from apps.cases.services.dashboard import CaseDashboardService


class AssignmentPermissionError(Exception):
    pass


class AssignmentValidationError(Exception):
    pass


class AssignmentService:
    BULK_LIMIT = 100

    @classmethod
    def _require_permission(cls, user) -> None:
        if not can_assign_case(user):
            raise AssignmentPermissionError

    @classmethod
    def list_requests(cls, *, user, filters: dict) -> dict:
        cls._require_permission(user)
        queryset = RightsRequest.objects.select_related(
            "right", "assigned_to"
        ).order_by("-received_at", "-created_at")
        search = filters.get("search")
        if search:
            queryset = queryset.filter(reference_number__icontains=search)
        if filters.get("right_id"):
            queryset = queryset.filter(right_id=filters["right_id"])
        if filters.get("status"):
            queryset = queryset.filter(status=filters["status"])
        if filters.get("assigned_to"):
            queryset = queryset.filter(assigned_to_id=filters["assigned_to"])
        if filters.get("assignment_state") == "ASSIGNED":
            queryset = queryset.filter(assigned_to__isnull=False)
        elif filters.get("assignment_state") == "UNASSIGNED":
            queryset = queryset.filter(assigned_to__isnull=True)
        if filters.get("due_from"):
            queryset = queryset.filter(
                current_due_at__date__gte=filters["due_from"]
            )
        if filters.get("due_to"):
            queryset = queryset.filter(
                current_due_at__date__lte=filters["due_to"]
            )
        page_size = filters.get("page_size") or 20
        page = Paginator(queryset, page_size).get_page(filters.get("page") or 1)
        return {
            "pagination": cls._pagination(page, page_size),
            "results": [cls._serialize_request(item) for item in page.object_list],
        }

    @classmethod
    def summary(cls, *, user, generated_at=None) -> dict:
        cls._require_permission(user)
        generated_at = generated_at or timezone.now()
        active = RightsRequest.objects.filter(
            status__in=CaseDashboardService.ACTIVE_STATUSES
        )
        metrics = active.aggregate(
            active=Count("id"),
            assigned=Count("id", filter=Q(assigned_to__isnull=False)),
            unassigned=Count("id", filter=Q(assigned_to__isnull=True)),
            due_today=Count(
                "id",
                filter=Q(current_due_at__date=timezone.localdate(generated_at)),
            ),
        )
        today_logs = AuditLog.objects.filter(
            action="RIGHTS_REQUEST_ASSIGNED",
            entity_type="RIGHTS_REQUEST",
            created_at__date=timezone.localdate(generated_at),
        ).only("previous_values")
        metrics["reassigned_today"] = sum(
            1
            for entry in today_logs
            if (entry.previous_values or {}).get("assigned_to_id")
        )
        return {
            "generated_at": generated_at,
            "metrics": metrics,
            "workload": cls._workload(),
        }

    @classmethod
    def _workload(cls) -> list[dict]:
        user_model = get_user_model()
        capacity = int(getattr(settings, "ASSIGNMENT_CAPACITY_PER_USER", 25))
        if capacity < 1 or capacity > 10000:
            raise ValueError("ASSIGNMENT_CAPACITY_PER_USER is invalid")
        users = (
            user_model.objects.filter(is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(
                    role_assignments__revoked_at__isnull=True,
                    role_assignments__role__is_active=True,
                    role_assignments__role__code__in=(
                        CaseWorkflowService.ASSIGNEE_ROLE_CODES
                    ),
                )
            )
            .annotate(
                active_assignments=Count(
                    "assigned_requests",
                    filter=Q(
                        assigned_requests__status__in=(
                            CaseDashboardService.ACTIVE_STATUSES
                        )
                    ),
                    distinct=True,
                )
            )
            .distinct()
            .order_by("full_name", "email")
        )
        return [
            {
                "user_id": str(item.id),
                "name": item.full_name,
                "active_assignments": item.active_assignments,
                "capacity": capacity,
                "utilization_percentage": round(
                    item.active_assignments * 100 / capacity, 1
                ),
            }
            for item in users
        ]

    @classmethod
    def history(cls, *, user, filters: dict) -> dict:
        cls._require_permission(user)
        queryset = AuditLog.objects.filter(
            action="RIGHTS_REQUEST_ASSIGNED",
            entity_type="RIGHTS_REQUEST",
        ).select_related("actor_user").order_by("-created_at", "-id")
        if filters.get("request_id"):
            queryset = queryset.filter(entity_pk=str(filters["request_id"]))
        page_size = filters.get("page_size") or 20
        page = Paginator(queryset, page_size).get_page(filters.get("page") or 1)
        assignee_ids = set()
        for entry in page.object_list:
            for values in (entry.previous_values, entry.new_values):
                assignee_id = (values or {}).get("assigned_to_id")
                if assignee_id:
                    assignee_ids.add(assignee_id)
        names = {
            str(user_id): name
            for user_id, name in get_user_model().objects.filter(
                id__in=assignee_ids
            ).values_list("id", "full_name")
        }
        return {
            "pagination": cls._pagination(page, page_size),
            "results": [
                cls._serialize_history(item, names) for item in page.object_list
            ],
        }

    @classmethod
    def assign_many(cls, *, user, request_ids, assignee_id) -> dict:
        cls._require_permission(user)
        normalized_ids = cls._normalize_request_ids(request_ids)
        try:
            assignee_uuid = uuid.UUID(str(assignee_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AssignmentValidationError("El responsable no es válido.") from exc
        assignee = get_user_model().objects.filter(pk=assignee_uuid).first()
        if assignee is None:
            raise AssignmentValidationError("El responsable no existe.")
        correlation_id = uuid.uuid4()
        assigned = 0
        unchanged = 0
        with transaction.atomic():
            cases = list(
                RightsRequest.objects.select_for_update()
                .filter(pk__in=normalized_ids)
                .order_by("pk")
            )
            if len(cases) != len(normalized_ids):
                raise AssignmentValidationError(
                    "Uno o más expedientes no existen. No se realizó ningún cambio."
                )
            for case in cases:
                previous_id = case.assigned_to_id
                CaseWorkflowService.assign(
                    request=case,
                    assignee=assignee,
                    actor=user,
                    correlation_id=correlation_id,
                )
                if previous_id == assignee.id:
                    unchanged += 1
                else:
                    assigned += 1
        return {
            "correlation_id": str(correlation_id),
            "requested": len(normalized_ids),
            "assigned": assigned,
            "unchanged": unchanged,
            "assignee": {"id": str(assignee.id), "name": assignee.full_name},
        }

    @classmethod
    def _normalize_request_ids(cls, request_ids) -> list[uuid.UUID]:
        if not isinstance(request_ids, list) or not request_ids:
            raise AssignmentValidationError("Debe seleccionar al menos un expediente.")
        if len(request_ids) > cls.BULK_LIMIT:
            raise AssignmentValidationError(
                f"No se pueden asignar más de {cls.BULK_LIMIT} expedientes."
            )
        try:
            normalized = [uuid.UUID(str(item)) for item in request_ids]
        except (TypeError, ValueError, AttributeError) as exc:
            raise AssignmentValidationError(
                "La lista contiene un expediente inválido."
            ) from exc
        if len(set(normalized)) != len(normalized):
            raise AssignmentValidationError("La lista contiene expedientes duplicados.")
        return normalized

    @staticmethod
    def _pagination(page, page_size: int) -> dict:
        return {
            "page": page.number,
            "page_size": page_size,
            "pages": page.paginator.num_pages,
            "total": page.paginator.count,
        }

    @staticmethod
    def _serialize_request(item: RightsRequest) -> dict:
        return {
            "id": str(item.id),
            "reference_number": item.reference_number,
            "right": {"code": item.right.code, "name": item.right.name},
            "status": {"code": item.status, "label": item.get_status_display()},
            "assignee": (
                {"id": str(item.assigned_to_id), "name": item.assigned_to.full_name}
                if item.assigned_to_id
                else None
            ),
            "received_at": item.received_at,
            "current_due_at": item.current_due_at,
        }

    @staticmethod
    def _serialize_history(entry: AuditLog, names: dict[str, str]) -> dict:
        previous_id = (entry.previous_values or {}).get("assigned_to_id")
        new_id = (entry.new_values or {}).get("assigned_to_id")
        return {
            "id": entry.id,
            "request_id": entry.entity_pk,
            "reference_number": (entry.metadata or {}).get("reference_number"),
            "change_type": "REASSIGNED" if previous_id else "ASSIGNED",
            "previous_assignee": (
                {"id": previous_id, "name": names.get(previous_id)}
                if previous_id
                else None
            ),
            "new_assignee": {"id": new_id, "name": names.get(new_id)},
            "actor": {
                "id": str(entry.actor_user_id) if entry.actor_user_id else None,
                "name": entry.actor_user.full_name if entry.actor_user else None,
            },
            "correlation_id": str(entry.correlation_id),
            "created_at": entry.created_at,
        }
