from django.contrib.postgres.functions import RandomUUID
import uuid

from django.contrib.auth.base_user import (
    AbstractBaseUser,
    BaseUserManager,
)
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from .fields import CIEmailField


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(
        self,
        email,
        password=None,
        **extra_fields,
    ):
        if not email:
            raise ValueError(
                "El correo electrónico es obligatorio."
            )

        email = self.normalize_email(email).strip()

        user = self.model(
            email=email,
            **extra_fields,
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(
        self,
        email,
        password=None,
        **extra_fields,
    ):
        extra_fields.setdefault(
            "is_staff",
            True,
        )
        extra_fields.setdefault(
            "is_superuser",
            True,
        )
        extra_fields.setdefault(
            "is_active",
            True,
        )

        if extra_fields.get("is_staff") is not True:
            raise ValueError(
                "El superusuario debe tener is_staff=True."
            )

        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "El superusuario debe tener "
                "is_superuser=True."
            )

        return self.create_user(
            email,
            password,
            **extra_fields,
        )


class User(AbstractBaseUser):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    email = CIEmailField(
        unique=True,
        max_length=254,
    )

    full_name = models.CharField(
        max_length=180,
    )

    is_active = models.BooleanField(
        default=True,
    )

    is_staff = models.BooleanField(
        default=False,
    )

    is_superuser = models.BooleanField(
        default=False,
    )

    failed_login_attempts = models.IntegerField(
        default=0,
    )

    locked_until = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        db_default=Now(),
        editable=False,
    )

    updated_at = models.DateTimeField(
        db_default=Now(),
    )

    objects = UserManager()

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = [
        "full_name",
    ]

    class Meta:
        db_table = "users"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    failed_login_attempts__gte=0
                ),
                name=(
                    "ck_users_failed_login_"
                    "attempts_nonnegative"
                ),
            ),
        ]

        ordering = [
            "email",
        ]

    def __str__(self):
        return self.email

    def has_perm(
        self,
        perm,
        obj=None,
    ):
        return (
            self.is_active
            and self.is_superuser
        )

    def has_module_perms(
        self,
        app_label,
    ):
        return (
            self.is_active
            and self.is_superuser
        )


class Role(models.Model):
    class Code(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        DPD = "DPD", "Delegado de Protección de Datos"
        RESPONSABLE = "RESPONSABLE", "Responsable del tratamiento"
        OPERADOR = "OPERADOR", "Operador"
        AUDITOR = "AUDITOR", "Auditor"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    code = models.CharField(
        max_length=30,
        choices=Code.choices,
        unique=True,
    )

    name = models.CharField(
        max_length=100,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        db_default=Now(),
        editable=False,
    )
    class Meta:
        db_table = "roles"
        ordering = ["code"]

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    code__in=[
                        "ADMIN",
                        "DPD",
                        "RESPONSABLE",
                        "OPERADOR",
                        "AUDITOR",
                    ],
                ),
                name="ck_roles_code_valid",
            ),
        ]

    def __str__(self):
        return self.name


class UserRole(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.RESTRICT,
        related_name="user_assignments",
    )

    is_primary = models.BooleanField(
        default=False,
    )

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_assigned",
    )

    assigned_at = models.DateTimeField(
        db_default=Now(),
        editable=False,
    )

    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "user_roles"

        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(revoked_at__isnull=True)
                    | Q(revoked_at__gte=models.F("assigned_at"))
                ),
                name="ck_user_roles_revoked_after_assigned",
            ),
            models.UniqueConstraint(
                fields=[
                    "user",
                    "role",
                ],
                condition=Q(
                    revoked_at__isnull=True,
                ),
                name="uq_user_active_role",
            ),
            models.UniqueConstraint(
                fields=[
                    "user",
                ],
                condition=Q(
                    is_primary=True,
                    revoked_at__isnull=True,
                ),
                name="uq_user_primary_role",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "-assigned_at",
                ],
                name="idx_user_roles_user_history",
            ),
            models.Index(
                fields=[
                    "role",
                    "user",
                ],
                condition=Q(
                    revoked_at__isnull=True,
                ),
                name="idx_user_roles_role_active",
            ),
        ]


class MFADevice(models.Model):
    class DeviceType(models.TextChoices):
        TOTP = "TOTP", "TOTP"
        RECOVERY_CODES = (
            "RECOVERY_CODES",
            "Códigos de recuperación",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mfa_devices",
    )

    device_name = models.CharField(
        max_length=100,
    )

    device_type = models.CharField(
        max_length=20,
        choices=DeviceType.choices,
        default=DeviceType.TOTP,
    )

    secret_encrypted = models.BinaryField()

    encryption_key_version = models.PositiveSmallIntegerField(
        default=1,
    )

    is_confirmed = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        db_default=Now(),
        editable=False,
    )

    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "mfa_devices"

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    device_type__in=[
                        "TOTP",
                        "RECOVERY_CODES",
                    ],
                ),
                name="ck_mfa_device_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    encryption_key_version__gt=0,
                ),
                name="ck_mfa_key_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(revoked_at__isnull=True)
                    | Q(revoked_at__gte=models.F("created_at"))
                ),
                name="ck_mfa_revoked_after_created",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_confirmed=False)
                    | Q(confirmed_at__isnull=False)
                ),
                name="ck_mfa_confirmed_timestamp",
            ),
        ]

        indexes = [
            models.Index(
                fields=["user"],
                condition=Q(
                    is_active=True,
                    revoked_at__isnull=True,
                ),
                name="idx_mfa_devices_user_active",
            ),
        ]


