import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import F, Q, Value

from apps.core.fields import FixedCharField
from apps.legal_content.models import RightCatalog
from apps.subjects.models import (
    DataSubject,
    SubjectRepresentative,
)


class RightsRequest(models.Model):
    class SourceChannel(models.TextChoices):
        WEB = "WEB", "Web"
        EMAIL = "EMAIL", "Correo electrónico"
        PHYSICAL = "PHYSICAL", "Físico"
        PHONE = "PHONE", "Teléfono"
        OTHER = "OTHER", "Otro"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Recibida"
        UNDER_REVIEW = "UNDER_REVIEW", "En revisión"
        AWAITING_INFORMATION = (
            "AWAITING_INFORMATION",
            "Esperando información",
        )
        EXTENDED = "EXTENDED", "Extendida"
        PARTIALLY_APPROVED = (
            "PARTIALLY_APPROVED",
            "Aprobada parcialmente",
        )
        RESPONDED = "RESPONDED", "Respondida"
        REJECTED = "REJECTED", "Rechazada"
        ARCHIVED = "ARCHIVED", "Archivada"
        CANCELLED = "CANCELLED", "Cancelada"
        CLOSED = "CLOSED", "Cerrada"

    class IdentityStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        VERIFIED = "VERIFIED", "Verificada"
        REJECTED = "REJECTED", "Rechazada"
        REQUIRES_REVIEW = (
            "REQUIRES_REVIEW",
            "Requiere revisión",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    data_subject = models.ForeignKey(
        DataSubject,
        on_delete=models.RESTRICT,
        related_name="rights_requests",
        db_index=False,
    )

    representative = models.ForeignKey(
        SubjectRepresentative,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="rights_requests",
        db_constraint=False,
        db_index=False,
    )

    right = models.ForeignKey(
        RightCatalog,
        on_delete=models.RESTRICT,
        related_name="rights_requests",
        db_index=False,
    )

    reference_number = models.CharField(
        max_length=50,
        unique=True,
    )

    request_details_encrypted = models.BinaryField()

    subject_snapshot_encrypted = models.BinaryField()

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    snapshot_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    source_channel = models.CharField(
        max_length=20,
        choices=SourceChannel.choices,
        default=SourceChannel.WEB,
        db_default="WEB",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_default="RECEIVED",
    )

    identity_status = models.CharField(
        max_length=20,
        choices=IdentityStatus.choices,
        default=IdentityStatus.PENDING,
        db_default="PENDING",
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_requests",
        db_index=False,
    )

    received_at = models.DateTimeField(
        db_default=TransactionNow(),
    )

    current_due_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    extension_applied = models.BooleanField(
        default=False,
        db_default=False,
    )

    extension_reason_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    updated_at = models.DateTimeField(
        db_default=TransactionNow(),
    )

    class Meta:
        db_table = "rights_requests"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_rr_encryption_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    snapshot_key_version__gt=0,
                ),
                name="ck_rr_snapshot_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    source_channel__in=[
                        "WEB",
                        "EMAIL",
                        "PHYSICAL",
                        "PHONE",
                        "OTHER",
                    ],
                ),
                name="ck_rr_source_channel",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "RECEIVED",
                        "UNDER_REVIEW",
                        "AWAITING_INFORMATION",
                        "EXTENDED",
                        "PARTIALLY_APPROVED",
                        "RESPONDED",
                        "REJECTED",
                        "ARCHIVED",
                        "CANCELLED",
                        "CLOSED",
                    ],
                ),
                name="ck_rr_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    identity_status__in=[
                        "PENDING",
                        "VERIFIED",
                        "REJECTED",
                        "REQUIRES_REVIEW",
                    ],
                ),
                name="ck_rr_identity_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(closed_at__isnull=True)
                    | Q(closed_at__gte=F("received_at"))
                ),
                name="ck_rr_closed_after_received",
            ),
            models.CheckConstraint(
                condition=(
                    Q(responded_at__isnull=True)
                    | Q(responded_at__gte=F("received_at"))
                ),
                name="ck_rr_responded_after_received",
            ),
            models.CheckConstraint(
                condition=(
                    Q(extension_applied=False)
                    | Q(
                        extension_reason_encrypted__isnull=False
                    )
                ),
                name="ck_rr_extension_reason",
            ),
        ]

        indexes = [
            models.Index(
                fields=["status"],
                name="idx_rr_status",
            ),
            models.Index(
                fields=["current_due_at"],
                condition=~Q(
                    status__in=[
                        "RESPONDED",
                        "REJECTED",
                        "ARCHIVED",
                        "CANCELLED",
                        "CLOSED",
                    ],
                ),
                name="idx_rr_due",
            ),
            models.Index(
                fields=["data_subject"],
                name="idx_rr_subject",
            ),
            models.Index(
                fields=["right"],
                name="idx_rr_right",
            ),
            models.Index(
                fields=["assigned_to", "status"],
                name="idx_rr_assigned",
            ),
            models.Index(
                fields=["-received_at"],
                name="idx_rr_received",
            ),
        ]

    def __str__(self):
        return self.reference_number


class PublicIntakeSubmission(models.Model):
    idempotency_key = models.UUIDField(
        unique=True,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_intake_submissions",
        db_index=False,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "public_intake_submissions"

        indexes = [
            models.Index(
                fields=["created_at"],
                name="idx_public_intake_created",
            ),
            models.Index(
                fields=["request"],
                name="idx_public_intake_request",
            ),
        ]

    def __str__(self):
        return str(self.idempotency_key)


class RequestAccessToken(models.Model):
    class Purpose(models.TextChoices):
        TRACKING = "TRACKING", "Seguimiento"
        FILE_DOWNLOAD = "FILE_DOWNLOAD", "Descarga de archivo"
        PORTABILITY_DOWNLOAD = (
            "PORTABILITY_DOWNLOAD",
            "Descarga de portabilidad",
        )
        EMAIL_VERIFICATION = (
            "EMAIL_VERIFICATION",
            "Verificación de correo",
        )

    class ResourceType(models.TextChoices):
        ATTACHMENT = "ATTACHMENT", "Adjunto"
        PORTABILITY_EXPORT = (
            "PORTABILITY_EXPORT",
            "Exportación de portabilidad",
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
        related_name="access_tokens",
        db_index=False,
    )

    token_hash = FixedCharField(
        max_length=64,
        unique=True,
    )

    lookup_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    purpose = models.CharField(
        max_length=30,
        choices=Purpose.choices,
        default=Purpose.TRACKING,
        db_default="TRACKING",
    )

    resource_type = models.CharField(
        max_length=30,
        choices=ResourceType.choices,
        null=True,
        blank=True,
    )

    resource_id = models.UUIDField(
        null=True,
        blank=True,
    )

    expires_at = models.DateTimeField()

    failed_attempts = models.IntegerField(
        default=0,
        db_default=0,
    )

    locked_until = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "request_access_tokens"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    lookup_key_version__gt=0,
                ),
                name="ck_rat_lookup_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    purpose__in=[
                        "TRACKING",
                        "FILE_DOWNLOAD",
                        "PORTABILITY_DOWNLOAD",
                        "EMAIL_VERIFICATION",
                    ],
                ),
                name="ck_rat_purpose",
            ),
            models.CheckConstraint(
                condition=(
                    Q(resource_type__isnull=True)
                    | Q(
                        resource_type__in=[
                            "ATTACHMENT",
                            "PORTABILITY_EXPORT",
                        ]
                    )
                ),
                name="ck_rat_resource_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    failed_attempts__gte=0,
                ),
                name="ck_rat_failed_attempts",
            ),
            models.CheckConstraint(
                condition=Q(
                    expires_at__gt=F("created_at"),
                ),
                name="ck_rat_expiration",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        purpose="FILE_DOWNLOAD",
                        resource_type="ATTACHMENT",
                        resource_id__isnull=False,
                    )
                    | Q(
                        purpose="PORTABILITY_DOWNLOAD",
                        resource_type="PORTABILITY_EXPORT",
                        resource_id__isnull=False,
                    )
                    | (
                        Q(
                            purpose__in=[
                                "TRACKING",
                                "EMAIL_VERIFICATION",
                            ]
                        )
                        & Q(resource_type__isnull=True)
                        & Q(resource_id__isnull=True)
                    )
                ),
                name="ck_rat_resource_binding",
            ),
        ]

        indexes = [
            models.Index(
                fields=["request", "purpose"],
                name="idx_rat_request",
            ),
            models.Index(
                fields=["expires_at"],
                condition=Q(
                    revoked_at__isnull=True,
                ),
                name="idx_rat_expiration",
            ),
        ]


class RequestClarification(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Solicitada"
        RECEIVED = "RECEIVED", "Recibida"
        EXPIRED = "EXPIRED", "Vencida"
        CANCELLED = "CANCELLED", "Cancelada"

    class DeadlineEffect(models.TextChoices):
        NO_CHANGE = "NO_CHANGE", "Sin cambio"
        PAUSE = "PAUSE", "Pausa"
        RESTART = "RESTART", "Reinicio"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="clarifications",
        db_index=False,
    )

    requested_at = models.DateTimeField()

    due_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    received_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_default="REQUESTED",
    )

    request_message_encrypted = models.BinaryField()

    response_message_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    deadline_effect = models.CharField(
        max_length=20,
        choices=DeadlineEffect.choices,
        default=DeadlineEffect.NO_CHANGE,
        db_default="NO_CHANGE",
    )

    deadline_effect_legal_basis = models.TextField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clarifications_created",
        db_index=False,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "request_clarifications"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "REQUESTED",
                        "RECEIVED",
                        "EXPIRED",
                        "CANCELLED",
                    ],
                ),
                name="ck_clar_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_clar_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    deadline_effect__in=[
                        "NO_CHANGE",
                        "PAUSE",
                        "RESTART",
                    ],
                ),
                name="ck_clar_deadline_effect",
            ),
            models.CheckConstraint(
                condition=(
                    Q(due_at__isnull=True)
                    | Q(due_at__gte=F("requested_at"))
                ),
                name="ck_clar_due_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(received_at__isnull=True)
                    | Q(
                        received_at__gte=F(
                            "requested_at"
                        )
                    )
                ),
                name="ck_clar_received_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(deadline_effect="NO_CHANGE")
                    | Q(
                        deadline_effect_legal_basis__isnull=False
                    )
                ),
                name="ck_clar_legal_basis",
            ),
        ]

        indexes = [
            models.Index(
                fields=["request", "-requested_at"],
                name="idx_clar_request",
            ),
        ]


class RequestStatusHistory(models.Model):
    class ChangeSource(models.TextChoices):
        WEB = "WEB", "Web"
        CELERY = "CELERY", "Celery"
        SYSTEM = "SYSTEM", "Sistema"
        COMMAND = "COMMAND", "Comando"
        API = "API", "API"

    id = models.BigAutoField(
        primary_key=True,
    )

    request = models.ForeignKey(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="status_history",
        db_index=False,
    )

    previous_status = models.CharField(
        max_length=30,
        choices=RightsRequest.Status.choices,
        null=True,
        blank=True,
    )

    new_status = models.CharField(
        max_length=30,
        choices=RightsRequest.Status.choices,
    )

    notes_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_status_changes",
        db_index=False,
    )

    change_source = models.CharField(
        max_length=20,
        choices=ChangeSource.choices,
        default=ChangeSource.WEB,
        db_default="WEB",
    )

    changed_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "request_status_history"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_rsh_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    change_source__in=[
                        "WEB",
                        "CELERY",
                        "SYSTEM",
                        "COMMAND",
                        "API",
                    ],
                ),
                name="ck_rsh_change_source",
            ),
        ]

        indexes = [
            models.Index(
                fields=["request", "-changed_at"],
                name="idx_rsh_request",
            ),
            models.Index(
                fields=["changed_by", "-changed_at"],
                condition=Q(
                    changed_by__isnull=False,
                ),
                name="idx_rsh_actor",
            ),
        ]


class RequestDeadline(models.Model):
    class DeadlineType(models.TextChoices):
        INITIAL = "INITIAL", "Inicial"
        EXTENSION = "EXTENSION", "Extensión"
        CLARIFICATION = "CLARIFICATION", "Aclaración"
        OTHER = "OTHER", "Otro"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Activo"
        PAUSED = "PAUSED", "Pausado"
        COMPLETED = "COMPLETED", "Completado"
        EXPIRED = "EXPIRED", "Vencido"
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
        related_name="deadlines",
        db_index=False,
    )

    deadline_type = models.CharField(
        max_length=30,
        choices=DeadlineType.choices,
    )

    sequence_number = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    starts_at = models.DateTimeField()
    due_at = models.DateTimeField()

    warning_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    warning_sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    paused_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    resumed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_default="ACTIVE",
    )

    rule_snapshot = models.JSONField(
        default=dict,
        db_default=Value(
            {},
            output_field=models.JSONField(),
        ),
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "request_deadlines"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    deadline_type__in=[
                        "INITIAL",
                        "EXTENSION",
                        "CLARIFICATION",
                        "OTHER",
                    ],
                ),
                name="ck_rd_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    sequence_number__gt=0,
                ),
                name="ck_rd_sequence",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "ACTIVE",
                        "PAUSED",
                        "COMPLETED",
                        "EXPIRED",
                        "CANCELLED",
                    ],
                ),
                name="ck_rd_status",
            ),
            models.UniqueConstraint(
                fields=[
                    "request",
                    "deadline_type",
                    "sequence_number",
                ],
                name="uq_rd_request_type_seq",
            ),
            models.CheckConstraint(
                condition=Q(
                    due_at__gte=F("starts_at"),
                ),
                name="ck_rd_due_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(warning_at__isnull=True)
                    | Q(warning_at__lte=F("due_at"))
                ),
                name="ck_rd_warning_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(resumed_at__isnull=True)
                    | Q(paused_at__isnull=False)
                ),
                name="ck_rd_resume_requires_pause",
            ),
            models.CheckConstraint(
                condition=(
                    Q(completed_at__isnull=True)
                    | Q(
                        completed_at__gte=F("starts_at")
                    )
                ),
                name="ck_rd_completed_date",
            ),
        ]

        indexes = [
            models.Index(
                fields=["due_at"],
                condition=Q(status="ACTIVE"),
                name="idx_rd_active",
            ),
            models.Index(
                fields=["request", "sequence_number"],
                name="idx_rd_request",
            ),
        ]


class CaseOutcomeReason(models.Model):
    class ReasonType(models.TextChoices):
        REJECTION = "REJECTION", "Rechazo"
        ARCHIVE = "ARCHIVE", "Archivo"
        CANCELLATION = "CANCELLATION", "Cancelación"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    reason_type = models.CharField(
        max_length=20,
        choices=ReasonType.choices,
    )

    code = models.CharField(
        max_length=50,
    )

    name = models.CharField(
        max_length=180,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    legal_basis = models.CharField(
        max_length=250,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_default=True,
    )

    class Meta:
        db_table = "case_outcome_reasons"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    reason_type__in=[
                        "REJECTION",
                        "ARCHIVE",
                        "CANCELLATION",
                    ],
                ),
                name="ck_cor_reason_type",
            ),
            models.UniqueConstraint(
                fields=[
                    "reason_type",
                    "code",
                ],
                name="uq_cor_type_code",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "reason_type",
                    "code",
                ],
                condition=Q(
                    is_active=True,
                ),
                name="idx_cor_type_active",
            ),
        ]

        ordering = [
            "reason_type",
            "code",
        ]

    def __str__(self):
        return f"{self.reason_type}: {self.name}"


class RequestResolution(models.Model):
    class ResolutionType(models.TextChoices):
        APPROVED = (
            "APPROVED",
            "Aprobada",
        )
        PARTIALLY_APPROVED = (
            "PARTIALLY_APPROVED",
            "Aprobada parcialmente",
        )
        REJECTED = (
            "REJECTED",
            "Rechazada",
        )
        ARCHIVED = (
            "ARCHIVED",
            "Archivada",
        )
        CANCELLED = (
            "CANCELLED",
            "Cancelada",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    request = models.OneToOneField(
        RightsRequest,
        on_delete=models.CASCADE,
        related_name="resolution",
        db_index=False,
    )

    resolution_type = models.CharField(
        max_length=30,
        choices=ResolutionType.choices,
    )

    outcome_reason = models.ForeignKey(
        CaseOutcomeReason,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="resolutions",
        db_index=False,
    )

    legal_basis = models.TextField(
        null=True,
        blank=True,
    )

    resolution_details_encrypted = models.BinaryField()

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="requests_resolved",
        db_index=False,
    )

    resolved_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "request_resolutions"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    resolution_type__in=[
                        "APPROVED",
                        "PARTIALLY_APPROVED",
                        "REJECTED",
                        "ARCHIVED",
                        "CANCELLED",
                    ],
                ),
                name="ck_resolution_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_resolution_key_version",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(
                        resolution_type__in=[
                            "REJECTED",
                            "ARCHIVED",
                            "CANCELLED",
                        ],
                    )
                    | Q(
                        outcome_reason__isnull=False,
                    )
                ),
                name="ck_resolution_reason_required",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "resolved_by",
                    "-resolved_at",
                ],
                name="idx_resolution_actor",
            ),
        ]

    def __str__(self):
        return (
            f"{self.request.reference_number} - "
            f"{self.resolution_type}"
        )
