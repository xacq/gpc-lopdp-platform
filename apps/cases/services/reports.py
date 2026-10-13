from __future__ import annotations

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.cases.models import RightsRequest
from apps.cases.policies import (
    can_access_case_panel,
    can_view_sensitive_case_data,
    visible_requests_for,
)
from apps.cases.services.dashboard import CaseDashboardService
from apps.cases.services.cases import CaseWorkflowService
from apps.core.services.crypto import CryptoError
from apps.subjects.models import DataSubject, SubjectRepresentative
from apps.subjects.services.subjects import RepresentativeService


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


class DetailedCaseReportService(CaseReportService):
    @staticmethod
    def _choice_label(choices, value):
        return dict(choices).get(value, value or "")

    @classmethod
    def _subject_payload(cls, *, user, case):
        if not can_view_sensitive_case_data(user, case):
            return {
                "subject_type": "Protegido",
                "document_type": "Protegido",
                "document_number": "Protegido",
                "full_name": "Protegido",
                "email": "Protegido",
                "phone": "Protegido",
                "representative_name": "—",
                "representative_document": "—",
                "representative_email": "—",
                "representative_status": "—",
            }

        try:
            snapshot = CaseWorkflowService.decrypt_subject_snapshot(case)
        except CryptoError:
            snapshot = None

        representative_name = "—"
        representative_document = "—"
        representative_email = "—"
        representative_status = "—"
        if case.representative_id:
            try:
                representative = RepresentativeService.decrypt(
                    case.representative
                )
            except CryptoError:
                representative = None
            if representative is not None:
                representative_name = representative.representative_name
                representative_document = (
                    f"{cls._choice_label(SubjectRepresentative.DocumentType.choices, representative.representative_document_type)} "
                    f"{representative.representative_document_number}"
                )
                representative_email = representative.representative_email or "—"
                representative_status = cls._choice_label(
                    SubjectRepresentative.VerificationStatus.choices,
                    representative.verification_status,
                )

        return {
            "subject_type": cls._choice_label(
                DataSubject.SubjectType.choices,
                getattr(snapshot, "subject_type", None),
            ),
            "document_type": cls._choice_label(
                DataSubject.DocumentType.choices,
                getattr(snapshot, "document_type", None),
            ),
            "document_number": getattr(snapshot, "document_number", "") or "",
            "full_name": getattr(snapshot, "full_name", "") or "",
            "email": getattr(snapshot, "email", "") or "",
            "phone": getattr(snapshot, "phone", None) or "—",
            "representative_name": representative_name,
            "representative_document": representative_document,
            "representative_email": representative_email,
            "representative_status": representative_status,
        }

    @classmethod
    def _privacy_payload(cls, case):
        delivery = (
            case.notice_deliveries.filter(acknowledged=True)
            .select_related("legal_document")
            .order_by("-acknowledged_at", "-delivered_at")
            .first()
        )
        if delivery is None:
            return {
                "accepted": "No registrado",
                "accepted_at": None,
                "document_title": "—",
                "document_version": "—",
                "document_sha256": "—",
                "content_sha256": "—",
                "channel": "—",
                "ip_address": "—",
                "user_agent": "—",
            }
        document = delivery.legal_document
        return {
            "accepted": "Sí" if delivery.acknowledged else "No",
            "accepted_at": delivery.acknowledged_at,
            "document_title": document.title,
            "document_version": document.version,
            "document_sha256": document.content_sha256,
            "content_sha256": delivery.rendered_content_sha256,
            "channel": delivery.get_delivery_channel_display(),
            "ip_address": delivery.ip_address or "—",
            "user_agent": delivery.user_agent or "—",
        }

    @classmethod
    def rows(cls, *, user, filters):
        queryset = (
            cls._filtered_queryset(user=user, filters=filters)
            .select_related("right", "assigned_to", "representative")
            .annotate(
                attachment_count=Count(
                    "attachments",
                    filter=Q(attachments__deleted_at__isnull=True),
                    distinct=True,
                ),
                communication_count=Count("communications", distinct=True),
            )
            .order_by("-received_at", "-id")
        )

        rows = []
        for case in queryset:
            subject = cls._subject_payload(user=user, case=case)
            privacy = cls._privacy_payload(case)
            rows.append(
                {
                    "id": case.id,
                    "reference_number": case.reference_number,
                    "received_at": case.received_at,
                    "right": case.right.name,
                    "status": case.get_status_display(),
                    "source_channel": case.get_source_channel_display(),
                    "assigned_to": (
                        case.assigned_to.full_name
                        or case.assigned_to.email
                        if case.assigned_to_id
                        else "Sin asignar"
                    ),
                    "identity_status": case.get_identity_status_display(),
                    "current_due_at": case.current_due_at,
                    "responded_at": case.responded_at,
                    "closed_at": case.closed_at,
                    "attachment_count": case.attachment_count,
                    "communication_count": case.communication_count,
                    **subject,
                    **{
                        f"privacy_{key}": value
                        for key, value in privacy.items()
                    },
                }
            )
        return rows

    @classmethod
    def build(cls, *, user, filters) -> dict:
        rows = cls.rows(user=user, filters=filters)
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
            "total": len(rows),
            "rows": rows,
        }
