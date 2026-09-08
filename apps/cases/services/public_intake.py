from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import uuid

from django.conf import settings
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import RequestAccessToken, RightsRequest
from apps.cases.services.intake import CaseIntakeService
from apps.cases.services.tokens import (
    RequestAccessTokenService,
    TokenInvalidOrExpiredError,
)
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import NotificationService
from apps.organization.models import SystemSetting
from apps.evidence.services.temporary_uploads import TemporaryUploadService
from apps.subjects.services.normalization import normalize_email


class PublicIntakeError(Exception):
    pass


class PublicIntakeSubmissionError(PublicIntakeError):
    pass


class PublicEmailVerificationAccessError(PublicIntakeError):
    """Generic error for unknown references and invalid verification codes."""

    pass


@dataclass(frozen=True)
class PublicIntakeResult:
    request: RightsRequest
    communication: RequestCommunication


@dataclass(frozen=True)
class PublicEmailVerificationResult:
    reference_number: str


class PublicIntakeService:
    @classmethod
    def _positive_ttl(cls, setting_name: str, default_seconds: int):
        seconds = int(getattr(settings, setting_name, default_seconds))
        if seconds <= 0:
            raise PublicIntakeSubmissionError(
                f"{setting_name} must be greater than zero."
            )
        return timedelta(seconds=seconds)

    @classmethod
    def submit(
        cls,
        *,
        subject_type: str,
        document_type: str,
        document_number: str,
        full_name: str,
        email: str,
        phone: str | None,
        right,
        request_details: str,
        representative_name: str | None = None,
        representative_document_type: str | None = None,
        representative_document_number: str | None = None,
        representative_email: str | None = None,
        temporary_uploads=(),
        upload_session_key: str | None = None,
        correlation_id=None,
    ) -> PublicIntakeResult:
        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        verification_ttl = cls._positive_ttl(
            "PUBLIC_EMAIL_VERIFICATION_TTL_SECONDS",
            24 * 60 * 60,
        )
        tracking_ttl = cls._positive_ttl(
            "PUBLIC_TRACKING_TTL_SECONDS",
            90 * 24 * 60 * 60,
        )
        temporary_uploads = tuple(temporary_uploads)
        if temporary_uploads and not upload_session_key:
            raise PublicIntakeSubmissionError(
                "Upload session is required for temporary attachments."
            )

        with transaction.atomic():
            case = CaseIntakeService.create_administrative_request(
                subject_type=subject_type,
                document_type=document_type,
                document_number=document_number,
                full_name=full_name,
                email=email,
                phone=phone,
                right=right,
                request_details=request_details,
                source_channel=RightsRequest.SourceChannel.WEB,
                actor=None,
                representative_name=representative_name,
                representative_document_type=representative_document_type,
                representative_document_number=(
                    representative_document_number
                ),
                representative_email=representative_email,
            )

            verification = RequestAccessTokenService.issue(
                request=case,
                purpose=RequestAccessToken.Purpose.EMAIL_VERIFICATION,
                ttl=verification_ttl,
                correlation_id=correlation_id,
                source=AuditLog.Source.WEB,
            )
            tracking = RequestAccessTokenService.issue(
                request=case,
                purpose=RequestAccessToken.Purpose.TRACKING,
                ttl=tracking_ttl,
                correlation_id=correlation_id,
                source=AuditLog.Source.WEB,
            )

            for issued_upload in temporary_uploads:
                TemporaryUploadService.promote(
                    request=case,
                    upload_id=issued_upload.record.id,
                    token=issued_upload.token,
                    session_key=upload_session_key,
                    correlation_id=correlation_id,
                )

            organization = SystemSetting.objects.get(singleton_key=1)
            public_site_url = settings.PUBLIC_SITE_URL or (
                f"https://{organization.domain}"
            )
            portal_base = f"{public_site_url.rstrip('/')}/cases/public"
            recipient = normalize_email(email)
            message_subject = f"Solicitud recibida: {case.reference_number}"
            message_body = (
                "Recibimos tu solicitud de ejercicio de derechos.\n\n"
                f"Referencia: {case.reference_number}\n"
                "Para confirmar tu correo visita:\n"
                f"{portal_base}/verify-email/\n"
                f"Código de verificación: {verification.token}\n\n"
                "Para consultar el estado visita:\n"
                f"{portal_base}/tracking/\n"
                f"Código de seguimiento: {tracking.token}\n\n"
                "Conserva estos códigos y no los compartas."
            )

            communication = NotificationService.queue_email(
                request=case,
                communication_type=(
                    RequestCommunication.CommunicationType.ACKNOWLEDGEMENT
                ),
                recipient=recipient,
                subject=message_subject,
                body=message_body,
                # The body carries one-time access codes and must never be
                # exposed later through a subject-visible message history.
                visible_to_subject=False,
                actor=None,
                correlation_id=correlation_id,
            )

        return PublicIntakeResult(
            request=case,
            communication=communication,
        )


class PublicEmailVerificationService:
    @classmethod
    def verify(
        cls,
        *,
        reference_number: str,
        token: str,
        correlation_id=None,
    ) -> PublicEmailVerificationResult:
        if not isinstance(reference_number, str):
            raise PublicEmailVerificationAccessError()
        reference_number = reference_number.strip().upper()
        if not reference_number:
            raise PublicEmailVerificationAccessError()

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        with transaction.atomic():
            case = RightsRequest.objects.filter(
                reference_number=reference_number
            ).first()
            if case is None:
                raise PublicEmailVerificationAccessError()

            try:
                RequestAccessTokenService.consume(
                    request=case,
                    token=token,
                    purpose=RequestAccessToken.Purpose.EMAIL_VERIFICATION,
                    actor=None,
                    correlation_id=correlation_id,
                    source=AuditLog.Source.WEB,
                )
            except TokenInvalidOrExpiredError as exc:
                raise PublicEmailVerificationAccessError() from exc

            AuditService.write(
                actor_type=AuditLog.ActorType.SYSTEM,
                actor=None,
                source=AuditLog.Source.WEB,
                correlation_id=correlation_id,
                action="PUBLIC_REQUEST_EMAIL_VERIFIED",
                entity_type="RIGHTS_REQUEST",
                entity_pk=case.id,
                description="Public request email ownership verified.",
                metadata={
                    "request_id": str(case.id),
                },
            )

        return PublicEmailVerificationResult(
            reference_number=case.reference_number
        )
