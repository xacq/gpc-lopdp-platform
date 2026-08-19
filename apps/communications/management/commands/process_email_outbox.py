import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.communications.services.notifications import NotificationService


class Command(BaseCommand):
    help = "Procesa correos pendientes del outbox sin mostrar contenido ni PII."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Cantidad por lote (1-1000).",
        )
        parser.add_argument(
            "--drain",
            action="store_true",
            help="Procesa lotes hasta que no queden mensajes actualmente vencidos.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 1000:
            raise CommandError("--batch-size debe estar entre 1 y 1000.")

        totals = {
            "selected": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }
        correlation_id = uuid.uuid4()

        while True:
            result = NotificationService.process_due_email_batch(
                batch_size=batch_size,
                correlation_id=correlation_id,
            )
            for field_name in totals:
                totals[field_name] += getattr(result, field_name)

            if not options["drain"] or result.selected < batch_size:
                break

        self.stdout.write(
            self.style.SUCCESS(
                "Outbox procesado: "
                f"seleccionados={totals['selected']} "
                f"enviados={totals['sent']} "
                f"fallidos={totals['failed']} "
                f"omitidos={totals['skipped']}"
            )
        )
