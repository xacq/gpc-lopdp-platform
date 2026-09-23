from django.core.management.base import BaseCommand

from apps.legal_content.models import RightCatalog, RightRule


RIGHTS = (
    (
        "ACCESS",
        "Acceso",
        (
            "Conocer y obtener gratuitamente los datos personales tratados "
            "y la información legalmente exigida."
        ),
        "LOPDP, art. 13",
    ),
    (
        "RECTIFICATION_UPDATE",
        "Rectificación y actualización",
        "Corregir o actualizar datos personales inexactos o incompletos.",
        "LOPDP, art. 14",
    ),
    (
        "ELIMINATION",
        "Eliminación",
        "Solicitar la supresión de datos personales cuando proceda conforme a la ley.",
        "LOPDP, art. 15",
    ),
    (
        "OPPOSITION",
        "Oposición",
        "Oponerse o negarse al tratamiento en los casos previstos por la ley.",
        "LOPDP, art. 16",
    ),
    (
        "PORTABILITY",
        "Portabilidad",
        (
            "Recibir los datos en formato compatible, actualizado, "
            "estructurado, común, interoperable y de lectura mecánica, o "
            "pedir su transmisión."
        ),
        "LOPDP, art. 17",
    ),
    (
        "SUSPENSION",
        "Suspensión del tratamiento",
        "Solicitar el cese temporal del tratamiento en los casos previstos por la ley.",
        "LOPDP, art. 18",
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
