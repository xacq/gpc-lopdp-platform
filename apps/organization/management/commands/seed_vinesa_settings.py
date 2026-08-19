from django.core.management.base import BaseCommand

from apps.organization.defaults import VINESA_SYSTEM_SETTINGS
from apps.organization.models import SystemSetting


class Command(BaseCommand):
    help = (
        "Crea la configuración institucional confirmada de VINESA "
        "cuando todavía no existe el registro único."
    )

    def handle(self, *args, **options):
        setting, created = SystemSetting.objects.get_or_create(
            singleton_key=1,
            defaults=VINESA_SYSTEM_SETTINGS,
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    "Configuración institucional de VINESA creada."
                )
            )
            return
        self.stdout.write(
            self.style.WARNING(
                "La configuración institucional ya existe; no se "
                "sobrescribió ningún dato."
            )
        )

