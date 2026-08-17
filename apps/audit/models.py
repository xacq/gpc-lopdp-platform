import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import Q, Value

from apps.core.fields import FixedCharField


class AuditLog(models.Model):
    class ActorType(models.TextChoices):
        USER = "USER", "Usuario"
        SYSTEM = "SYSTEM", "Sistema"

    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        API = "API", "API"
        CELERY = "CELERY", "Celery"
        SIGNAL = "SIGNAL", "Signal"
        COMMAND = "COMMAND", "Comando"
        SYSTEM = "SYSTEM", "Sistema"

    id = models.BigAutoField(
        primary_key=True,
    )

    actor_type = models.CharField(
        max_length=10,
        choices=ActorType.choices,
        default=ActorType.USER,
        db_default="USER",
    )

    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
        db_index=False,
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.WEB,
        db_default="WEB",
    )

    correlation_id = models.UUIDField(
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    action = models.CharField(
        max_length=100,
    )

    entity_type = models.CharField(
        max_length=50,
    )

    entity_pk = models.TextField(
        null=True,
        blank=True,
    )

    description = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    reason_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    previous_values = models.JSONField(
        null=True,
        blank=True,
    )

    new_values = models.JSONField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        db_default=Value(
            {},
            output_field=models.JSONField(),
        ),
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

    chain_scope = models.CharField(
        max_length=50,
        default="GLOBAL",
        db_default="GLOBAL",
    )

    chain_position = models.BigIntegerField()

    previous_hash = FixedCharField(
        max_length=64,
        null=True,
        blank=True,
    )

    entry_hash = FixedCharField(
        max_length=64,
        unique=True,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "audit_logs"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    actor_type__in=[
                        "USER",
                        "SYSTEM",
                    ],
                ),
                name="ck_audit_actor_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    source__in=[
                        "WEB",
                        "API",
                        "CELERY",
                        "SIGNAL",
                        "COMMAND",
                        "SYSTEM",
                    ],
                ),
                name="ck_audit_source",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_audit_key_version",
            ),
            models.CheckConstraint(
                condition=(
                    Q(actor_type="SYSTEM")
                    | Q(actor_user__isnull=False)
                ),
                name="ck_audit_actor_user",
            ),
            models.CheckConstraint(
                condition=Q(
                    chain_position__gt=0,
                ),
                name="ck_audit_chain_position",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(chain_position=1)
                    | Q(previous_hash__isnull=True)
                ),
                name="ck_audit_first_hash",
            ),
            models.UniqueConstraint(
                fields=[
                    "chain_scope",
                    "chain_position",
                ],
                name="uq_audit_chain_position",
            ),
        ]

        indexes = [
            models.Index(
                fields=["-created_at"],
                name="idx_audit_created_at",
            ),
            models.Index(
                fields=[
                    "entity_type",
                    "entity_pk",
                    "-created_at",
                ],
                name="idx_audit_entity",
            ),
            models.Index(
                fields=["correlation_id"],
                name="idx_audit_correlation",
            ),
            models.Index(
                fields=[
                    "actor_user",
                    "-created_at",
                ],
                condition=Q(
                    actor_user__isnull=False,
                ),
                name="idx_audit_actor",
            ),
        ]

    def __str__(self):
        return (
            f"{self.chain_scope}:{self.chain_position} "
            f"{self.action}"
        )