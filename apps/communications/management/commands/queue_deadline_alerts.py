from django.core.management.base import BaseCommand, CommandError

from apps.communications.services.deadline_alerts import DeadlineAlertService


class Command(BaseCommand):
    help = "Queue idempotent alerts for deadlines inside their warning window."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        try:
            result = DeadlineAlertService.queue_due_alerts(limit=options["limit"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Queued {result.queued} deadline alert(s).")
        )
