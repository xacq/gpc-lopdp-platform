from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import sensitive_reauthentication_required
from apps.organization.forms import SystemSettingForm
from apps.organization.models import SystemSetting
from apps.organization.policies import can_manage_system_settings
from apps.organization.services import (
    SystemSettingsError,
    SystemSettingsService,
)


@login_required
@sensitive_reauthentication_required
@require_http_methods(["GET", "POST"])
def system_settings(request):
    if not can_manage_system_settings(request.user):
        raise PermissionDenied

    setting = SystemSetting.objects.filter(
        singleton_key=1
    ).first()
    form = SystemSettingForm(
        request.POST or None,
        request.FILES or None,
        instance=setting,
    )
    saved = False
    if request.method == "POST" and form.is_valid():
        try:
            setting = SystemSettingsService.save(
                values={
                    field: form.cleaned_data.get(field)
                    for field in SystemSettingsService.EDITABLE_FIELDS
                },
                actor=request.user,
            )
        except SystemSettingsError:
            form.add_error(
                None,
                "No fue posible guardar la configuración. "
                "Verifique RUC, dominio, URLs y zona horaria.",
            )
        else:
            form = SystemSettingForm(instance=setting)
            saved = True

    return render(
        request,
        "organization/system_settings.html",
        {
            "form": form,
            "saved": saved,
        },
    )
