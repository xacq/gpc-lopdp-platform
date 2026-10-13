import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.cases.models import RightsRequest
from apps.evidence.models import NoticeDelivery
from apps.legal_content.models import LegalDocument
from apps.legal_content.services.documents import (
    LegalDocumentService,
    NoticeDeliveryService,
)


class Command(BaseCommand):
    help = (
        "Registra evidencia de aceptacion de politica de privacidad para "
        "solicitudes web existentes que fueron creadas con el checkbox "
        "obligatorio, pero no tienen NoticeDelivery asociado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica los cambios. Sin este flag solo muestra el conteo.",
        )

    def handle(self, *args, **options):
        policy = LegalDocumentService.current_or_latest_published(
            document_type=LegalDocument.DocumentType.PRIVACY_POLICY,
        )
        if policy is None:
            raise CommandError(
                "No existe una politica de privacidad publicada."
            )

        queryset = (
            RightsRequest.objects.filter(
                source_channel=RightsRequest.SourceChannel.WEB,
            )
            .exclude(
                notice_deliveries__acknowledged=True,
            )
            .order_by("received_at", "reference_number")
        )
        total = queryset.count()
        if not options["apply"]:
            self.stdout.write(
                "Modo verificacion: "
                f"{total} solicitud(es) web sin evidencia de aceptacion. "
                "Ejecuta nuevamente con --apply para registrar la evidencia."
            )
            self.stdout.write(
                f"Politica a usar: {policy.title} v{policy.version}"
            )
            return

        created = 0
        for case in queryset.iterator():
            NoticeDeliveryService.record(
                request=case,
                legal_document=policy,
                rendered_content=policy.content_html,
                delivery_channel=NoticeDelivery.DeliveryChannel.WEB,
                acknowledged=True,
                acknowledged_at=case.received_at,
                delivered_at=case.received_at,
                correlation_id=uuid.uuid4(),
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Evidencia de aceptacion registrada: {created}."
            )
        )
