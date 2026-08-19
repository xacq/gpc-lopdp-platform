from django.core.management.base import BaseCommand, CommandError

from apps.cases.models import RightsRequest
from apps.retention.services.retention import (
    RetentionRuleNotFoundError,
    RetentionService,
)


class Command(BaseCommand):
    help = "Detecta expedientes que cumplieron su plazo de retención."

    def handle(self, *args, **options):
        detected = 0
        reviewed = 0
        try:
            queryset = RightsRequest.objects.only("id").order_by("id")
            for case in queryset.iterator(chunk_size=500):
                reviewed += 1
                if RetentionService.detect_rights_request(request=case) is not None:
                    detected += 1
        except RetentionRuleNotFoundError as exc:
            raise CommandError(
                "No existe una regla activa para RIGHTS_REQUEST."
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Retención revisada: expedientes={reviewed}, eventos={detected}."
            )
        )
