from django import forms


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )

    password = forms.CharField(
        label="Contraseña",
        max_length=4096,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
            }
        ),
    )

    next = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )


class TOTPForm(forms.Form):
    code = forms.CharField(
        label="Código de verificación",
        min_length=6,
        max_length=8,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "autofocus": True,
            }
        ),
    )


class MFAChallengeForm(forms.Form):
    code = forms.CharField(
        label="Código de verificación o recuperación",
        min_length=6,
        max_length=32,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "autofocus": True,
            }
        ),
    )
