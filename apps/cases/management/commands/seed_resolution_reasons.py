from django.core.management.base import BaseCommand

from apps.cases.models import CaseOutcomeReason


REASONS = (
    (
        "REJECTION",
        "NOT_DATA_SUBJECT_OR_UNACCREDITED_REPRESENTATIVE",
        "El solicitante no es el titular o el representante no está acreditado.",
        "LOPDP, art. 18 numeral 1.",
    ),
    (
        "REJECTION",
        "LEGAL_OR_CONTRACTUAL_OBLIGATION",
        "Los datos son necesarios para cumplir una obligación legal o contractual.",
        "LOPDP, art. 18 numeral 2.",
    ),
    (
        "REJECTION",
        "JUDICIAL_OR_AUTHORITY_ORDER",
        "Los datos son necesarios para cumplir una orden judicial o mandato de autoridad competente.",
        "LOPDP, art. 18 numeral 3.",
    ),
    (
        "REJECTION",
        "CLAIMS_OR_RECOURSES_DEFENSE",
        "Los datos son necesarios para formular, ejercer o defender reclamos o recursos.",
        "LOPDP, art. 18 numeral 4.",
    ),
    (
        "REJECTION",
        "THIRD_PARTY_RIGHTS",
        "La solicitud causa un perjuicio acreditado a derechos o intereses legítimos de terceros.",
        "LOPDP, art. 18 numeral 5.",
    ),
    (
        "REJECTION",
        "ONGOING_JUDICIAL_OR_ADMINISTRATIVE_PROCEEDING",
        "La solicitud obstaculiza una actuación judicial o administrativa en curso debidamente notificada.",
        "LOPDP, art. 18 numeral 6.",
    ),
    (
        "REJECTION",
        "FREEDOM_OF_EXPRESSION_OR_OPINION",
        "Los datos son necesarios para ejercer la libertad de expresión y opinión.",
        "LOPDP, art. 18 numeral 7.",
    ),
    (
        "REJECTION",
        "VITAL_INTEREST",
        "Los datos son necesarios para proteger el interés vital del titular o de otra persona natural.",
        "LOPDP, art. 18 numeral 8.",
    ),
    (
        "REJECTION",
        "PUBLIC_INTEREST",
        "Existe interés público, conforme a legalidad, proporcionalidad y necesidad.",
        "LOPDP, art. 18 numeral 9.",
    ),
    (
        "REJECTION",
        "STATE_ARCHIVE_RESEARCH_OR_STATISTICS",
        "Los datos son necesarios para archivo patrimonial del Estado, investigación científica, histórica o estadística.",
        "LOPDP, art. 18 numeral 10.",
    ),
    (
        "ARCHIVE",
        "CLARIFICATION_EXPIRED",
        "Venció el plazo de la aclaración solicitada sin que se reciba respuesta.",
        "Regla procedimental del portal; requiere aclaración vencida.",
    ),
    (
        "CANCELLATION",
        "WITHDRAWN_BY_DATA_SUBJECT",
        "El titular desistió expresamente de la solicitud antes de iniciar la revisión.",
        "Regla procedimental del portal.",
    ),
    (
        "CANCELLATION",
        "DUPLICATE_REQUEST",
        "Solicitud duplicada antes de iniciar la revisión.",
        "Regla procedimental del portal.",
    ),
    (
        "CANCELLATION",
        "FILED_IN_ERROR",
        "Solicitud ingresada por error antes de iniciar la revisión.",
        "Regla procedimental del portal.",
    ),
)


class Command(BaseCommand):
    help = "Carga las causales de resolución LOPDP y procedimentales."

    def handle(self, *args, **options):
        for reason_type, code, name, legal_basis in REASONS:
            CaseOutcomeReason.objects.update_or_create(
                reason_type=reason_type,
                code=code,
                defaults={
                    "name": name,
                    "legal_basis": legal_basis,
                    "is_active": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo de causales configurado: {len(REASONS)} causales."
            )
        )
