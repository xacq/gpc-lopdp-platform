from django.core.management.base import BaseCommand, CommandError

from apps.evidence.services.temporary_uploads import TemporaryUploadService


class Command(BaseCommand):
    help = "Elimina archivos temporales expirados sin mostrar metadatos."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 1000:
            raise CommandError("--batch-size debe estar entre 1 y 1000.")
        result = TemporaryUploadService.cleanup_expired(
            batch_size=batch_size
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Temporales procesados: "
                f"seleccionados={result.selected} "
                f"eliminados={result.deleted} "
                f"fallidos={result.failed}"
            )
        )
