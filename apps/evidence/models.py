import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import F, Q, Value

from apps.cases.models import RightsRequest
from apps.core.fields import FixedCharField
from apps.legal_content.models import LegalDocument
from apps.subjects.models import SubjectRepresentative


class IdentityVerification(models.Model):
    class VerificationMethod(models.TextChoices):
        STRUCTURAL_DOCUMENT_CHECK = (
            "STRUCTURAL_DOCUMENT_CHECK",
            "Validación estructural de documento",
        )
        EMAIL_CODE = (
            "EMAIL_CODE",
            "Código por correo",
        )
        DOCUMENT_REVIEW = (
            "DOCUMENT_REVIEW",
            "Revisión documental",
        )
        IN_PERSON = (
            "IN_PERSON",
            "Presencial",
        )
        MANUAL = (
            "MANUAL",
            "Manual",
        )
        OTHER = (
            "OTHER",
            "Otro",
        )

    class Result(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        VERIFIED = "VERIFIED", "Verificado"
        REJECTED = "REJECTED", "Rechazado"
        INCONCLUSIVE = "INCONCLUSIVE", "No concluyente"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="identity_verifications",
        db_index=False,
    )

    verification_method = models.CharField(
        max_length=40,
        choices=VerificationMethod.choices,
    )

    result = models.CharField(
        max_length=20,
        choices=Result.choices,
    )

    validation_metadata = models.JSONField(
        default=dict,
        db_default=Value(
            {},
            output_field=models.JSONField(),
        ),
    )

    validation_notes_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="identity_verifications",
        db_index=False,
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "identity_verifications"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    verification_method__in=[
                        "STRUCTURAL_DOCUMENT_CHECK",
                        "EMAIL_CODE",
                        "DOCUMENT_REVIEW",
                        "IN_PERSON",
                        "MANUAL",
                        "OTHER",
                    ],
                ),
                name="ck_idv_method",
            ),
            models.CheckConstraint(
                condition=Q(
                    result__in=[
                        "PENDING",
                        "VERIFIED",
                        "REJECTED",
                        "INCONCLUSIVE",
                    ],
                ),
                name="ck_idv_result",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_idv_key_version",
            ),
            models.CheckConstraint(
                condition=(
                    Q(result="PENDING")
                    | Q(verified_at__isnull=False)
                ),
                name="ck_idv_verified_at",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "request",
                    "-created_at",
                ],
                name="idx_idv_request",
            ),
            models.Index(
                fields=[
                    "verified_by",
                    "-created_at",
                ],
                condition=Q(
                    verified_by__isnull=False,
                ),
                name="idx_idv_actor",
            ),
        ]


class RequestAttachment(models.Model):
    class AttachmentType(models.TextChoices):
        IDENTITY_DOCUMENT = (
            "IDENTITY_DOCUMENT",
            "Documento de identidad",
        )
        AUTHORITY_DOCUMENT = (
            "AUTHORITY_DOCUMENT",
            "Documento de representación",
        )
        SUPPORTING_DOCUMENT = (
            "SUPPORTING_DOCUMENT",
            "Documento de respaldo",
        )
        REQUEST_DOCUMENT = (
            "REQUEST_DOCUMENT",
            "Documento de solicitud",
        )
        RESPONSE_DOCUMENT = (
            "RESPONSE_DOCUMENT",
            "Documento de respuesta",
        )
        PORTABILITY_EXPORT = (
            "PORTABILITY_EXPORT",
            "Exportación de portabilidad",
        )
        OTHER = (
            "OTHER",
            "Otro",
        )

    class Visibility(models.TextChoices):
        INTERNAL = "INTERNAL", "Interno"
        SUBJECT = "SUBJECT", "Visible al titular"

    class StorageBackend(models.TextChoices):
        LOCAL = "LOCAL", "Local"
        S3 = "S3", "S3"
        MINIO = "MINIO", "MinIO"

    class MalwareScanStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        CLEAN = "CLEAN", "Limpio"
        INFECTED = "INFECTED", "Infectado"
        FAILED = "FAILED", "Fallido"
        NOT_APPLICABLE = (
            "NOT_APPLICABLE",
            "No aplica",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="attachments",
        db_index=False,
    )

    representative = models.ForeignKey(
        SubjectRepresentative,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attachments",
        db_index=False,
    )

    attachment_type = models.CharField(
        max_length=40,
        choices=AttachmentType.choices,
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.INTERNAL,
        db_default="INTERNAL",
    )

    original_filename_encrypted = models.BinaryField()

    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
        db_default="LOCAL",
    )

    storage_key = models.TextField(
        unique=True,
    )

    mime_type = models.CharField(
        max_length=120,
    )

    size_bytes = models.BigIntegerField()

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

    malware_scan_status = models.CharField(
        max_length=20,
        choices=MalwareScanStatus.choices,
        default=MalwareScanStatus.PENDING,
        db_default="PENDING",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attachments_uploaded",
        db_index=False,
    )

    uploaded_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "request_attachments"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    attachment_type__in=[
                        "IDENTITY_DOCUMENT",
                        "AUTHORITY_DOCUMENT",
                        "SUPPORTING_DOCUMENT",
                        "REQUEST_DOCUMENT",
                        "RESPONSE_DOCUMENT",
                        "PORTABILITY_EXPORT",
                        "OTHER",
                    ],
                ),
                name="ck_att_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    visibility__in=[
                        "INTERNAL",
                        "SUBJECT",
                    ],
                ),
                name="ck_att_visibility",
            ),
            models.CheckConstraint(
                condition=Q(
                    storage_backend__in=[
                        "LOCAL",
                        "S3",
                        "MINIO",
                    ],
                ),
                name="ck_att_storage",
            ),
            models.CheckConstraint(
                condition=Q(
                    size_bytes__gt=0,
                ),
                name="ck_att_size",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_att_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    malware_scan_status__in=[
                        "PENDING",
                        "CLEAN",
                        "INFECTED",
                        "FAILED",
                        "NOT_APPLICABLE",
                    ],
                ),
                name="ck_att_scan_status",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "request",
                    "-uploaded_at",
                ],
                name="idx_att_request",
            ),
            models.Index(
                fields=[
                    "request",
                    "visibility",
                ],
                condition=Q(
                    deleted_at__isnull=True,
                ),
                name="idx_att_visible",
            ),
            models.Index(
                fields=["representative"],
                condition=Q(
                    representative__isnull=False,
                ),
                name="idx_att_rep",
            ),
        ]


class TemporaryUpload(models.Model):
    class AttachmentType(models.TextChoices):
        IDENTITY_DOCUMENT = (
            "IDENTITY_DOCUMENT",
            "Documento de identidad",
        )
        AUTHORITY_DOCUMENT = (
            "AUTHORITY_DOCUMENT",
            "Documento de representación",
        )
        SUPPORTING_DOCUMENT = (
            "SUPPORTING_DOCUMENT",
            "Documento de respaldo",
        )
        OTHER = "OTHER", "Otro"

    class StorageBackend(models.TextChoices):
        LOCAL = "LOCAL", "Local"
        S3 = "S3", "S3"
        MINIO = "MINIO", "MinIO"

    class MalwareScanStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        CLEAN = "CLEAN", "Limpio"
        INFECTED = "INFECTED", "Infectado"
        FAILED = "FAILED", "Fallido"
        NOT_APPLICABLE = (
            "NOT_APPLICABLE",
            "No aplica",
        )

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Cargado"
        PROMOTED = "PROMOTED", "Promovido"
        QUARANTINED = "QUARANTINED", "Cuarentena"
        EXPIRED = "EXPIRED", "Expirado"
        DELETED = "DELETED", "Eliminado"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    session_key_hash = FixedCharField(
        max_length=64,
    )

    upload_token_hash = FixedCharField(
        max_length=64,
        unique=True,
    )

    lookup_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    attachment_type = models.CharField(
        max_length=40,
        choices=AttachmentType.choices,
    )

    original_filename_encrypted = models.BinaryField()

    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
        db_default="LOCAL",
    )

    storage_key = models.TextField(
        unique=True,
    )

    mime_type = models.CharField(
        max_length=120,
    )

    size_bytes = models.BigIntegerField()

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

    malware_scan_status = models.CharField(
        max_length=20,
        choices=MalwareScanStatus.choices,
        default=MalwareScanStatus.PENDING,
        db_default="PENDING",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
        db_default="UPLOADED",
    )

    expires_at = models.DateTimeField()

    promoted_request = models.ForeignKey(
        RightsRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temporary_uploads",
        db_index=False,
    )

    promoted_attachment = models.ForeignKey(
        RequestAttachment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temporary_sources",
        db_index=False,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    promoted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "temporary_uploads"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    lookup_key_version__gt=0,
                ),
                name="ck_tmp_lookup_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    attachment_type__in=[
                        "IDENTITY_DOCUMENT",
                        "AUTHORITY_DOCUMENT",
                        "SUPPORTING_DOCUMENT",
                        "OTHER",
                    ],
                ),
                name="ck_tmp_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    storage_backend__in=[
                        "LOCAL",
                        "S3",
                        "MINIO",
                    ],
                ),
                name="ck_tmp_storage",
            ),
            models.CheckConstraint(
                condition=Q(
                    size_bytes__gt=0,
                ),
                name="ck_tmp_size",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_tmp_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    malware_scan_status__in=[
                        "PENDING",
                        "CLEAN",
                        "INFECTED",
                        "FAILED",
                        "NOT_APPLICABLE",
                    ],
                ),
                name="ck_tmp_scan_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "UPLOADED",
                        "PROMOTED",
                        "QUARANTINED",
                        "EXPIRED",
                        "DELETED",
                    ],
                ),
                name="ck_tmp_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    expires_at__gt=F("created_at"),
                ),
                name="ck_tmp_expiration",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="PROMOTED")
                    | (
                        Q(
                            promoted_request__isnull=False
                        )
                        & Q(
                            promoted_attachment__isnull=False
                        )
                        & Q(
                            promoted_at__isnull=False
                        )
                    )
                ),
                name="ck_tmp_promoted",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "session_key_hash",
                    "status",
                ],
                name="idx_tmp_session",
            ),
            models.Index(
                fields=["expires_at"],
                condition=Q(
                    status="UPLOADED",
                ),
                name="idx_tmp_expiry",
            ),
        ]


class NoticeDelivery(models.Model):
    class DeliveryChannel(models.TextChoices):
        WEB = "WEB", "Web"
        EMAIL = "EMAIL", "Correo electrónico"
        PHYSICAL = "PHYSICAL", "Físico"
        OTHER = "OTHER", "Otro"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="notice_deliveries",
        db_index=False,
    )

    legal_document = models.ForeignKey(
        LegalDocument,
        on_delete=models.RESTRICT,
        related_name="notice_deliveries",
        db_index=False,
    )

    delivery_channel = models.CharField(
        max_length=20,
        choices=DeliveryChannel.choices,
        default=DeliveryChannel.WEB,
        db_default="WEB",
    )

    delivered_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    acknowledged = models.BooleanField(
        default=False,
        db_default=False,
    )

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    user_agent = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    rendered_content_sha256 = FixedCharField(
        max_length=64,
    )

    class Meta:
        db_table = "notice_deliveries"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    delivery_channel__in=[
                        "WEB",
                        "EMAIL",
                        "PHYSICAL",
                        "OTHER",
                    ],
                ),
                name="ck_notice_channel",
            ),
            models.CheckConstraint(
                condition=(
                    Q(acknowledged=False)
                    | Q(
                        acknowledged_at__isnull=False
                    )
                ),
                name="ck_notice_ack",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "request",
                    "-delivered_at",
                ],
                name="idx_notice_request",
            ),
            models.Index(
                fields=["legal_document"],
                name="idx_notice_doc",
            ),
        ]