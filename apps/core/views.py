from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.legal_content.models import RightCatalog
from apps.organization.defaults import (
    VINESA_PRIVACY_POLICY_URL,
    VINESA_SYSTEM_SETTINGS,
)
from apps.organization.models import SystemSetting


PRELIMINARY_RIGHTS = (
    {
        "name": "Acceso",
        "description": (
            "Solicitar información sobre los datos personales tratados y "
            "la forma en que se utilizan."
        ),
    },
    {
        "name": "Rectificación",
        "description": (
            "Solicitar la corrección de datos inexactos o incompletos."
        ),
    },
    {
        "name": "Eliminación",
        "description": (
            "Solicitar la supresión de datos cuando se cumplan las "
            "condiciones aplicables."
        ),
    },
    {
        "name": "Oposición",
        "description": (
            "Oponerse a determinados tratamientos en los casos previstos "
            "por la normativa."
        ),
    },
)

PROVISIONAL_DPD_NAME = "María Elena Terán"


@require_GET
def home(request):
    rights = list(
        RightCatalog.objects.filter(is_active=True).order_by("code")
    )
    return render(
        request,
        "core/home.html",
        {"rights": rights or PRELIMINARY_RIGHTS},
    )


@require_GET
def rights(request):
    return render(
        request,
        "core/rights.html",
        {
            "rights": RightCatalog.objects.filter(is_active=True).order_by(
                "code"
            ),
            "preliminary_rights": PRELIMINARY_RIGHTS,
        },
    )


@require_GET
def contact(request):
    return render(
        request,
        "core/contact.html",
        {
            "settings": SystemSetting.objects.first(),
            "provisional_settings": VINESA_SYSTEM_SETTINGS,
            "privacy_policy_url": VINESA_PRIVACY_POLICY_URL,
            "provisional_dpd_name": PROVISIONAL_DPD_NAME,
        },
    )
