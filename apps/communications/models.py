import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import F, Q

from apps.cases.models import RightsRequest
from apps.core.fields import FixedCharField


class RequestCommunication(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "INBOUND", "Entrante"
        OUTBOUND = "OUTBOUND", "Saliente"
        SYSTEM = "SYSTEM", "Sistema"

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Correo electrónico"
        PORTAL = "PORTAL", "Portal"
        PHONE = "PHONE", "Teléfono"
        PHYSICAL = "PHYSICAL", "Físico"
        OTHER = "OTHER", "Otro"

    class CommunicationType(models.TextChoices):
        ACKNOWLEDGEMENT = (
            "ACKNOWLEDGEMENT",
            "Acuse de recepción",
        )
        ASSIGNMENT_NOTICE = (
            "ASSIGNMENT_NOTICE",
            "Aviso de asignación",
        )
        INFORMATION_REQUEST = (
            "INFORMATION_REQUEST",
            "Solicitud de información",
        )
        CLARIFICATION_REMINDER = (
            "CLARIFICATION_REMINDER",
            "Recordatorio de aclaración",
        )
        EXTENSION_NOTICE = (
            "EXTENSION_NOTICE",
            "Aviso de extensión",
        )
        DEADLINE_ALERT = (
            "DEADLINE_ALERT",
            "Alerta de vencimiento",
        )
        RESPONSE = (
            "RESPONSE",
            "Respuesta",
        )
        REJECTION = (
            "REJECTION",
            "Rechazo",
        )
        ARCHIVE_NOTICE = (
            "ARCHIVE_NOTICE",
            "Aviso de archivo",
        )
        CANCELLATION_NOTICE = (
            "CANCELLATION_NOTICE",
            "Aviso de cancelación",
        )
        PORTABILITY_READY = (
            "PORTABILITY_READY",
            "Portabilidad disponible",
        )
        COMPLAINT_INFORMATION = (
            "COMPLAINT_INFORMATION",
            "Información de reclamación",
        )
        DELIVERY_FAILURE_ALERT = (
            "DELIVERY_FAILURE_ALERT",
            "Alerta de fallo de entrega",
        )
        OTHER = (
            "OTHER",
            "Otro",
        )

    class DeliveryStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PROCESSING = "PROCESSING", "Procesando"
        SENT = "SENT", "Enviado"
        DELIVERED = "DELIVERED", "Entregado"
        FAILED = "FAILED", "Fallido"
        RECEIVED = "RECEIVED", "Recibido"
        CANCELLED = "CANCELLED", "Cancelado"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="communications",
        db_index=False,
    )

    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
    )

    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
    )

    communication_type = models.CharField(
        max_length=40,
        choices=CommunicationType.choices,
    )

    visible_to_subject = models.BooleanField(
        default=False,
        db_default=False,
    )

    recipient_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    subject_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    body_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    idempotency_key = models.UUIDField(
        default=uuid.uuid4,
        db_default=RandomUUID(),
        unique=True,
        editable=False,
    )

    provider_message_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    delivery_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_default="PENDING",
    )

    attempt_count = models.IntegerField(
        default=0,
        db_default=0,
    )

    queued_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_error = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communications_sent",
        db_index=False,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "request_communications"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    direction__in=[
                        "INBOUND",
                        "OUTBOUND",
                        "SYSTEM",
                    ],
                ),
                name="ck_comm_direction",
            ),
            models.CheckConstraint(
                condition=Q(
                    channel__in=[
                        "EMAIL",
                        "PORTAL",
                        "PHONE",
                        "PHYSICAL",
                        "OTHER",
                    ],
                ),
                name="ck_comm_channel",
            ),
            models.CheckConstraint(
                condition=Q(
                    communication_type__in=[
                        "ACKNOWLEDGEMENT",
                        "ASSIGNMENT_NOTICE",
                        "INFORMATION_REQUEST",
                        "CLARIFICATION_REMINDER",
                        "EXTENSION_NOTICE",
                        "DEADLINE_ALERT",
                        "RESPONSE",
                        "REJECTION",
                        "ARCHIVE_NOTICE",
                        "CANCELLATION_NOTICE",
                        "PORTABILITY_READY",
                        "COMPLAINT_INFORMATION",
                        "DELIVERY_FAILURE_ALERT",
                        "OTHER",
                    ],
                ),
                name="ck_comm_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_comm_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    delivery_status__in=[
                        "PENDING",
                        "PROCESSING",
                        "SENT",
                        "DELIVERED",
                        "FAILED",
                        "RECEIVED",
                        "CANCELLED",
                    ],
                ),
                name="ck_comm_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    attempt_count__gte=0,
                ),
                name="ck_comm_attempts",
            ),
            models.CheckConstraint(
                condition=(
                    Q(sent_at__isnull=True)
                    | Q(sent_at__gte=F("created_at"))
                ),
                name="ck_comm_sent_at",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "request",
                    "-created_at",
                ],
                name="idx_comm_request",
            ),
            models.Index(
                fields=[
                    "request",
                    "-created_at",
                ],
                condition=Q(
                    visible_to_subject=True,
                ),
                name="idx_comm_visible",
            ),
            models.Index(
                fields=[
                    "next_retry_at",
                    "queued_at",
                ],
                condition=Q(
                    delivery_status__in=[
                        "PENDING",
                        "FAILED",
                    ],
                ),
                name="idx_comm_pending",
            ),
        ]

    def __str__(self):
        return f"{self.communication_type} - {self.request}"


class PortabilityExport(models.Model):
    class ExportFormat(models.TextChoices):
        JSON = "JSON", "JSON"
        CSV = "CSV", "CSV"

    class StorageBackend(models.TextChoices):
        LOCAL = "LOCAL", "Local"
        S3 = "S3", "S3"
        MINIO = "MINIO", "MinIO"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="portability_exports",
        db_index=False,
    )

    export_format = models.CharField(
        max_length=10,
        choices=ExportFormat.choices,
    )

    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
        db_default="LOCAL",
    )

    storage_key = models.TextField(
        unique=True,
    )

    file_sha256 = FixedCharField(
        max_length=64,
    )

    is_encrypted = models.BooleanField(
        default=True,
        db_default=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portability_exports_generated",
        db_index=False,
    )

    generated_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "portability_exports"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    export_format__in=[
                        "JSON",
                        "CSV",
                    ],
                ),
                name="ck_port_export_format",
            ),
            models.CheckConstraint(
                condition=Q(
                    storage_backend__in=[
                        "LOCAL",
                        "S3",
                        "MINIO",
                    ],
                ),
                name="ck_port_storage",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_port_key_version",
            ),
            models.CheckConstraint(
                condition=(
                    Q(expires_at__isnull=True)
                    | Q(
                        expires_at__gt=F(
                            "generated_at"
                        )
                    )
                ),
                name="ck_port_expiration",
            ),
            models.CheckConstraint(
                condition=(
                    Q(downloaded_at__isnull=True)
                    | Q(
                        downloaded_at__gte=F(
                            "generated_at"
                        )
                    )
                ),
                name="ck_port_downloaded",
            ),
            models.CheckConstraint(
                condition=(
                    Q(revoked_at__isnull=True)
                    | Q(
                        revoked_at__gte=F(
                            "generated_at"
                        )
                    )
                ),
                name="ck_port_revoked",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "request",
                    "-generated_at",
                ],
                name="idx_portability_request",
            ),
            models.Index(
                fields=["expires_at"],
                condition=(
                    Q(revoked_at__isnull=True)
                    & Q(expires_at__isnull=False)
                ),
                name="idx_portability_expiration",
            ),
        ]

    def __str__(self):
        return (
            f"{self.request.reference_number} "
            f"({self.export_format})"
        )