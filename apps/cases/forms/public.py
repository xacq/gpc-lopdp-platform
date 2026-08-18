from django import forms


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
