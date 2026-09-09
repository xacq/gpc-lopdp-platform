from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.cases.policies import can_assign_case
from apps.audit.presentation import entity_label
from apps.retention.models import DataDisposalEvent


class RetentionQueryPermissionError(Exception):
    pass


class RetentionQueryService:
    @staticmethod
    def _require(user):
        if not can_assign_case(user):
            raise RetentionQueryPermissionError

    @classmethod
    def summary(cls, *, user) -> dict:
        cls._require(user)
        queryset = DataDisposalEvent.objects.all()
        return {
            "metrics": queryset.aggregate(
                total=Count("id"),
                pending_approval=Count(
                    "id",
                    filter=Q(status=DataDisposalEvent.Status.PENDING_APPROVAL),
                ),
                approved=Count(
                    "id", filter=Q(status=DataDisposalEvent.Status.APPROVED)
                ),
                failed=Count(
                    "id", filter=Q(status=DataDisposalEvent.Status.FAILED)
                ),
                executed=Count(
                    "id", filter=Q(status=DataDisposalEvent.Status.EXECUTED)
                ),
            )
        }

    @classmethod
    def list(cls, *, user, filters: dict) -> dict:
        cls._require(user)
        queryset = DataDisposalEvent.objects.select_related(
            "retention_rule", "approved_by", "executed_by"
        )
        for field in ("status", "action", "entity_type"):
            if filters.get(field):
                queryset = queryset.filter(**{field: filters[field]})
        if filters.get("date_from"):
            queryset = queryset.filter(detected_at__date__gte=filters["date_from"])
        if filters.get("date_to"):
            queryset = queryset.filter(detected_at__date__lte=filters["date_to"])
        queryset = queryset.order_by("-detected_at", "-id")
        page_size = filters.get("page_size") or 20
        page = Paginator(queryset, page_size).get_page(filters.get("page") or 1)
        return {
            "pagination": {
                "page": page.number,
                "page_size": page_size,
                "pages": page.paginator.num_pages,
                "total": page.paginator.count,
            },
            "results": [cls.serialize(item) for item in page.object_list],
        }

    @staticmethod
    def serialize(item: DataDisposalEvent) -> dict:
        return {
            "id": str(item.id),
            "entity_type": item.entity_type,
            "entity_type_label": entity_label(item.entity_type),
            "entity_pk": item.entity_pk,
            "action": {"code": item.action, "label": item.get_action_display()},
            "status": {"code": item.status, "label": item.get_status_display()},
            "detected_at": item.detected_at,
            "approved_at": item.approved_at,
            "executed_at": item.executed_at,
            "approved_by": (
                {"id": str(item.approved_by_id), "name": item.approved_by.full_name}
                if item.approved_by_id
                else None
            ),
            "executed_by": (
                {"id": str(item.executed_by_id), "name": item.executed_by.full_name}
                if item.executed_by_id
                else None
            ),
            "has_evidence": item.evidence_sha256 is not None,
            "error_code": item.error_code,
        }
