from django.core.management.base import BaseCommand

from apps.legal_content.models import RightCatalog, RightRule


RIGHTS = (
    (
        "ACCESS",
        "Acceso",
        (
            "Conocer qué datos suyos tiene la organización, "
            "para qué los usa y con quién los comparte."
        ),
        "LOPDP, art. 19",
    ),
    (
        "RECTIFICATION_UPDATE",
        "Rectificación",
        (
            "Solicitar la corrección de datos incorrectos, "
            "incompletos o desactualizados."
        ),
        "LOPDP, art. 20",
    ),
    (
        "ELIMINATION",
        "Eliminación",
        (
            "Pedir la eliminación de sus datos cuando ya no sean "
            "necesarios o el tratamiento carezca de base legal."
        ),
        "LOPDP, art. 21",
    ),
    (
        "OPPOSITION",
        "Oposición",
        (
            "Oponerse al tratamiento de sus datos, especialmente "
            "para fines de mercadotecnia directa."
        ),
        "LOPDP, art. 22",
    ),
    (
        "PORTABILITY",
        "Portabilidad",
        (
            "Recibir los datos en formato compatible, actualizado, "
            "estructurado, común, interoperable y de lectura mecánica, o "
            "pedir su transmisión."
        ),
        "LOPDP, art. 23",
    ),
    (
        "SUSPENSION",
        "Suspensión del tratamiento",
        "Solicitar el cese temporal del tratamiento en los casos previstos por la ley.",
        "LOPDP, art. 24",
    ),
)


class Command(BaseCommand):
    help = "Carga los derechos LOPDP y sus reglas de atención por defecto."

    def handle(self, *args, **options):
        for code, name, description, legal_reference in RIGHTS:
            right, _ = RightCatalog.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "legal_reference": legal_reference,
                    "is_active": True,
                },
            )
            RightRule.objects.update_or_create(
                right=right,
                defaults={
                    "response_days": 15,
                    "day_count_type": RightRule.DayCountType.CALENDAR,
                    "extension_allowed": False,
                    "extension_days": 0,
                    "warning_days": 2,
                    "clarification_effect": (
                        RightRule.ClarificationEffect.NO_CHANGE
                    ),
                    "is_active": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS("Catálogo LOPDP configurado: 6 derechos.")
        )
