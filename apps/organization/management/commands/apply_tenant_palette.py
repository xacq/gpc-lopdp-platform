from django.core.management.base import BaseCommand, CommandError

from apps.organization.defaults import TENANT_PALETTES
from apps.organization.models import SystemSetting


class Command(BaseCommand):
    help = "Aplica la paleta visual validada a la configuración institucional existente."

    def add_arguments(self, parser):
        parser.add_argument("tenant", choices=TENANT_PALETTES.keys())

    def handle(self, *args, **options):
        setting = SystemSetting.objects.filter(singleton_key=1).first()
        if setting is None:
            raise CommandError("No existe configuración institucional para actualizar.")

        palette = TENANT_PALETTES[options["tenant"]]
        for field, value in palette.items():
            setattr(setting, field, value)
        setting.full_clean()
        setting.save(update_fields=[*palette.keys(), "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Paleta de {setting.trade_name} aplicada."))
