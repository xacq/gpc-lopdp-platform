import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import F, Q

from apps.core.fields import FixedCharField


class LegalDocument(models.Model):
    class DocumentType(models.TextChoices):
        PRIVACY_POLICY = (
            "PRIVACY_POLICY",
            "Política de Privacidad",
        )
        EMPLOYEE_NOTICE = (
            "EMPLOYEE_NOTICE",
            "Aviso Empleados",
        )
        CANDIDATE_NOTICE = (
            "CANDIDATE_NOTICE",
            "Aviso Candidatos",
        )
        CUSTOMER_VENDOR_NOTICE = (
            "CUSTOMER_VENDOR_NOTICE",
            "Aviso Clientes/Vendedores",
        )
        SUPPLIER_NOTICE = (
            "SUPPLIER_NOTICE",
            "Aviso Proveedores",
        )
        VIDEO_SURVEILLANCE_NOTICE = (
            "VIDEO_SURVEILLANCE_NOTICE",
            "Aviso Videovigilancia",
        )
        RIGHTS_NOTICE = (
            "RIGHTS_NOTICE",
            "Derechos y Contacto",
        )
        COOKIES_POLICY = (
            "COOKIES_POLICY",
            "Política de Cookies",
        )
        OTHER = (
            "OTHER",
            "Otro",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
    )

    title = models.CharField(
        max_length=250,
    )

    slug = models.CharField(
        max_length=180,
    )

    version = models.CharField(
        max_length=30,
    )

    content_html = models.TextField()

    content_sha256 = FixedCharField(
        max_length=64,
    )

    effective_from = models.DateTimeField()

    effective_to = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_published = models.BooleanField(
        default=False,
        db_default=False,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legal_documents_created",
        db_index=False,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    class Meta:
        db_table = "legal_documents"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    document_type__in=[
                        "PRIVACY_POLICY",
                        "EMPLOYEE_NOTICE",
                        "CANDIDATE_NOTICE",
                        "CUSTOMER_VENDOR_NOTICE",
                        "SUPPLIER_NOTICE",
                        "VIDEO_SURVEILLANCE_NOTICE",
                        "RIGHTS_NOTICE",
                        "COOKIES_POLICY",
                        "OTHER",
                    ],
                ),
                name="ck_legal_document_type_valid",
            ),
            models.UniqueConstraint(
                fields=[
                    "document_type",
                    "version",
                ],
                name="uq_legal_document_type_version",
            ),
            models.UniqueConstraint(
                fields=[
                    "slug",
                    "version",
                ],
                name="uq_legal_document_slug_version",
            ),
            models.UniqueConstraint(
                fields=["document_type"],
                condition=Q(
                    is_published=True,
                    effective_to__isnull=True,
                ),
                name="uq_legal_document_active_type",
            ),
            models.CheckConstraint(
                condition=(
                    Q(effective_to__isnull=True)
                    | Q(
                        effective_to__gt=F(
                            "effective_from"
                        )
                    )
                ),
                name="ck_legal_document_effective_dates",
            ),
        ]

        indexes = [
            models.Index(
                fields=["created_by"],
                condition=Q(
                    created_by__isnull=False,
                ),
                name="idx_legal_documents_creator",
            ),
        ]

        ordering = [
            "document_type",
            "-effective_from",
        ]

    def __str__(self):
        return f"{self.title} ({self.version})"


class RightCatalog(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    code = models.CharField(
        max_length=50,
        unique=True,
    )

    name = models.CharField(
        max_length=150,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    legal_reference = models.CharField(
        max_length=250,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_default=True,
    )

    class Meta:
        db_table = "rights_catalog"
        ordering = ["code"]

    def __str__(self):
        return self.name


class RightRule(models.Model):
    class DayCountType(models.TextChoices):
        BUSINESS = (
            "BUSINESS",
            "Días hábiles",
        )
        CALENDAR = (
            "CALENDAR",
            "Días calendario",
        )

    class ClarificationEffect(models.TextChoices):
        NO_CHANGE = (
            "NO_CHANGE",
            "Sin cambio",
        )
        PAUSE = (
            "PAUSE",
            "Pausa",
        )
        RESTART = (
            "RESTART",
            "Reinicio",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    right = models.OneToOneField(
        RightCatalog,
        on_delete=models.RESTRICT,
        related_name="rule",
        db_index=False,
    )

    response_days = models.IntegerField(
        default=15,
        db_default=15,
    )

    day_count_type = models.CharField(
        max_length=20,
        choices=DayCountType.choices,
        default=DayCountType.BUSINESS,
        db_default="BUSINESS",
    )

    extension_allowed = models.BooleanField(
        default=False,
        db_default=False,
    )

    extension_days = models.IntegerField(
        default=0,
        db_default=0,
    )

    warning_days = models.IntegerField(
        default=2,
        db_default=2,
    )

    clarification_effect = models.CharField(
        max_length=20,
        choices=ClarificationEffect.choices,
        default=ClarificationEffect.NO_CHANGE,
        db_default="NO_CHANGE",
    )

    is_active = models.BooleanField(
        default=True,
        db_default=True,
    )

    class Meta:
        db_table = "right_rules"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    response_days__gt=0,
                ),
                name="ck_right_rules_response_days",
            ),
            models.CheckConstraint(
                condition=Q(
                    day_count_type__in=[
                        "BUSINESS",
                        "CALENDAR",
                    ],
                ),
                name="ck_right_rules_day_count_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    extension_days__gte=0,
                ),
                name="ck_right_rules_extension_days",
            ),
            models.CheckConstraint(
                condition=Q(
                    warning_days__gte=0,
                ),
                name="ck_right_rules_warning_days",
            ),
            models.CheckConstraint(
                condition=Q(
                    clarification_effect__in=[
                        "NO_CHANGE",
                        "PAUSE",
                        "RESTART",
                    ],
                ),
                name=(
                    "ck_right_rules_clarification_effect"
                ),
            ),
            models.CheckConstraint(
                condition=(
                    Q(extension_allowed=True)
                    | Q(extension_days=0)
                ),
                name="ck_right_rules_extension_consistency",
            ),
        ]

    def __str__(self):
        return f"Regla: {self.right.name}"