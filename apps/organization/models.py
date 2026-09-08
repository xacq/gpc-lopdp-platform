import os
import uuid

from django.contrib.postgres.functions import (
    RandomUUID,
    TransactionNow,
)
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.fields import (
    CIEmailField,
    CITextField,
)


HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"

hex_color_validator = RegexValidator(
    regex=HEX_COLOR_PATTERN,
    message=(
        "El color debe utilizar formato hexadecimal "
        "#RRGGBB."
    ),
)

VALID_BRANDING_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".ico",
    ".gif",
}


def validate_branding_image(value):
    if not value or not hasattr(value, "name") or not value.name:
        return
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in VALID_BRANDING_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(VALID_BRANDING_IMAGE_EXTENSIONS))
        raise ValidationError(
            f"Formato no permitido. Solo se permiten imágenes ({allowed})."
        )


class SystemSetting(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )

    singleton_key = models.SmallIntegerField(
        default=1,
        db_default=1,
        unique=True,
        editable=False,
    )

    legal_name = models.CharField(
        max_length=180,
    )

    trade_name = models.CharField(
        max_length=180,
        null=True,
        blank=True,
    )

    ruc = models.CharField(
        max_length=13,
    )

    domain = CITextField(
        unique=True,
    )

    address = models.TextField(
        null=True,
        blank=True,
    )

    phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    contact_email = CIEmailField(
        max_length=254,
    )

    controller_name = models.CharField(
        max_length=180,
        null=True,
        blank=True,
    )

    controller_email = CIEmailField(
        max_length=254,
        null=True,
        blank=True,
    )

    controller_phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    dpd_name = models.CharField(
        max_length=180,
        null=True,
        blank=True,
    )

    dpd_email = CIEmailField(
        max_length=254,
        null=True,
        blank=True,
    )

    dpd_phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    complaint_authority_name = models.CharField(
        max_length=180,
        default=(
            "Superintendencia de Protección "
            "de Datos Personales"
        ),
        db_default=(
            "Superintendencia de Protección "
            "de Datos Personales"
        ),
    )

    complaint_channel_url = models.TextField(
        null=True,
        blank=True,
    )

    complaint_instructions = models.TextField(
        null=True,
        blank=True,
    )

    request_prefix = models.CharField(
        max_length=10,
    )

    timezone = models.CharField(
        max_length=50,
        default="America/Guayaquil",
        db_default="America/Guayaquil",
    )

    logo_image = models.FileField(
        upload_to="branding/",
        null=True,
        blank=True,
        validators=[validate_branding_image],
    )

    favicon_image = models.FileField(
        upload_to="branding/",
        null=True,
        blank=True,
        validators=[validate_branding_image],
    )

    logo_url = models.TextField(
        null=True,
        blank=True,
    )

    favicon_url = models.TextField(
        null=True,
        blank=True,
    )

    @property
    def effective_logo_url(self) -> str | None:
        if self.logo_image:
            try:
                return self.logo_image.url
            except ValueError:
                pass
        return self.logo_url or None

    @property
    def effective_favicon_url(self) -> str | None:
        if self.favicon_image:
            try:
                return self.favicon_image.url
            except ValueError:
                pass
        return self.favicon_url or None

    primary_color = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        validators=[hex_color_validator],
    )

    secondary_color = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        validators=[hex_color_validator],
    )

    accent_color = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        validators=[hex_color_validator],
    )

    background_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    active_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    separator_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    border_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    secondary_text_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    success_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    info_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    warning_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])
    error_color = models.CharField(max_length=7, null=True, blank=True, validators=[hex_color_validator])

    created_at = models.DateTimeField(
        db_default=TransactionNow(),
        editable=False,
    )

    updated_at = models.DateTimeField(
        db_default=TransactionNow(),
    )

    class Meta:
        db_table = "system_settings"

        constraints = [
            models.UniqueConstraint(
                fields=["ruc"],
                name="uq_system_settings_ruc",
            ),
            models.CheckConstraint(
                condition=Q(singleton_key=1),
                name="ck_system_settings_singleton",
            ),
            models.CheckConstraint(
                condition=(
                    Q(primary_color__isnull=True)
                    | Q(
                        primary_color__regex=(
                            HEX_COLOR_PATTERN
                        )
                    )
                ),
                name="ck_system_settings_primary_color",
            ),
            models.CheckConstraint(
                condition=(
                    Q(secondary_color__isnull=True)
                    | Q(
                        secondary_color__regex=(
                            HEX_COLOR_PATTERN
                        )
                    )
                ),
                name="ck_system_settings_secondary_color",
            ),
            models.CheckConstraint(
                condition=(
                    Q(accent_color__isnull=True)
                    | Q(
                        accent_color__regex=(
                            HEX_COLOR_PATTERN
                        )
                    )
                ),
                name="ck_system_settings_accent_color",
            ),
            *[
                models.CheckConstraint(
                    condition=Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__regex": HEX_COLOR_PATTERN}),
                    name=f"ck_system_settings_{field}",
                )
                for field in (
                    "background_color", "active_color", "separator_color", "border_color",
                    "secondary_text_color", "success_color", "info_color", "warning_color", "error_color",
                )
            ],
        ]

    def __str__(self):
        return self.trade_name or self.legal_name
