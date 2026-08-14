from django.db import models

# Create your models here.

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