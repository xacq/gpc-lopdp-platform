from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

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

        asset_dir = Path(settings.BASE_DIR) / "static" / "branding" / options["tenant"]
        for field_name, filename in (("logo_image", "logo.png"), ("favicon_image", "favicon.png")):
            asset_path = asset_dir / filename
            if not asset_path.exists():
                raise CommandError(f"No se encontró el recurso de marca: {asset_path}")
            image_field = getattr(setting, field_name)
            if image_field:
                image_field.delete(save=False)
            with asset_path.open("rb") as asset:
                image_field.save(f"{options['tenant']}-{filename}", File(asset), save=False)
        setting.updated_at = timezone.now()
        setting.full_clean()
        setting.save(update_fields=[*palette.keys(), "logo_image", "favicon_image", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Marca de {setting.trade_name} aplicada."))
