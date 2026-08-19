from django import forms

from apps.cases.forms.requests import RequestCreateForm


class PublicRequestForm(RequestCreateForm):
    identity_document = forms.FileField(
        label="Documento de identidad (opcional)",
        required=False,
        help_text="PDF, JPG o PNG. Máximo 10 MB.",
    )
    authority_document = forms.FileField(
        label="Documento de representación (opcional)",
        required=False,
        help_text="PDF, JPG o PNG. Máximo 10 MB.",
    )
    supporting_document = forms.FileField(
        label="Documento de respaldo (opcional)",
        required=False,
        help_text="PDF, JPG o PNG. Máximo 10 MB.",
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
