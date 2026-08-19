from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from django.db import transaction
from django.utils import timezone

from apps.cases.models import RequestDeadline
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import NotificationService
from apps.organization.models import SystemSetting


@dataclass(frozen=True)
class DeadlineAlertBatchResult:
    queued: int
    communication_ids: tuple[uuid.UUID, ...]


class DeadlineAlertService:
    IDEMPOTENCY_NAMESPACE = uuid.UUID("894e6a36-0f95-43df-ae3f-48c05a51c7b3")

    @classmethod
    def _idempotency_key(cls, deadline: RequestDeadline) -> uuid.UUID:
        return uuid.uuid5(
            cls.IDEMPOTENCY_NAMESPACE,
            f"deadline-alert:{deadline.id}",
        )

    @classmethod
    def queue_due_alerts(
        cls,
        *,
        limit: int = 100,
        now=None,
        enqueue_callback: Callable[[uuid.UUID], None] | None = None,
    ) -> DeadlineAlertBatchResult:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer.")
        now = now or timezone.now()
        setting = SystemSetting.objects.get(singleton_key=1)
        recipient = setting.dpd_email or setting.contact_email
        queued_ids: list[uuid.UUID] = []

        with transaction.atomic():
            deadlines = list(
                RequestDeadline.objects.select_for_update(skip_locked=True)
                .select_related("request")
                .filter(
                    status=RequestDeadline.Status.ACTIVE,
                    warning_at__isnull=False,
                    warning_at__lte=now,
                    due_at__gt=now,
                    warning_sent_at__isnull=True,
                )
                .order_by("warning_at", "id")[:limit]
            )
            for deadline in deadlines:
                request = deadline.request
                communication = NotificationService.queue_email(
                    request=request,
                    communication_type=(
                        RequestCommunication.CommunicationType.DEADLINE_ALERT
                    ),
                    recipient=recipient,
                    subject=(
                        f"Alerta de vencimiento: {request.reference_number}"
                    ),
                    body=(
                        "El expediente "
                        f"{request.reference_number} vence el "
                        f"{deadline.due_at.isoformat()}."
                    ),
                    visible_to_subject=False,
                    actor=None,
                    idempotency_key=cls._idempotency_key(deadline),
                    enqueue_callback=enqueue_callback,
                )
                deadline.warning_sent_at = now
                deadline.save(update_fields=["warning_sent_at"])
                queued_ids.append(communication.id)

        return DeadlineAlertBatchResult(
            queued=len(queued_ids),
            communication_ids=tuple(queued_ids),
        )
