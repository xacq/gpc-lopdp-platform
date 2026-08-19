from django import forms

from apps.accounts.models import Role


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "usuario@vinesa.com",
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
                "placeholder": "Ingresa tu contraseña",
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
                "placeholder": "000000",
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
                "placeholder": "Código MFA o de respaldo",
            }
        ),
    )


class UserListFilterForm(forms.Form):
    search = forms.CharField(required=False, max_length=180)
    role = forms.ModelChoiceField(
        required=False,
        queryset=Role.objects.none(),
        empty_label="Todos los roles",
    )
    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Todos los estados"),
            ("ACTIVE", "Activos"),
            ("INACTIVE", "Inactivos"),
            ("LOCKED", "Bloqueados"),
        ),
    )
    page = forms.IntegerField(required=False, min_value=1, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.filter(
            is_active=True
        ).order_by("code")

    def clean_search(self):
        return (self.cleaned_data.get("search") or "").strip()


class ActiveRoleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, role):
        return f"{role.get_code_display()} ({role.code})"


class UserCreateForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={"autocomplete": "off"}
        ),
    )
    full_name = forms.CharField(
        label="Nombre completo",
        max_length=180,
    )
    role = ActiveRoleChoiceField(
        label="Rol primario",
        queryset=Role.objects.none(),
    )
    password1 = forms.CharField(
        label="Contraseña inicial",
        max_length=4096,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        max_length=4096,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.filter(
            is_active=True
        ).order_by("code")

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error(
                "password2",
                "Las contraseñas no coinciden.",
            )
        return cleaned


class UserRoleForm(forms.Form):
    role = ActiveRoleChoiceField(
        label="Rol primario",
        queryset=Role.objects.none(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.filter(
            is_active=True
        ).order_by("code")


class UserPasswordResetForm(forms.Form):
    password1 = forms.CharField(
        label="Nueva contraseña",
        max_length=4096,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        max_length=4096,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error(
                "password2",
                "Las contraseñas no coinciden.",
            )
        return cleaned
