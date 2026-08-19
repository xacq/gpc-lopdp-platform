from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting


PRELIMINARY_RIGHTS = (
    (
        "Acceso",
        "Solicitar información sobre los datos personales tratados y la "
        "forma en que se utilizan.",
    ),
    (
        "Rectificación y actualización",
        "Solicitar la corrección o actualización de datos inexactos o "
        "incompletos.",
    ),
    (
        "Eliminación",
        "Solicitar la supresión de datos cuando se cumplan las condiciones "
        "aplicables.",
    ),
    (
        "Oposición",
        "Oponerse a determinados tratamientos en los casos previstos por la "
        "normativa.",
    ),
    (
        "Portabilidad",
        "Solicitar la entrega o transferencia de datos en un formato "
        "estructurado cuando corresponda.",
    ),
    (
        "Suspensión",
        "Solicitar la suspensión temporal de un tratamiento mientras se "
        "revisa su procedencia.",
    ),
    (
        "Decisiones automatizadas",
        "Solicitar garantías frente a decisiones basadas únicamente en "
        "tratamientos automatizados.",
    ),
    (
        "Información",
        "Conocer finalidades, conservación, transferencias y medidas de "
        "seguridad aplicables.",
    ),
)

PROVISIONAL_DPD_NAME = "María Elena Terán"


@require_GET
def home(request):
    return render(request, "core/home.html")


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
            "provisional_dpd_name": PROVISIONAL_DPD_NAME,
        },
    )
