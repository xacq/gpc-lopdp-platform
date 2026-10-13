from __future__ import annotations

import uuid

from django.utils import timezone
from django.utils.formats import date_format

from apps.cases.models import (
    RequestDeadline,
    RequestResolution,
    RightsRequest,
)
from apps.communications.models import (
    RequestCommunication,
)
from apps.communications.services.notifications import (
    NotificationService,
)
from apps.subjects.services.subjects import (
    SubjectService,
)


class CaseNotificationService:
    @classmethod
    def _recipient(cls, request: RightsRequest) -> str:
        return SubjectService.decrypt(
            request.data_subject
        ).email

    @classmethod
    def _local_date(cls, value) -> str:
        if value is None:
            return "Por determinar"

        return date_format(
            timezone.localtime(value),
            "d/m/Y H:i",
        )

    @classmethod
    def _idempotency_key(
        cls,
        *,
        request: RightsRequest,
        event: str,
        entity_id=None,
    ) -> uuid.UUID:
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "gpc-lopdp:"
                f"{request.id}:"
                f"{event}:"
                f"{entity_id or '-'}"
            ),
        )

    @classmethod
    def _queue(
        cls,
        *,
        request: RightsRequest,
        actor,
        event: str,
        communication_type: str,
        subject: str,
        body: str,
        entity_id=None,
    ) -> RequestCommunication:
        return NotificationService.queue_email(
            request=request,
            communication_type=communication_type,
            recipient=cls._recipient(request),
            subject=subject,
            body=body,
            visible_to_subject=False,
            actor=actor,
            idempotency_key=cls._idempotency_key(
                request=request,
                event=event,
                entity_id=entity_id,
            ),
        )

    @classmethod
    def clarification_requested(
        cls,
        *,
        request: RightsRequest,
        message: str,
        clarification_due_at,
        actor,
        clarification_id,
        legal_basis: str | None = None,
    ) -> RequestCommunication:
        due_text = cls._local_date(
            clarification_due_at
        )
        legal_text = (
            f"\n\nBase jurídica o fundamento: {legal_basis.strip()}"
            if legal_basis and legal_basis.strip()
            else ""
        )

        return cls._queue(
            request=request,
            actor=actor,
            event="clarification-requested",
            entity_id=clarification_id,
            communication_type=(
                RequestCommunication
                .CommunicationType
                .INFORMATION_REQUEST
            ),
            subject=(
                "Solicitud de aclaración "
                f"- {request.reference_number}"
            ),
            body=(
                "El Delegado de Protección de Datos requiere información "
                "adicional para continuar con la atención de tu solicitud.\n\n"
                f"Expediente: {request.reference_number}\n"
                f"Plazo para responder: {due_text}\n\n"
                f"Detalle de la aclaración solicitada:\n{message.strip()}"
                f"{legal_text}\n\n"
                "Por favor revisa esta solicitud y remite la información "
                "necesaria usando el canal indicado por la organización."
            ),
        )

    @classmethod
    def extension_applied(
        cls,
        *,
        request: RightsRequest,
        reason: str,
        extension_deadline: RequestDeadline,
        actor,
    ) -> RequestCommunication:
        due_text = cls._local_date(
            extension_deadline.due_at
        )

        return cls._queue(
            request=request,
            actor=actor,
            event="extension-applied",
            entity_id=extension_deadline.id,
            communication_type=(
                RequestCommunication
                .CommunicationType
                .EXTENSION_NOTICE
            ),
            subject=(
                "Aviso de extensión de plazo "
                f"- {request.reference_number}"
            ),
            body=(
                "Te informamos que se aplicó una extensión del plazo de "
                "atención de tu solicitud de ejercicio de derechos.\n\n"
                f"Expediente: {request.reference_number}\n"
                f"Nueva fecha estimada de atención: {due_text}\n\n"
                f"Motivo de la extensión:\n{reason.strip()}\n\n"
                "Puedes consultar el estado actualizado del trámite con "
                "tu número de referencia y código de seguimiento."
            ),
        )

    @classmethod
    def resolution_registered(
        cls,
        *,
        request: RightsRequest,
        resolution_type: str,
        details: str,
        actor,
        resolution_id,
    ) -> RequestCommunication | None:
        config = {
            RequestResolution
            .ResolutionType
            .REJECTED: (
                RequestCommunication
                .CommunicationType
                .REJECTION,
                "Resolución de rechazo",
                "Tu solicitud fue resuelta como rechazada.",
            ),
            RequestResolution
            .ResolutionType
            .ARCHIVED: (
                RequestCommunication
                .CommunicationType
                .ARCHIVE_NOTICE,
                "Aviso de archivo",
                "Tu solicitud fue archivada.",
            ),
            RequestResolution
            .ResolutionType
            .CANCELLED: (
                RequestCommunication
                .CommunicationType
                .CANCELLATION_NOTICE,
                "Aviso de cancelación",
                "Tu solicitud fue cancelada.",
            ),
        }.get(resolution_type)

        if config is None:
            return None

        communication_type, title, intro = config

        return cls._queue(
            request=request,
            actor=actor,
            event="resolution-registered",
            entity_id=resolution_id,
            communication_type=communication_type,
            subject=f"{title} - {request.reference_number}",
            body=(
                f"{intro}\n\n"
                f"Expediente: {request.reference_number}\n\n"
                f"Detalle de la resolución:\n{details.strip()}\n\n"
                "Esta comunicación forma parte de la trazabilidad oficial "
                "del trámite."
            ),
        )

    @classmethod
    def response_marked(
        cls,
        *,
        request: RightsRequest,
        details: str,
        actor,
    ) -> RequestCommunication:
        return cls._queue(
            request=request,
            actor=actor,
            event="response-marked",
            communication_type=(
                RequestCommunication
                .CommunicationType
                .RESPONSE
            ),
            subject=(
                "Respuesta a su solicitud "
                f"- {request.reference_number}"
            ),
            body=(
                "El Delegado de Protección de Datos ha emitido una "
                "respuesta para tu solicitud.\n\n"
                f"Expediente: {request.reference_number}\n\n"
                f"Respuesta:\n{details.strip()}\n\n"
                "Puedes consultar el estado del trámite con tu número "
                "de referencia y código de seguimiento."
            ),
        )
