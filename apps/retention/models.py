import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import F, Q

from apps.core.fields import FixedCharField


class BusinessHoliday(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    holiday_date = models.DateField(
        unique=True,
    )

    description = models.CharField(
        max_length=180,
    )

    is_national = models.BooleanField(
        default=False,
        db_default=False,
    )

    class Meta:
        db_table = "business_holidays"
        ordering = ["holiday_date"]

    def __str__(self):
        return f"{self.holiday_date} - {self.description}"


class RetentionRule(models.Model):
    class RetentionAnchor(models.TextChoices):
        CREATED_AT = "CREATED_AT", "Fecha de creación"
        RECEIVED_AT = "RECEIVED_AT", "Fecha de recepción"
        CLOSED_AT = "CLOSED_AT", "Fecha de cierre"
        EXPIRES_AT = "EXPIRES_AT", "Fecha de expiración"
        REVOKED_AT = "REVOKED_AT", "Fecha de revocación"
        LAST_ACTIVITY_AT = (
            "LAST_ACTIVITY_AT",
            "Última actividad",
        )

    class FinalAction(models.TextChoices):
        DELETE = "DELETE", "Eliminar"
        ANONYMIZE = "ANONYMIZE", "Anonimizar"
        BLOCK = "BLOCK", "Bloquear"
        ARCHIVE = "ARCHIVE", "Archivar"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    entity_type = models.CharField(
        max_length=50,
        unique=True,
    )

    retention_days = models.IntegerField()

    retention_anchor = models.CharField(
        max_length=30,
        choices=RetentionAnchor.choices,
    )

    final_action = models.CharField(
        max_length=20,
        choices=FinalAction.choices,
    )

    requires_approval = models.BooleanField(
        default=True,
        db_default=True,
    )

    legal_basis = models.TextField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_default=True,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    updated_at = models.DateTimeField(
        db_default=TransactionNow(),
    )

    class Meta:
        db_table = "retention_rules"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    retention_days__gt=0,
                ),
                name="ck_retention_days",
            ),
            models.CheckConstraint(
                condition=Q(
                    retention_anchor__in=[
                        "CREATED_AT",
                        "RECEIVED_AT",
                        "CLOSED_AT",
                        "EXPIRES_AT",
                        "REVOKED_AT",
                        "LAST_ACTIVITY_AT",
                    ],
                ),
                name="ck_retention_anchor",
            ),
            models.CheckConstraint(
                condition=Q(
                    final_action__in=[
                        "DELETE",
                        "ANONYMIZE",
                        "BLOCK",
                        "ARCHIVE",
                    ],
                ),
                name="ck_retention_action",
            ),
        ]

    def __str__(self):
        return (
            f"{self.entity_type}: "
            f"{self.retention_days} días"
        )


class DataDisposalEvent(models.Model):
    class Action(models.TextChoices):
        DELETE = "DELETE", "Eliminar"
        ANONYMIZE = "ANONYMIZE", "Anonimizar"
        BLOCK = "BLOCK", "Bloquear"
        ARCHIVE = "ARCHIVE", "Archivar"

    class Status(models.TextChoices):
        DETECTED = "DETECTED", "Detectado"
        PENDING_APPROVAL = (
            "PENDING_APPROVAL",
            "Pendiente de aprobación",
        )
        APPROVED = "APPROVED", "Aprobado"
        EXECUTED = "EXECUTED", "Ejecutado"
        REJECTED = "REJECTED", "Rechazado"
        FAILED = "FAILED", "Fallido"
        CANCELLED = "CANCELLED", "Cancelado"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    retention_rule = models.ForeignKey(
        RetentionRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disposal_events",
        db_index=False,
    )

    entity_type = models.CharField(
        max_length=50,
    )

    entity_pk = models.TextField()

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DETECTED,
        db_default="DETECTED",
    )

    detected_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disposal_events_approved",
        db_index=False,
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    approval_notes_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disposal_events_executed",
        db_index=False,
    )

    executed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    evidence_sha256 = FixedCharField(
        max_length=64,
        null=True,
        blank=True,
    )

    error_code = models.CharField(
        max_length=80,
        null=True,
        blank=True,
    )

    error_message = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "data_disposal_events"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    action__in=[
                        "DELETE",
                        "ANONYMIZE",
                        "BLOCK",
                        "ARCHIVE",
                    ],
                ),
                name="ck_disposal_action",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "DETECTED",
                        "PENDING_APPROVAL",
                        "APPROVED",
                        "EXECUTED",
                        "REJECTED",
                        "FAILED",
                        "CANCELLED",
                    ],
                ),
                name="ck_disposal_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_disposal_key_version",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="APPROVED")
                    | Q(approved_at__isnull=False)
                ),
                name="ck_disposal_approved",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="EXECUTED")
                    | Q(executed_at__isnull=False)
                ),
                name="ck_disposal_executed",
            ),
            models.CheckConstraint(
                condition=(
                    Q(approved_at__isnull=True)
                    | Q(
                        approved_at__gte=F(
                            "detected_at"
                        )
                    )
                ),
                name="ck_disposal_approval_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(executed_at__isnull=True)
                    | Q(
                        executed_at__gte=F(
                            "detected_at"
                        )
                    )
                ),
                name="ck_disposal_execution_date",
            ),
            models.UniqueConstraint(
                fields=[
                    "entity_type",
                    "entity_pk",
                    "action",
                ],
                condition=Q(
                    status__in=[
                        "DETECTED",
                        "PENDING_APPROVAL",
                        "APPROVED",
                    ],
                ),
                name="uq_disposal_open_event",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "detected_at",
                ],
                condition=Q(
                    status__in=[
                        "DETECTED",
                        "PENDING_APPROVAL",
                        "APPROVED",
                    ],
                ),
                name="idx_disposal_pending",
            ),
            models.Index(
                fields=["retention_rule"],
                condition=Q(
                    retention_rule__isnull=False,
                ),
                name="idx_disposal_rule",
            ),
        ]

    def __str__(self):
        return (
            f"{self.entity_type}:{self.entity_pk} "
            f"- {self.action}"
        )