from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import Role
from apps.cases.models import RightsRequest
from apps.cases.policies import (
    FULL_READ_ROLE_CODES,
    active_role_codes,
    can_access_case_panel,
    visible_requests_for,
)


class DashboardPermissionError(Exception):
    pass


class CaseDashboardService:
    IN_REVIEW_STATUSES = (
        RightsRequest.Status.UNDER_REVIEW,
        RightsRequest.Status.AWAITING_INFORMATION,
        RightsRequest.Status.EXTENDED,
        RightsRequest.Status.PARTIALLY_APPROVED,
    )
    FINAL_STATUSES = (
        RightsRequest.Status.RESPONDED,
        RightsRequest.Status.REJECTED,
        RightsRequest.Status.ARCHIVED,
        RightsRequest.Status.CANCELLED,
        RightsRequest.Status.CLOSED,
    )
    ACTIVE_STATUSES = (
        RightsRequest.Status.RECEIVED,
        *IN_REVIEW_STATUSES,
    )

    @classmethod
    def _scope(cls, user) -> str:
        if getattr(user, "is_superuser", False):
            return "ALL"
        role_codes = active_role_codes(user)
        if role_codes & FULL_READ_ROLE_CODES:
            return "ALL"
        if Role.Code.OPERADOR in role_codes:
            return "ASSIGNED"
        return "NONE"

    @classmethod
    def snapshot(
        cls,
        *,
        user,
        generated_at=None,
        latest_limit: int = 8,
    ) -> dict:
        if not can_access_case_panel(user):
            raise DashboardPermissionError
        if latest_limit < 1 or latest_limit > 50:
            raise ValueError("latest_limit must be between 1 and 50")

        generated_at = generated_at or timezone.now()
        due_soon_days = int(
            getattr(settings, "DASHBOARD_DUE_SOON_DAYS", 7)
        )
        if due_soon_days < 1 or due_soon_days > 90:
            raise ValueError("DASHBOARD_DUE_SOON_DAYS must be between 1 and 90")
        due_soon_until = generated_at + timedelta(days=due_soon_days)

        queryset = visible_requests_for(user)
        metrics = queryset.aggregate(
            total=Count("id"),
            active=Count(
                "id",
                filter=Q(status__in=cls.ACTIVE_STATUSES),
            ),
            received=Count(
                "id",
                filter=Q(status=RightsRequest.Status.RECEIVED),
            ),
            in_review=Count(
                "id",
                filter=Q(status__in=cls.IN_REVIEW_STATUSES),
            ),
            finalized=Count(
                "id",
                filter=Q(status__in=cls.FINAL_STATUSES),
            ),
            unassigned=Count(
                "id",
                filter=(
                    Q(status__in=cls.ACTIVE_STATUSES)
                    & Q(assigned_to__isnull=True)
                ),
            ),
            due_soon=Count(
                "id",
                filter=(
                    Q(status__in=cls.ACTIVE_STATUSES)
                    & Q(current_due_at__gte=generated_at)
                    & Q(current_due_at__lte=due_soon_until)
                ),
            ),
            overdue=Count(
                "id",
                filter=(
                    Q(status__in=cls.ACTIVE_STATUSES)
                    & Q(current_due_at__lt=generated_at)
                ),
            ),
        )

        counts = {
            row["status"]: row["count"]
            for row in queryset.values("status").annotate(count=Count("id"))
        }
        status_counts = [
            {
                "code": code,
                "label": label,
                "count": counts.get(code, 0),
            }
            for code, label in RightsRequest.Status.choices
        ]

        latest = (
            queryset.select_related("right", "assigned_to")
            .order_by("-received_at", "-created_at")[:latest_limit]
        )
        latest_requests = [
            {
                "id": str(item.id),
                "reference_number": item.reference_number,
                "right": {
                    "code": item.right.code,
                    "name": item.right.name,
                },
                "status": {
                    "code": item.status,
                    "label": item.get_status_display(),
                },
                "assigned": item.assigned_to_id is not None,
                "received_at": item.received_at,
                "current_due_at": item.current_due_at,
            }
            for item in latest
        ]

        return {
            "generated_at": generated_at,
            "scope": cls._scope(user),
            "due_soon_days": due_soon_days,
            "metrics": metrics,
            "status_counts": status_counts,
            "latest_requests": latest_requests,
        }

