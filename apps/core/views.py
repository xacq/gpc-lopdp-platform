from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting


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
        },
    )


@require_GET
def contact(request):
    return render(
        request,
        "core/contact.html",
        {"settings": SystemSetting.objects.first()},
    )
