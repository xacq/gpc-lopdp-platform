import uuid

from django.conf import settings
from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.db import models
from django.db.models import F, Q

from apps.core.fields import FixedCharField


DOCUMENT_TYPES = [
    "CEDULA",
    "RUC",
    "PASSPORT",
    "OTHER",
]


class DataSubject(models.Model):
    class SubjectType(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Empleado"
        CANDIDATE = "CANDIDATE", "Candidato"
        CUSTOMER = "CUSTOMER", "Cliente"
        VENDOR = "VENDOR", "Vendedor"
        SUPPLIER = "SUPPLIER", "Proveedor"
        FORMER_EMPLOYEE = (
            "FORMER_EMPLOYEE",
            "Exempleado",
        )
        OTHER = "OTHER", "Otro"

    class DocumentType(models.TextChoices):
        CEDULA = "CEDULA", "Cédula"
        RUC = "RUC", "RUC"
        PASSPORT = "PASSPORT", "Pasaporte"
        OTHER = "OTHER", "Otro"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    subject_type = models.CharField(
        max_length=30,
        choices=SubjectType.choices,
    )

    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
    )

    document_number_encrypted = models.BinaryField()

    document_number_lookup_hash = FixedCharField(
        max_length=64,
        unique=True,
    )

    full_name_encrypted = models.BinaryField()

    email_encrypted = models.BinaryField()

    email_lookup_hash = FixedCharField(
        max_length=64,
    )

    phone_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    lookup_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    updated_at = models.DateTimeField(
        db_default=TransactionNow(),
    )

    class Meta:
        db_table = "data_subjects"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    subject_type__in=[
                        "EMPLOYEE",
                        "CANDIDATE",
                        "CUSTOMER",
                        "VENDOR",
                        "SUPPLIER",
                        "FORMER_EMPLOYEE",
                        "OTHER",
                    ]
                ),
                name="ck_data_subjects_subject_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    document_type__in=DOCUMENT_TYPES,
                ),
                name="ck_data_subjects_document_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_data_subjects_encryption_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    lookup_key_version__gt=0,
                ),
                name="ck_data_subjects_lookup_key_version",
            ),
        ]

        indexes = [
            models.Index(
                fields=["email_lookup_hash"],
                name="idx_ds_email_lookup",
            ),
        ]

    def __str__(self):
        return str(self.id)


class SubjectRepresentative(models.Model):
    class DocumentType(models.TextChoices):
        CEDULA = "CEDULA", "Cédula"
        RUC = "RUC", "RUC"
        PASSPORT = "PASSPORT", "Pasaporte"
        OTHER = "OTHER", "Otro"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        VERIFIED = "VERIFIED", "Verificado"
        REJECTED = "REJECTED", "Rechazado"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    data_subject = models.ForeignKey(
        DataSubject,
        on_delete=models.CASCADE,
        related_name="representatives",
        db_index=False,
    )

    representative_name_encrypted = models.BinaryField()

    representative_document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
    )

    representative_document_encrypted = models.BinaryField()

    representative_document_lookup_hash = FixedCharField(
        max_length=64,
    )

    representative_email_encrypted = models.BinaryField(
        null=True,
        blank=True,
    )

    encryption_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    lookup_key_version = models.SmallIntegerField(
        default=1,
        db_default=1,
    )

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_default="PENDING",
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="representatives_verified",
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
        db_table = "subject_representatives"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    representative_document_type__in=DOCUMENT_TYPES,
                ),
                name="ck_representative_document_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_representative_encryption_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    lookup_key_version__gt=0,
                ),
                name="ck_representative_lookup_key_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    verification_status__in=[
                        "PENDING",
                        "VERIFIED",
                        "REJECTED",
                    ],
                ),
                name="ck_representative_verification_status",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(
                        verification_status="VERIFIED"
                    )
                    | Q(
                        verified_at__isnull=False
                    )
                ),
                name="ck_representative_verified_timestamp",
            ),
            models.UniqueConstraint(
                fields=[
                    "id",
                    "data_subject",
                ],
                name="uq_representative_id_subject",
            ),
            models.UniqueConstraint(
                fields=[
                    "data_subject",
                    "representative_document_lookup_hash",
                ],
                name="uq_representative_subject_document",
            ),
        ]

        indexes = [
            models.Index(
                fields=["data_subject"],
                name="idx_representatives_subject",
            ),
            models.Index(
                fields=[
                    "representative_document_lookup_hash"
                ],
                name="idx_rep_doc_lookup",
            ),
        ]

    def __str__(self):
        return str(self.id)