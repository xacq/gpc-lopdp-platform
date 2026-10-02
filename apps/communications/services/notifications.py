from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from typing import Callable
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.formats import date_format

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.communications.models import RequestCommunication
from apps.core.services.crypto import CryptoService
from apps.organization.models import SystemSetting


class NotificationServiceError(Exception):
    pass


class CommunicationStateError(
    NotificationServiceError
):
    pass


class CommunicationPayloadError(
    NotificationServiceError
):
    pass


@dataclass(frozen=True)
class OutboxBatchResult:
    selected: int
    sent: int
    failed: int
    skipped: int


class NotificationService:
    DEFAULT_MAX_ATTEMPTS = 5
    DEFAULT_RETRY_MINUTES = 5
    MAX_RETRY_MINUTES = 60

    EMAIL_PATTERN = re.compile(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        re.IGNORECASE,
    )
    TOKEN_PATTERN = re.compile(
        r"Código de (?P<kind>verificación|seguimiento): (?P<token>\S+)"
    )

    @classmethod
    def _database_now(cls):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT transaction_timestamp()"
            )
            row = cursor.fetchone()

        return row[0]

    @classmethod
    def _normalize_text(
        cls,
        value: str,
        *,
        field_name: str,
        max_length: int | None = None,
    ) -> str:
        if not isinstance(value, str):
            raise CommunicationPayloadError(
                f"{field_name} must be text."
            )

        value = value.strip()

        if not value:
            raise CommunicationPayloadError(
                f"{field_name} is required."
            )

        if (
            max_length is not None
            and len(value) > max_length
        ):
            raise CommunicationPayloadError(
                f"{field_name} exceeds "
                f"{max_length} characters."
            )

        return value

    @classmethod
    def _validate_choice(
        cls,
        *,
        field_name: str,
        value: str,
    ) -> str:
        value = value.strip().upper()

        field = (
            RequestCommunication
            ._meta
            .get_field(field_name)
        )

        valid = {
            choice[0]
            for choice in field.choices
        }

        if value not in valid:
            raise ValueError(
                f"Invalid {field_name}: {value}"
            )

        return value

    @classmethod
    def _aad(
        cls,
        communication_id: uuid.UUID,
        field_name: str,
    ) -> bytes:
        return (
            "request_communications:"
            f"{communication_id}:"
            f"{field_name}"
        ).encode("utf-8")

    @classmethod
    def _encrypt_text(
        cls,
        *,
        communication_id: uuid.UUID,
        field_name: str,
        value: str,
        key_version: int,
    ) -> bytes:
        encrypted = CryptoService.encrypt_text(
            value,
            aad=cls._aad(
                communication_id,
                field_name,
            ),
            key_version=key_version,
        )

        return encrypted.data

    @classmethod
    def _decrypt_text(
        cls,
        *,
        communication: RequestCommunication,
        field_name: str,
        value: bytes | None,
    ) -> str | None:
        if not value:
            return None

        return CryptoService.decrypt_text(
            value,
            aad=cls._aad(
                communication.id,
                field_name,
            ),
            key_version=(
                communication
                .encryption_key_version
            ),
        )

    @classmethod
    def _max_attempts(cls) -> int:
        value = int(
            getattr(
                settings,
                "COMMUNICATION_MAX_ATTEMPTS",
                cls.DEFAULT_MAX_ATTEMPTS,
            )
        )

        if value <= 0:
            raise NotificationServiceError(
                "COMMUNICATION_MAX_ATTEMPTS "
                "must be greater than zero."
            )

        return value

    @classmethod
    def _retry_delay(
        cls,
        attempt_count: int,
    ) -> timedelta:
        base = int(
            getattr(
                settings,
                "COMMUNICATION_RETRY_MINUTES",
                cls.DEFAULT_RETRY_MINUTES,
            )
        )

        if base <= 0:
            raise NotificationServiceError(
                "COMMUNICATION_RETRY_MINUTES "
                "must be greater than zero."
            )

        minutes = min(
            base * (2 ** max(
                attempt_count - 1,
                0,
            )),
            cls.MAX_RETRY_MINUTES,
        )

        return timedelta(
            minutes=minutes
        )

    @classmethod
    def _sanitize_error(
        cls,
        exc: Exception,
    ) -> str:
        error_class = (
            exc.__class__.__name__
        )

        value = (
            "EMAIL_DELIVERY_FAILED:"
            f"{error_class}"
        )

        value = cls.EMAIL_PATTERN.sub(
            "[REDACTED_EMAIL]",
            value,
        )

        return value[:500]

    @classmethod
    def _public_site_url(cls, organization: SystemSetting) -> str:
        return (
            getattr(settings, "PUBLIC_SITE_URL", "")
            or f"https://{organization.domain}"
        ).rstrip("/")

    @classmethod
    def _absolute_url(cls, base_url: str, value: str | None) -> str | None:
        if not value:
            return None
        if value.startswith(("http://", "https://")):
            return value
        return urljoin(f"{base_url}/", value.lstrip("/"))

    @classmethod
    def _format_local_datetime(cls, value) -> str:
        if value is None:
            value = timezone.now()
        return date_format(
            timezone.localtime(value),
            "d/m/Y H:i",
        )

    @classmethod
    def _paragraphs(cls, body: str) -> str:
        paragraphs = []
        for block in body.split("\n\n"):
            lines = [
                escape(line.strip())
                for line in block.splitlines()
                if line.strip()
            ]
            if lines:
                paragraphs.append(
                    "<p style=\"margin:0 0 12px;color:#351411;"
                    "font-size:15px;line-height:1.6;\">"
                    + "<br>".join(lines)
                    + "</p>"
                )
        return "".join(paragraphs)

    @classmethod
    def _email_shell(
        cls,
        *,
        organization: SystemSetting,
        public_site_url: str,
        title: str,
        preheader: str,
        content_html: str,
    ) -> str:
        trade_name = organization.trade_name or organization.legal_name
        primary = organization.primary_color or "#C8393C"
        secondary = organization.secondary_color or "#552A2A"
        accent = organization.accent_color or primary
        privacy_url = f"{public_site_url}/legal/"
        logo_url = cls._absolute_url(public_site_url, organization.effective_logo_url)
        logo_html = (
            f'<img src="{escape(logo_url, quote=True)}" '
            f'alt="{escape(trade_name, quote=True)}" '
            'style="display:block;margin:0 auto 12px;max-width:180px;'
            'max-height:72px;width:auto;height:auto;">'
            if logo_url
            else (
                f'<div style="font-family:Georgia,serif;font-size:28px;'
                f'color:{secondary};letter-spacing:.04em;margin-bottom:8px;">'
                f'{escape(trade_name)}</div>'
            )
        )

        return f"""<!doctype html>
<html lang="es">
<body style="margin:0;padding:0;background:#f7f2f0;font-family:Arial,Helvetica,sans-serif;color:#351411;">
  <div style="display:none;max-height:0;overflow:hidden;color:transparent;">{escape(preheader)}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f7f2f0;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border:1px solid #eadbd6;border-radius:18px;overflow:hidden;box-shadow:0 14px 34px rgba(72,35,28,.08);">
          <tr>
            <td align="center" style="padding:30px 34px 22px;border-bottom:1px solid #f0e4e0;">
              {logo_html}
              <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:{primary};font-weight:700;">Plataforma de Privacidad y Gestión LOPDP</div>
              <a href="{escape(public_site_url, quote=True)}" style="display:inline-block;margin-top:8px;color:{accent};font-size:14px;text-decoration:none;">{escape(public_site_url)}</a>
            </td>
          </tr>
          <tr>
            <td style="padding:30px 34px;">
              <h1 style="margin:0 0 18px;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.18;color:{secondary};font-weight:500;">{escape(title)}</h1>
              {content_html}
            </td>
          </tr>
          <tr>
            <td style="padding:20px 34px;background:#fbf7f5;border-top:1px solid #f0e4e0;color:#6e625e;font-size:12px;line-height:1.6;text-align:center;">
              <div>© {timezone.localdate().year} {escape(organization.legal_name)}</div>
              <div>Canal de privacidad: <a href="mailto:{escape(organization.contact_email, quote=True)}" style="color:{accent};">{escape(organization.contact_email)}</a></div>
              <div><a href="{escape(privacy_url, quote=True)}" style="color:{accent};">Página de privacidad</a></div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    @classmethod
    def _button(cls, *, url: str, label: str, color: str) -> str:
        return (
            f'<a href="{escape(url, quote=True)}" '
            'style="display:inline-block;padding:12px 18px;border-radius:9px;'
            f'background:{color};color:#ffffff;text-decoration:none;'
            'font-weight:700;font-size:14px;">'
            f'{escape(label)}</a>'
        )

    @classmethod
    def _code_box(cls, *, label: str, value: str) -> str:
        return (
            '<div style="margin:12px 0 18px;padding:12px 14px;'
            'background:#f8f1ee;border:1px solid #eadbd6;border-radius:10px;">'
            f'<div style="font-size:12px;text-transform:uppercase;'
            f'letter-spacing:.06em;color:#7a6e6a;font-weight:700;">{escape(label)}</div>'
            f'<div style="margin-top:6px;font-family:Consolas,Monaco,monospace;'
            f'font-size:13px;line-height:1.45;color:#351411;word-break:break-all;">'
            f'{escape(value)}</div></div>'
        )

    @classmethod
    def _tokens_from_body(cls, body: str) -> dict[str, str]:
        tokens = {}
        for match in cls.TOKEN_PATTERN.finditer(body):
            tokens[match.group("kind")] = match.group("token")
        return tokens

    @classmethod
    def _acknowledgement_html(
        cls,
        *,
        communication: RequestCommunication,
        body: str,
        organization: SystemSetting,
        public_site_url: str,
    ) -> str:
        tokens = cls._tokens_from_body(body)
        reference = communication.request.reference_number
        if (
            not tokens.get("verificación")
            or not tokens.get("seguimiento")
        ):
            return cls._generic_html(
                communication=communication,
                body=body,
                organization=organization,
                public_site_url=public_site_url,
            )

        portal_base = f"{public_site_url}/cases/public"
        verify_url = f"{portal_base}/verify-email/"
        tracking_url = f"{portal_base}/tracking/"
        privacy_url = f"{public_site_url}/legal/"
        primary = organization.primary_color or "#C8393C"
        secondary = organization.secondary_color or "#552A2A"

        content = (
            '<p style="margin:0 0 16px;color:#351411;font-size:15px;line-height:1.6;">'
            "Hemos recibido tu solicitud de ejercicio de derechos.</p>"
            f'{cls._code_box(label="Número de referencia", value=reference)}'
            f'<div style="margin:22px 0;padding-top:4px;">'
            f'<h2 style="margin:0 0 8px;color:{secondary};font-size:18px;">'
            "Paso 1 · Verifica tu correo electrónico</h2>"
            '<p style="margin:0 0 14px;color:#5f5350;font-size:14px;line-height:1.55;">'
            "Para continuar con la gestión, confirma que este correo te pertenece.</p>"
            f'{cls._button(url=verify_url, label="Verificar correo", color=primary)}'
            f'<div style="margin-top:10px;"><a href="{escape(verify_url, quote=True)}" '
            f'style="color:{primary};font-size:13px;">{escape(verify_url)}</a></div>'
            f'{cls._code_box(label="Código de verificación", value=tokens.get("verificación", ""))}'
            "</div>"
            f'<div style="margin:22px 0;padding-top:4px;">'
            f'<h2 style="margin:0 0 8px;color:{secondary};font-size:18px;">'
            "Paso 2 · Revisa el seguimiento</h2>"
            '<p style="margin:0 0 14px;color:#5f5350;font-size:14px;line-height:1.55;">'
            "Después de verificar tu correo, podrás consultar el estado del trámite.</p>"
            f'{cls._button(url=tracking_url, label="Revisar seguimiento", color=primary)}'
            f'<div style="margin-top:10px;"><a href="{escape(tracking_url, quote=True)}" '
            f'style="color:{primary};font-size:13px;">{escape(tracking_url)}</a></div>'
            f'{cls._code_box(label="Código de seguimiento", value=tokens.get("seguimiento", ""))}'
            "</div>"
            '<div style="margin-top:20px;padding:14px;border-radius:10px;'
            'background:#fff8f6;border:1px solid #f0ddd7;color:#5f5350;'
            'font-size:13px;line-height:1.55;">'
            "<strong>Importante:</strong> conserva estos códigos y no los compartas. "
            "El código de verificación confirma tu correo y el código de seguimiento "
            "permite consultar el estado del trámite.</div>"
            f'<p style="margin:16px 0 0;color:#5f5350;font-size:13px;">'
            f'Página de privacidad: <a href="{escape(privacy_url, quote=True)}" '
            f'style="color:{primary};">{escape(privacy_url)}</a></p>'
        )

        return cls._email_shell(
            organization=organization,
            public_site_url=public_site_url,
            title="Solicitud recibida",
            preheader=f"Solicitud {reference} recibida. Verifica tu correo y revisa el seguimiento.",
            content_html=content,
        )

    @classmethod
    def _response_html(
        cls,
        *,
        communication: RequestCommunication,
        body: str,
        organization: SystemSetting,
        public_site_url: str,
    ) -> str:
        reference = communication.request.reference_number
        tracking_url = f"{public_site_url}/cases/public/tracking/"
        privacy_url = f"{public_site_url}/legal/"
        primary = organization.primary_color or "#C8393C"

        content = (
            f'{cls._code_box(label="Expediente", value=reference)}'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'style="margin:0 0 18px;"><tr>'
            '<td style="padding:10px 0;color:#6e625e;font-size:13px;">'
            '<strong style="color:#351411;">Fecha de respuesta:</strong><br>'
            f'{escape(cls._format_local_datetime(communication.created_at))}</td>'
            '<td style="padding:10px 0;color:#6e625e;font-size:13px;">'
            '<strong style="color:#351411;">Responsable:</strong><br>'
            f'{escape(organization.trade_name or organization.legal_name)}</td>'
            '</tr></table>'
            '<div style="margin:18px 0;padding:18px;border:1px solid #eadbd6;'
            'border-radius:12px;background:#fffaf8;">'
            '<div style="margin:0 0 10px;font-size:12px;text-transform:uppercase;'
            'letter-spacing:.08em;color:#7a6e6a;font-weight:700;">Mensaje del Delegado</div>'
            f'{cls._paragraphs(body)}'
            '</div>'
            f'{cls._button(url=tracking_url, label="Revisar seguimiento", color=primary)}'
            f'<div style="margin-top:10px;"><a href="{escape(tracking_url, quote=True)}" '
            f'style="color:{primary};font-size:13px;">{escape(tracking_url)}</a></div>'
            f'<p style="margin:18px 0 0;color:#5f5350;font-size:13px;line-height:1.55;">'
            "Este mensaje corresponde a una comunicación oficial dentro del trámite "
            "de ejercicio de derechos LOPDP.</p>"
            f'<p style="margin:10px 0 0;color:#5f5350;font-size:13px;">'
            f'Página de privacidad: <a href="{escape(privacy_url, quote=True)}" '
            f'style="color:{primary};">{escape(privacy_url)}</a></p>'
        )

        return cls._email_shell(
            organization=organization,
            public_site_url=public_site_url,
            title="Respuesta del Delegado de Protección de Datos",
            preheader=f"Respuesta oficial para el expediente {reference}.",
            content_html=content,
        )

    @classmethod
    def _generic_html(
        cls,
        *,
        communication: RequestCommunication,
        body: str,
        organization: SystemSetting,
        public_site_url: str,
    ) -> str:
        return cls._email_shell(
            organization=organization,
            public_site_url=public_site_url,
            title=communication.get_communication_type_display(),
            preheader=f"Comunicación del expediente {communication.request.reference_number}.",
            content_html=(
                f'{cls._code_box(label="Expediente", value=communication.request.reference_number)}'
                '<div style="margin:18px 0;padding:18px;border:1px solid #eadbd6;'
                'border-radius:12px;background:#fffaf8;">'
                f'{cls._paragraphs(body)}'
                '</div>'
            ),
        )

    @classmethod
    def _html_body(
        cls,
        *,
        communication: RequestCommunication,
        body: str,
    ) -> str:
        organization = SystemSetting.objects.get(singleton_key=1)
        public_site_url = cls._public_site_url(organization)

        if (
            communication.communication_type
            == RequestCommunication.CommunicationType.ACKNOWLEDGEMENT
        ):
            return cls._acknowledgement_html(
                communication=communication,
                body=body,
                organization=organization,
                public_site_url=public_site_url,
            )

        if (
            communication.communication_type
            == RequestCommunication.CommunicationType.RESPONSE
        ):
            return cls._response_html(
                communication=communication,
                body=body,
                organization=organization,
                public_site_url=public_site_url,
            )

        return cls._generic_html(
            communication=communication,
            body=body,
            organization=organization,
            public_site_url=public_site_url,
        )

    @classmethod
    def _audit(
        cls,
        *,
        action: str,
        communication: RequestCommunication,
        correlation_id: uuid.UUID,
        actor=None,
        source: str = AuditLog.Source.SYSTEM,
    ) -> None:
        AuditService.write(
            actor_type=(
                AuditLog.ActorType.USER
                if actor is not None
                else AuditLog.ActorType.SYSTEM
            ),
            actor=actor,
            source=source,
            correlation_id=correlation_id,
            action=action,
            entity_type=(
                "REQUEST_COMMUNICATION"
            ),
            entity_pk=communication.id,
            description=(
                "Request communication "
                "processing event."
            ),
            metadata={
                "request_id": str(
                    communication.request_id
                ),
                "communication_type": (
                    communication
                    .communication_type
                ),
                "channel": (
                    communication.channel
                ),
                "delivery_status": (
                    communication
                    .delivery_status
                ),
                "attempt_count": (
                    communication
                    .attempt_count
                ),
            },
        )

    @classmethod
    def queue_email(
        cls,
        *,
        request,
        communication_type: str,
        recipient: str,
        subject: str,
        body: str,
        visible_to_subject: bool,
        actor=None,
        idempotency_key: (
            uuid.UUID | None
        ) = None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
        enqueue_callback: (
            Callable[[uuid.UUID], None]
            | None
        ) = None,
    ) -> RequestCommunication:
        communication_type = (
            cls._validate_choice(
                field_name=(
                    "communication_type"
                ),
                value=communication_type,
            )
        )

        recipient = cls._normalize_text(
            recipient,
            field_name="recipient",
            max_length=254,
        )
        subject = cls._normalize_text(
            subject,
            field_name="subject",
            max_length=998,
        )
        body = cls._normalize_text(
            body,
            field_name="body",
        )

        if idempotency_key is None:
            idempotency_key = uuid.uuid4()
        elif not isinstance(
            idempotency_key,
            uuid.UUID,
        ):
            idempotency_key = uuid.UUID(
                str(idempotency_key)
            )

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        existing = (
            RequestCommunication.objects
            .filter(
                idempotency_key=(
                    idempotency_key
                )
            )
            .first()
        )

        if existing is not None:
            return existing

        communication_id = uuid.uuid4()
        key_version = int(
            settings
            .PII_ENCRYPTION_ACTIVE_VERSION
        )

        recipient_encrypted = (
            cls._encrypt_text(
                communication_id=(
                    communication_id
                ),
                field_name="recipient",
                value=recipient,
                key_version=key_version,
            )
        )

        subject_encrypted = (
            cls._encrypt_text(
                communication_id=(
                    communication_id
                ),
                field_name="subject",
                value=subject,
                key_version=key_version,
            )
        )

        body_encrypted = (
            cls._encrypt_text(
                communication_id=(
                    communication_id
                ),
                field_name="body",
                value=body,
                key_version=key_version,
            )
        )

        with transaction.atomic():
            try:
                with transaction.atomic():
                    communication = (
                        RequestCommunication.objects
                        .create(
                            id=communication_id,
                            request=request,
                            direction="OUTBOUND",
                            channel="EMAIL",
                            communication_type=(
                                communication_type
                            ),
                            visible_to_subject=(
                                visible_to_subject
                            ),
                            recipient_encrypted=(
                                recipient_encrypted
                            ),
                            subject_encrypted=(
                                subject_encrypted
                            ),
                            body_encrypted=(
                                body_encrypted
                            ),
                            encryption_key_version=(
                                key_version
                            ),
                            idempotency_key=(
                                idempotency_key
                            ),
                            delivery_status="PENDING",
                            attempt_count=0,
                        )
                    )
            except IntegrityError:
                existing = (
                    RequestCommunication.objects
                    .filter(
                        idempotency_key=(
                            idempotency_key
                        )
                    )
                    .first()
                )

                if existing is None:
                    raise

                return existing

            cls._audit(
                action=(
                    "REQUEST_COMMUNICATION_QUEUED"
                ),
                communication=communication,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
                source=(
                    AuditLog.Source.WEB
                    if actor is not None
                    else AuditLog.Source.SYSTEM
                ),
            )

            if enqueue_callback is not None:
                transaction.on_commit(
                    lambda: enqueue_callback(
                        communication.id
                    )
                )

            return communication

    @classmethod
    def decrypt_payload(
        cls,
        communication: RequestCommunication,
    ) -> dict[str, str | None]:
        return {
            "recipient": cls._decrypt_text(
                communication=communication,
                field_name="recipient",
                value=(
                    communication
                    .recipient_encrypted
                ),
            ),
            "subject": cls._decrypt_text(
                communication=communication,
                field_name="subject",
                value=(
                    communication
                    .subject_encrypted
                ),
            ),
            "body": cls._decrypt_text(
                communication=communication,
                field_name="body",
                value=(
                    communication
                    .body_encrypted
                ),
            ),
        }

    @classmethod
    def record_inbound(
        cls,
        *,
        request,
        channel: str,
        communication_type: str,
        contact: str,
        subject: str,
        body: str,
        visible_to_subject: bool,
        actor,
        idempotency_key: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> RequestCommunication:
        channel = cls._validate_choice(field_name="channel", value=channel)
        communication_type = cls._validate_choice(
            field_name="communication_type",
            value=communication_type,
        )
        contact = cls._normalize_text(
            contact,
            field_name="contact",
            max_length=254,
        )
        subject = cls._normalize_text(
            subject,
            field_name="subject",
            max_length=998,
        )
        body = cls._normalize_text(body, field_name="body")
        if idempotency_key is None:
            idempotency_key = uuid.uuid4()
        elif not isinstance(idempotency_key, uuid.UUID):
            idempotency_key = uuid.UUID(str(idempotency_key))
        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        existing = RequestCommunication.objects.filter(
            idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            return existing

        communication_id = uuid.uuid4()
        key_version = int(settings.PII_ENCRYPTION_ACTIVE_VERSION)
        encrypted = {
            field_name: cls._encrypt_text(
                communication_id=communication_id,
                field_name=field_name,
                value=value,
                key_version=key_version,
            )
            for field_name, value in {
                "recipient": contact,
                "subject": subject,
                "body": body,
            }.items()
        }
        with transaction.atomic():
            communication = RequestCommunication.objects.create(
                id=communication_id,
                request=request,
                direction=RequestCommunication.Direction.INBOUND,
                channel=channel,
                communication_type=communication_type,
                visible_to_subject=visible_to_subject,
                recipient_encrypted=encrypted["recipient"],
                subject_encrypted=encrypted["subject"],
                body_encrypted=encrypted["body"],
                encryption_key_version=key_version,
                idempotency_key=idempotency_key,
                delivery_status=RequestCommunication.DeliveryStatus.RECEIVED,
                sent_by=actor,
            )
            cls._audit(
                action="REQUEST_COMMUNICATION_RECEIVED",
                communication=communication,
                actor=actor,
                correlation_id=correlation_id,
                source=AuditLog.Source.WEB,
            )
            return communication

    @classmethod
    def process_email(
        cls,
        communication_id,
        *,
        correlation_id: (
            uuid.UUID | None
        ) = None,
        source: str = AuditLog.Source.CELERY,
    ) -> RequestCommunication:
        if not isinstance(
            communication_id,
            uuid.UUID,
        ):
            communication_id = uuid.UUID(
                str(communication_id)
            )

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        with transaction.atomic():
            communication = (
                RequestCommunication.objects
                .select_for_update()
                .get(pk=communication_id)
            )

            if (
                communication
                .delivery_status
                in {
                    "SENT",
                    "DELIVERED",
                    "CANCELLED",
                    "PROCESSING",
                }
            ):
                return communication

            if (
                communication.channel
                != "EMAIL"
                or communication.direction
                != "OUTBOUND"
            ):
                raise CommunicationStateError(
                    "Communication is not an "
                    "outbound email."
                )

            db_now = cls._database_now()

            if (
                communication.next_retry_at
                is not None
                and communication
                .next_retry_at
                > db_now
            ):
                raise CommunicationStateError(
                    "Communication is not due "
                    "for retry yet."
                )

            communication.delivery_status = (
                "PROCESSING"
            )
            communication.attempt_count += 1
            communication.last_attempt_at = (
                db_now
            )
            communication.next_retry_at = (
                None
            )
            communication.last_error = None

            communication.save(
                update_fields=[
                    "delivery_status",
                    "attempt_count",
                    "last_attempt_at",
                    "next_retry_at",
                    "last_error",
                ]
            )

            payload = cls.decrypt_payload(
                communication
            )

        try:
            message = EmailMultiAlternatives(
                subject=payload["subject"],
                body=payload["body"],
                to=[payload["recipient"]],
            )
            message.attach_alternative(
                cls._html_body(
                    communication=communication,
                    body=payload["body"],
                ),
                "text/html",
            )

            sent_count = message.send(
                fail_silently=False
            )

            if sent_count != 1:
                raise RuntimeError(
                    "Email backend did not "
                    "confirm one message."
                )

        except Exception as exc:
            with transaction.atomic():
                communication = (
                    RequestCommunication.objects
                    .select_for_update()
                    .get(pk=communication_id)
                )

                db_now = cls._database_now()

                communication.delivery_status = (
                    "FAILED"
                )
                communication.last_error = (
                    cls._sanitize_error(exc)
                )

                if (
                    communication
                    .attempt_count
                    < cls._max_attempts()
                ):
                    communication.next_retry_at = (
                        db_now
                        + cls._retry_delay(
                            communication
                            .attempt_count
                        )
                    )
                else:
                    communication.next_retry_at = (
                        None
                    )

                communication.save(
                    update_fields=[
                        "delivery_status",
                        "last_error",
                        "next_retry_at",
                    ]
                )

                cls._audit(
                    action=(
                        "REQUEST_COMMUNICATION_FAILED"
                    ),
                    communication=(
                        communication
                    ),
                    correlation_id=(
                        correlation_id
                    ),
                    source=source,
                )

            return communication

        with transaction.atomic():
            communication = (
                RequestCommunication.objects
                .select_for_update()
                .get(pk=communication_id)
            )

            db_now = cls._database_now()

            communication.delivery_status = (
                "SENT"
            )
            communication.sent_at = db_now
            communication.next_retry_at = (
                None
            )
            communication.last_error = None

            communication.save(
                update_fields=[
                    "delivery_status",
                    "sent_at",
                    "next_retry_at",
                    "last_error",
                ]
            )

            cls._audit(
                action=(
                    "REQUEST_COMMUNICATION_SENT"
                ),
                communication=communication,
                correlation_id=(
                    correlation_id
                ),
                source=source,
            )

            return communication

    @classmethod
    def process_due_email_batch(
        cls,
        *,
        batch_size: int = 100,
        correlation_id: uuid.UUID | None = None,
        source: str = AuditLog.Source.COMMAND,
    ) -> OutboxBatchResult:
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000.")

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        db_now = cls._database_now()
        candidate_ids = list(
            RequestCommunication.objects.filter(
                direction=RequestCommunication.Direction.OUTBOUND,
                channel=RequestCommunication.Channel.EMAIL,
                attempt_count__lt=cls._max_attempts(),
            )
            .filter(
                Q(delivery_status=RequestCommunication.DeliveryStatus.PENDING)
                | Q(
                    delivery_status=RequestCommunication.DeliveryStatus.FAILED,
                    next_retry_at__lte=db_now,
                )
            )
            .order_by("queued_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )

        sent = 0
        failed = 0
        skipped = 0

        for communication_id in candidate_ids:
            try:
                communication = cls.process_email(
                    communication_id,
                    correlation_id=correlation_id,
                    source=source,
                )
            except (
                CommunicationStateError,
                RequestCommunication.DoesNotExist,
            ):
                skipped += 1
                continue

            if communication.delivery_status in {
                RequestCommunication.DeliveryStatus.SENT,
                RequestCommunication.DeliveryStatus.DELIVERED,
            }:
                sent += 1
            elif communication.delivery_status == (
                RequestCommunication.DeliveryStatus.FAILED
            ):
                failed += 1
            else:
                skipped += 1

        return OutboxBatchResult(
            selected=len(candidate_ids),
            sent=sent,
            failed=failed,
            skipped=skipped,
        )
