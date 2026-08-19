from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.cases.policies import (
    can_access_case_panel,
    can_view_sensitive_case_data,
    visible_requests_for,
)
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import NotificationService


class CommunicationPermissionError(Exception):
    pass


class CommunicationQueryService:
    @classmethod
    def _scope(cls, user):
        if not can_access_case_panel(user):
            raise CommunicationPermissionError
        return RequestCommunication.objects.filter(
            request__in=visible_requests_for(user)
        )

    @classmethod
    def summary(cls, *, user) -> dict:
        queryset = cls._scope(user)
        metrics = queryset.aggregate(
            total=Count("id"),
            inbound=Count(
                "id", filter=Q(direction=RequestCommunication.Direction.INBOUND)
            ),
            outbound=Count(
                "id", filter=Q(direction=RequestCommunication.Direction.OUTBOUND)
            ),
            pending=Count(
                "id",
                filter=Q(
                    delivery_status=RequestCommunication.DeliveryStatus.PENDING
                ),
            ),
            failed=Count(
                "id",
                filter=Q(delivery_status=RequestCommunication.DeliveryStatus.FAILED),
            ),
            sent=Count(
                "id",
                filter=Q(
                    delivery_status__in=(
                        RequestCommunication.DeliveryStatus.SENT,
                        RequestCommunication.DeliveryStatus.DELIVERED,
                    )
                ),
            ),
        )
        counts = {
            row["channel"]: row["count"]
            for row in queryset.values("channel").annotate(count=Count("id"))
        }
        return {
            "metrics": metrics,
            "by_channel": [
                {"code": code, "label": label, "count": counts.get(code, 0)}
                for code, label in RequestCommunication.Channel.choices
            ],
        }

    @classmethod
    def list(cls, *, user, filters: dict) -> dict:
        queryset = cls._scope(user).select_related(
            "request", "request__right", "sent_by"
        )
        for field in (
            "request_id",
            "direction",
            "channel",
            "communication_type",
            "delivery_status",
            "visible_to_subject",
        ):
            value = filters.get(field)
            if value is not None and value != "":
                queryset = queryset.filter(**{field: value})
        if filters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=filters["date_from"])
        if filters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=filters["date_to"])
        queryset = queryset.order_by("-created_at", "-id")
        page_size = filters.get("page_size") or 20
        page = Paginator(queryset, page_size).get_page(filters.get("page") or 1)
        return {
            "pagination": {
                "page": page.number,
                "page_size": page_size,
                "pages": page.paginator.num_pages,
                "total": page.paginator.count,
            },
            "results": [cls._serialize(item) for item in page.object_list],
        }

    @classmethod
    def detail(cls, *, user, communication_id) -> dict:
        communication = cls._scope(user).select_related(
            "request", "request__right", "sent_by"
        ).get(pk=communication_id)
        result = cls._serialize(communication)
        may_read = can_view_sensitive_case_data(user, communication.request)
        result["can_view_content"] = may_read
        result["content"] = (
            NotificationService.decrypt_payload(communication) if may_read else None
        )
        return result

    @staticmethod
    def _serialize(item: RequestCommunication) -> dict:
        return {
            "id": str(item.id),
            "request": {
                "id": str(item.request_id),
                "reference_number": item.request.reference_number,
                "right": item.request.right.name,
            },
            "direction": {
                "code": item.direction,
                "label": item.get_direction_display(),
            },
            "channel": {"code": item.channel, "label": item.get_channel_display()},
            "communication_type": {
                "code": item.communication_type,
                "label": item.get_communication_type_display(),
            },
            "delivery_status": {
                "code": item.delivery_status,
                "label": item.get_delivery_status_display(),
            },
            "visible_to_subject": item.visible_to_subject,
            "attempt_count": item.attempt_count,
            "sent_by": (
                {"id": str(item.sent_by_id), "name": item.sent_by.full_name}
                if item.sent_by_id
                else None
            ),
            "queued_at": item.queued_at,
            "sent_at": item.sent_at,
            "created_at": item.created_at,
        }
