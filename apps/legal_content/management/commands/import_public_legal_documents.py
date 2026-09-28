from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.template import Context, Engine
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.legal_content.models import LegalDocument
from apps.legal_content.services.documents import (
    LegalDocumentError,
    LegalDocumentService,
)
from apps.organization.models import SystemSetting


DOCUMENTS = (
    {
        "type": LegalDocument.DocumentType.PRIVACY_POLICY,
        "title": "Politica de Proteccion de Datos Personales",
        "slug": "privacidad",
        "template": "privacy_policy.html",
    },
    {
        "type": LegalDocument.DocumentType.CUSTOMER_VENDOR_NOTICE,
        "title": "Aviso Clientes",
        "slug": "clientes-vendedores",
        "template": "customer_vendor_notice.html",
    },
    {
        "type": LegalDocument.DocumentType.EMPLOYEE_NOTICE,
        "title": "Aviso Empleados",
        "slug": "empleados",
        "template": "employee_notice.html",
    },
    {
        "type": LegalDocument.DocumentType.CANDIDATE_NOTICE,
        "title": "Aviso Candidatos",
        "slug": "candidatos",
        "template": "candidate_notice.html",
    },
    {
        "type": LegalDocument.DocumentType.SUPPLIER_NOTICE,
        "title": "Aviso Proveedores",
        "slug": "proveedores",
        "template": "supplier_notice.html",
    },
    {
        "type": LegalDocument.DocumentType.VIDEO_SURVEILLANCE_NOTICE,
        "title": "Aviso Videovigilancia",
        "slug": "videovigilancia",
        "template": "video_surveillance_notice.html",
    },
)


class Command(BaseCommand):
    help = "Importa y publica las plantillas legales publicas del repositorio."

    def add_arguments(self, parser):
        parser.add_argument(
            "--legal-version",
            dest="legal_version",
            default="1.0",
            help="Version legal a crear para todos los documentos.",
        )
        parser.add_argument(
            "--effective-from",
            help=(
                "Fecha/hora de vigencia. Acepta ISO datetime o YYYY-MM-DD. "
                "Por defecto usa la fecha y hora actual."
            ),
        )
        parser.add_argument(
            "--actor-email",
            help=(
                "Correo del usuario que quedara registrado como creador. "
                "Si se omite, se usa el primer superusuario activo."
            ),
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publica cada borrador despues de crearlo.",
        )
        parser.add_argument(
            "--templates-dir",
            default=str(Path(settings.BASE_DIR) / "legal_documents"),
            help="Directorio con las plantillas HTML legales.",
        )

    def handle(self, *args, **options):
        setting = SystemSetting.objects.filter(singleton_key=1).first()
        if setting is None:
            raise CommandError(
                "No existe configuracion institucional para renderizar documentos."
            )
        actor = self._actor(options["actor_email"])
        effective_from = self._effective_from(options["effective_from"])
        templates_dir = Path(options["templates_dir"])
        if not templates_dir.exists():
            raise CommandError(f"No existe el directorio {templates_dir}.")

        context = self._context(setting)
        engine = Engine.get_default()
        created = 0
        skipped = 0
        published = 0

        for item in DOCUMENTS:
            existing = LegalDocument.objects.filter(
                document_type=item["type"],
                version=options["legal_version"],
            ).first()
            if existing is not None:
                skipped += 1
                self.stdout.write(
                    f"Ya existe {existing.title} version {existing.version}; omitido."
                )
                if options["publish"] and not existing.is_published:
                    LegalDocumentService.publish(document=existing, actor=actor)
                    published += 1
                continue

            template_path = templates_dir / item["template"]
            if not template_path.exists():
                raise CommandError(f"No existe la plantilla {template_path}.")
            content_html = engine.from_string(
                template_path.read_text(encoding="utf-8")
            ).render(Context(context, autoescape=True))
            document = LegalDocumentService.create_draft(
                document_type=item["type"],
                title=item["title"],
                slug=item["slug"],
                version=options["legal_version"],
                content_html=content_html,
                effective_from=effective_from,
                actor=actor,
            )
            created += 1
            if options["publish"]:
                LegalDocumentService.publish(document=document, actor=actor)
                published += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Documentos legales procesados: "
                f"{created} creados, {published} publicados, {skipped} omitidos."
            )
        )

    def _actor(self, actor_email):
        users = get_user_model().objects.filter(is_active=True)
        if actor_email:
            actor = users.filter(email__iexact=actor_email).first()
            if actor is None:
                raise CommandError(
                    f"No existe un usuario activo con correo {actor_email}."
                )
            return actor
        actor = users.filter(is_superuser=True).order_by("email").first()
        if actor is None:
            raise CommandError(
                "No existe un superusuario activo para registrar la importacion."
            )
        return actor

    def _effective_from(self, value):
        if not value:
            return timezone.now()
        parsed = parse_datetime(value)
        if parsed is None:
            date_value = parse_date(value)
            if date_value is not None:
                parsed = timezone.datetime.combine(
                    date_value,
                    timezone.datetime.min.time(),
                )
        if parsed is None:
            raise CommandError("--effective-from no tiene un formato valido.")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _context(self, setting):
        contact_email = setting.contact_email
        return {
            "legal_name": setting.legal_name,
            "trade_name": setting.trade_name or setting.legal_name,
            "ruc": setting.ruc,
            "domain": setting.domain,
            "address": setting.address or "el domicilio registrado por la organizacion",
            "phone": setting.phone or "",
            "contact_email": contact_email,
            "controller_email": setting.controller_email or contact_email,
            "dpd_email": setting.dpd_email or contact_email,
            "complaint_authority_name": setting.complaint_authority_name,
            "complaint_channel_url": setting.complaint_channel_url or "",
            "privacy_policy_url": "/legal/privacidad/",
        }
