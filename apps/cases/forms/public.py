from django import forms
from django.urls import reverse
from django.utils.html import format_html

from apps.cases.forms.requests import RequestCreateForm
from apps.evidence.services.attachments import AttachmentService
from apps.organization.models import SystemSetting


PUBLIC_FILE_HELP_TEXT = (
    "PDF, JPG o PNG. Tamaño máximo por archivo: "
    f"{AttachmentService.MAX_FILE_SIZE_MB} MB."
)

ADDITIONAL_DOCUMENTATION_HELP_TEXT = (
    "Si tienes más documentación que no puedas adjuntar por tamaño o cantidad, "
    "indícalo en esta descripción y señala que enviarás el resto desde el "
    "mismo correo electrónico registrado en la solicitud, para coordinarlo "
    "con el Delegado de Protección de Datos."
)


class PublicRequestForm(RequestCreateForm):
    identity_document = forms.FileField(
        label="Documento de identidad (opcional)",
        required=False,
        help_text=PUBLIC_FILE_HELP_TEXT,
    )
    authority_document = forms.FileField(
        label="Documento de representación (opcional)",
        required=False,
        help_text=PUBLIC_FILE_HELP_TEXT,
    )
    supporting_document = forms.FileField(
        label="Documento de respaldo (opcional)",
        required=False,
        help_text=PUBLIC_FILE_HELP_TEXT,
    )
    privacy_acknowledgement = forms.BooleanField(
        label=(
            "Confirmo que los datos proporcionados son correctos y que "
            "puedo recibir comunicaciones sobre esta solicitud."
        ),
        required=True,
    )
    website = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setting = SystemSetting.objects.filter(singleton_key=1).first()
        organization_name = "la empresa"
        if setting is not None:
            organization_name = setting.trade_name or setting.legal_name

        self.fields["request_details"].help_text = (
            ADDITIONAL_DOCUMENTATION_HELP_TEXT
        )
        self.fields["privacy_acknowledgement"].label = format_html(
            (
                "Confirmo que los datos proporcionados son correctos para "
                "evitar retrasos en el proceso de verificación de esta "
                "solicitud. También acepto la "
                '<a href="{}" target="_blank" rel="noopener">'
                "Política de Privacidad</a> de {} y autorizo recibir "
                "comunicaciones relacionadas con esta solicitud."
            ),
            reverse("legal_content:public_document", args=["privacidad"]),
            organization_name,
        )
        self.fields.pop("source_channel")
        self.fields["subject_type"].choices = [
            ("", "Seleccione un tipo de titular"),
            *self.fields["subject_type"].choices,
        ]
        self.fields["document_type"].choices = [
            ("", "Seleccione un tipo de documento"),
            *self.fields["document_type"].choices,
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError(
                "No fue posible procesar la solicitud."
            )
        if cleaned.get("authority_document") and not (
            cleaned.get("has_representative")
            or cleaned.get("representative_name")
        ):
            self.add_error(
                "authority_document",
                "Este documento requiere los datos del representante.",
            )
        return cleaned


class PublicTrackingForm(forms.Form):
    reference_number = forms.CharField(
        label="Número de referencia",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
            }
        ),
    )
    token = forms.CharField(
        label="Código de seguimiento",
        max_length=255,
        strip=True,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "off",
                "spellcheck": "false",
            },
        ),
    )


class PublicTrackingCodeResendForm(forms.Form):
    reference_number = forms.CharField(
        label="Número de referencia",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
            }
        ),
    )
    email = forms.EmailField(
        label="Correo electrónico registrado",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "spellcheck": "false",
            }
        ),
    )


class PublicDownloadForm(forms.Form):
    reference_number = forms.CharField(
        label="Número de referencia",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
            }
        ),
    )
    attachment_id = forms.UUIDField(
        label="Identificador del documento",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
    )
    token = forms.CharField(
        label="Código de descarga",
        max_length=255,
        strip=True,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "off",
                "spellcheck": "false",
            },
        ),
    )


class PublicEmailVerificationForm(forms.Form):
    reference_number = forms.CharField(
        label="Número de referencia",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
            }
        ),
    )
    token = forms.CharField(
        label="Código de verificación",
        max_length=255,
        strip=True,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "off",
                "spellcheck": "false",
            },
        ),
    )
