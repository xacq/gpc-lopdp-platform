from django import forms

from apps.organization.models import SystemSetting


class SystemSettingForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = (
            "legal_name",
            "trade_name",
            "ruc",
            "domain",
            "address",
            "phone",
            "contact_email",
            "controller_name",
            "controller_email",
            "controller_phone",
            "dpd_name",
            "dpd_email",
            "dpd_phone",
            "complaint_authority_name",
            "complaint_channel_url",
            "complaint_instructions",
            "request_prefix",
            "timezone",
            "logo_image",
            "favicon_image",
            "logo_url",
            "favicon_url",
            "primary_color",
            "secondary_color",
            "accent_color",
        )
        labels = {
            "logo_image": "Subir archivo de logotipo",
            "favicon_image": "Subir archivo de favicon",
            "logo_url": "O ingresar URL externa del logotipo",
            "favicon_url": "O ingresar URL externa del favicon",
            "primary_color": "Color primario (Rojo principal)",
            "secondary_color": "Color secundario (Vino/Oscuro)",
            "accent_color": "Color de acento (Rojo oscuro/Hover)",
        }
        help_texts = {
            "logo_image": "Formatos aceptados: PNG, SVG, JPG, WebP. Si no se sube, se usará el logotipo por defecto.",
            "favicon_image": "Formatos aceptados: ICO, PNG, SVG. Si no se sube, se usará el favicon por defecto.",
            "primary_color": "Formato hexadecimal #RRGGBB (ej. #C8393C)",
            "secondary_color": "Formato hexadecimal #RRGGBB (ej. #552A2A)",
            "accent_color": "Formato hexadecimal #RRGGBB (ej. #A02F30)",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "complaint_instructions": forms.Textarea(
                attrs={"rows": 4}
            ),
            "logo_image": forms.ClearableFileInput(
                attrs={"accept": "image/*,.svg,.ico", "class": "branding-file-input"}
            ),
            "favicon_image": forms.ClearableFileInput(
                attrs={"accept": "image/*,.ico,.svg", "class": "branding-file-input"}
            ),
            "logo_url": forms.URLInput(
                attrs={"placeholder": "https://assets.ejemplo.com/logo.svg"}
            ),
            "favicon_url": forms.URLInput(
                attrs={"placeholder": "https://assets.ejemplo.com/favicon.ico"}
            ),
            "primary_color": forms.TextInput(
                attrs={"placeholder": "#C8393C", "class": "form-control color-hex-input", "maxlength": 7}
            ),
            "secondary_color": forms.TextInput(
                attrs={"placeholder": "#552A2A", "class": "form-control color-hex-input", "maxlength": 7}
            ),
            "accent_color": forms.TextInput(
                attrs={"placeholder": "#A02F30", "class": "form-control color-hex-input", "maxlength": 7}
            ),
        }
