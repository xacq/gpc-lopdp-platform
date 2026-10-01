import signal
import time
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.communications.services.notifications import NotificationService


class Command(BaseCommand):
    help = (
        "Ejecuta un worker persistente para procesar la cola de correos "
        "sin mostrar contenido ni PII."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Cantidad por lote (1-1000).",
        )
        parser.add_argument(
            "--interval-seconds",
            type=float,
            default=60,
            help="Segundos de espera entre ciclos.",
        )
        parser.add_argument(
            "--max-loops",
            type=int,
            default=None,
            help="Uso operativo/test: detiene el worker tras N ciclos.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        interval_seconds = options["interval_seconds"]
        max_loops = options["max_loops"]

        if not 1 <= batch_size <= 1000:
            raise CommandError("--batch-size debe estar entre 1 y 1000.")
        if interval_seconds < 0:
            raise CommandError("--interval-seconds no puede ser negativo.")
        if max_loops is not None and max_loops < 1:
            raise CommandError("--max-loops debe ser mayor o igual a 1.")

        self._stop_requested = False
        self._install_signal_handlers()

        self.stdout.write(
            self.style.SUCCESS(
                "Worker de correo iniciado: "
                f"lote={batch_size} intervalo={interval_seconds:g}s"
            )
        )

        loops = 0
        while not self._stop_requested:
            loops += 1
            totals = self._drain_due_messages(batch_size=batch_size)
            self.stdout.write(
                "Outbox worker: "
                f"seleccionados={totals['selected']} "
                f"enviados={totals['sent']} "
                f"fallidos={totals['failed']} "
                f"omitidos={totals['skipped']}"
            )

            if max_loops is not None and loops >= max_loops:
                break
            if self._stop_requested:
                break
            time.sleep(interval_seconds)

        self.stdout.write(self.style.SUCCESS("Worker de correo detenido."))

    def _install_signal_handlers(self):
        def request_stop(signum, frame):
            self._stop_requested = True

        for signal_name in ("SIGTERM", "SIGINT"):
            if hasattr(signal, signal_name):
                signal.signal(getattr(signal, signal_name), request_stop)

    def _drain_due_messages(self, *, batch_size: int) -> dict[str, int]:
        totals = {
            "selected": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }
        correlation_id = uuid.uuid4()

        while not self._stop_requested:
            result = NotificationService.process_due_email_batch(
                batch_size=batch_size,
                correlation_id=correlation_id,
            )
            for field_name in totals:
                totals[field_name] += getattr(result, field_name)

            if result.selected < batch_size:
                break

        return totals
