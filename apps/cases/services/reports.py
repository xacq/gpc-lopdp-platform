from __future__ import annotations

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.cases.models import RightsRequest
from apps.cases.policies import can_access_case_panel, visible_requests_for
from apps.cases.services.dashboard import CaseDashboardService


class ReportPermissionError(Exception):
    pass


class CaseReportService:
    @classmethod
    def _filtered_queryset(cls, *, user, filters):
        if not can_access_case_panel(user):
            raise ReportPermissionError
        queryset = visible_requests_for(user)
        if filters.get("date_from"):
            queryset = queryset.filter(
                received_at__date__gte=filters["date_from"]
            )
        if filters.get("date_to"):
            queryset = queryset.filter(
                received_at__date__lte=filters["date_to"]
            )
        if filters.get("right_code"):
            queryset = queryset.filter(
                right__code=filters["right_code"]
            )
        if filters.get("status"):
            queryset = queryset.filter(status=filters["status"])
        if filters.get("assigned_to"):
            queryset = queryset.filter(
                assigned_to_id=filters["assigned_to"]
            )
        return queryset

    @staticmethod
    def _average_days(queryset):
        duration = ExpressionWrapper(
            Coalesce("closed_at", "responded_at") - F("received_at"),
            output_field=DurationField(),
        )
        average = (
            queryset.annotate(attention_duration=duration)
            .filter(attention_duration__isnull=False)
            .aggregate(value=Avg("attention_duration"))["value"]
        )
        if average is None:
            return None
        return round(average.total_seconds() / 86400, 2)

    @classmethod
    def build(cls, *, user, filters) -> dict:
        queryset = cls._filtered_queryset(user=user, filters=filters)
        metrics = queryset.aggregate(
            total=Count("id"),
            finalized=Count(
                "id",
                filter=Q(status__in=CaseDashboardService.FINAL_STATUSES),
            ),
            in_process=Count(
                "id",
                filter=Q(
                    status__in=CaseDashboardService.IN_REVIEW_STATUSES
                ),
            ),
            pending=Count(
                "id",
                filter=Q(status=RightsRequest.Status.RECEIVED),
            ),
        )
        metrics["average_attention_days"] = cls._average_days(queryset)
        total = metrics["total"]
        finalized_percentage = (
            round(metrics["finalized"] * 100 / total, 1) if total else 0.0
        )
        in_process_percentage = (
            round(metrics["in_process"] * 100 / total, 1) if total else 0.0
        )
        pending_percentage = (
            round(metrics["pending"] * 100 / total, 1) if total else 0.0
        )
        distribution = {
            "finalized_percentage": finalized_percentage,
            "in_process_percentage": in_process_percentage,
            "pending_percentage": pending_percentage,
            "in_process_end_percentage": min(
                finalized_percentage + in_process_percentage,
                100.0,
            ),
        }

        status_counts_by_code = {
            row["status"]: row["count"]
            for row in queryset.values("status").annotate(count=Count("id"))
        }
        by_status = [
            {
                "code": code,
                "label": label,
                "count": status_counts_by_code.get(code, 0),
            }
            for code, label in RightsRequest.Status.choices
        ]

        by_right = list(
            queryset.values("right__code", "right__name")
            .annotate(
                total=Count("id"),
                finalized=Count(
                    "id",
                    filter=Q(
                        status__in=CaseDashboardService.FINAL_STATUSES
                    ),
                ),
                in_process=Count(
                    "id",
                    filter=Q(
                        status__in=CaseDashboardService.IN_REVIEW_STATUSES
                    ),
                ),
                pending=Count(
                    "id",
                    filter=Q(status=RightsRequest.Status.RECEIVED),
                ),
            )
            .order_by("right__name", "right__code")
        )
        by_right = [
            {
                "code": row["right__code"],
                "name": row["right__name"],
                "total": row["total"],
                "finalized": row["finalized"],
                "in_process": row["in_process"],
                "pending": row["pending"],
                "completion_percentage": (
                    round(row["finalized"] * 100 / row["total"], 1)
                    if row["total"]
                    else 0.0
                ),
            }
            for row in by_right
        ]

        raw_by_month = list(
            queryset.annotate(month=TruncMonth("received_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        maximum_month_count = max(
            (row["count"] for row in raw_by_month),
            default=0,
        )
        by_month = [
            {
                "month": row["month"].date(),
                "count": row["count"],
                "relative_percentage": (
                    round(row["count"] * 100 / maximum_month_count, 1)
                    if maximum_month_count
                    else 0.0
                ),
            }
            for row in raw_by_month
        ]

        return {
            "generated_at": timezone.now(),
            "filters": {
                "date_from": filters.get("date_from"),
                "date_to": filters.get("date_to"),
                "right_code": filters.get("right_code") or None,
                "status": filters.get("status") or None,
                "assigned_to": (
                    str(filters["assigned_to"])
                    if filters.get("assigned_to")
                    else None
                ),
            },
            "metrics": metrics,
            "distribution": distribution,
            "by_status": by_status,
            "by_right": by_right,
            "by_month": by_month,
        }
