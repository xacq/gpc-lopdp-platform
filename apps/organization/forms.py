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
            "background_color",
            "active_color",
            "separator_color",
            "border_color",
            "secondary_text_color",
            "success_color",
            "info_color",
            "warning_color",
            "error_color",
        )
        labels = {
            "logo_image": "Subir archivo de logotipo",
            "favicon_image": "Subir archivo de favicon",
            "logo_url": "O ingresar URL externa del logotipo",
            "favicon_url": "O ingresar URL externa del favicon",
            "primary_color": "Color primario (Rojo principal)",
            "secondary_color": "Color secundario (Vino/Oscuro)",
            "accent_color": "Color de acento (Rojo oscuro/Hover)",
            "background_color": "Fondo general",
            "active_color": "Estado activo/presionado",
            "separator_color": "Separadores",
            "border_color": "Bordes y formularios",
            "secondary_text_color": "Texto secundario",
            "success_color": "Éxito",
            "info_color": "Información",
            "warning_color": "Advertencia",
            "error_color": "Error o rechazo",
        }
        help_texts = {
            "logo_image": "Formatos aceptados: PNG, SVG, JPG, WebP. Si no se sube, se usará el logotipo por defecto.",
            "favicon_image": "Formatos aceptados: ICO, PNG, SVG. Si no se sube, se usará el favicon por defecto.",
            "primary_color": "Escribe un código hexadecimal #RRGGBB (ej. #C8393C) o elige el color en el recuadro.",
            "secondary_color": "Escribe un código hexadecimal #RRGGBB (ej. #552A2A) o elige el color en el recuadro.",
            "accent_color": "Escribe un código hexadecimal #RRGGBB (ej. #A02F30) o elige el color en el recuadro.",
            "background_color": "Color base de fondos de la interfaz.",
            "active_color": "Color para elementos activos o presionados.",
            "separator_color": "Color de líneas y separadores suaves.",
            "border_color": "Color accesible de bordes e inputs.",
            "secondary_text_color": "Color de textos auxiliares y metadatos.",
            "success_color": "Color semántico de operaciones exitosas.",
            "info_color": "Color semántico informativo.",
            "warning_color": "Color semántico de advertencia.",
            "error_color": "Color semántico de error o rechazo.",
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
            **{
                field: forms.TextInput(
                    attrs={"placeholder": placeholder, "class": "form-control color-hex-input", "maxlength": 7}
                )
                for field, placeholder in {
                    "background_color": "#FAF7F7", "active_color": "#782224",
                    "separator_color": "#E8E3E3", "border_color": "#978B8B",
                    "secondary_text_color": "#756C6C", "success_color": "#5A6B43",
                    "info_color": "#24566B", "warning_color": "#8A5B00", "error_color": "#B42318",
                }.items()
            },
        }
