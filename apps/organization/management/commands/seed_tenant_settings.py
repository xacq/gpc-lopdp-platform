from django.core.management.base import BaseCommand, CommandError

from apps.organization.models import SystemSetting


class Command(BaseCommand):
    help = "Crea la configuración institucional inicial de una empresa."

    def add_arguments(self, parser):
        parser.add_argument("--legal-name", required=True)
        parser.add_argument("--trade-name", required=True)
        parser.add_argument("--ruc", required=True)
        parser.add_argument("--domain", required=True)
        parser.add_argument("--contact-email", required=True)
        parser.add_argument("--request-prefix", required=True)
        parser.add_argument("--primary-color", default="#C8393C")
        parser.add_argument("--secondary-color", default="#552A2A")
        parser.add_argument("--accent-color", default="#A02E30")
        parser.add_argument("--background-color", default="#FAF7F7")
        parser.add_argument("--active-color", default="#782224")
        parser.add_argument("--separator-color", default="#E8E3E3")
        parser.add_argument("--border-color", default="#978B8B")
        parser.add_argument("--secondary-text-color", default="#756C6C")
        parser.add_argument("--success-color", default="#5A6B43")
        parser.add_argument("--info-color", default="#24566B")
        parser.add_argument("--warning-color", default="#8A5B00")
        parser.add_argument("--error-color", default="#B42318")

    def handle(self, *args, **options):
        if SystemSetting.objects.exists():
            raise CommandError(
                "La configuración institucional ya existe; no fue sobrescrita."
            )

        setting = SystemSetting(
            legal_name=options["legal_name"],
            trade_name=options["trade_name"],
            ruc=options["ruc"],
            domain=options["domain"],
            contact_email=options["contact_email"],
            controller_email=options["contact_email"],
            request_prefix=options["request_prefix"].upper(),
            timezone="America/Guayaquil",
            primary_color=options["primary_color"],
            secondary_color=options["secondary_color"],
            accent_color=options["accent_color"],
            background_color=options["background_color"],
            active_color=options["active_color"],
            separator_color=options["separator_color"],
            border_color=options["border_color"],
            secondary_text_color=options["secondary_text_color"],
            success_color=options["success_color"],
            info_color=options["info_color"],
            warning_color=options["warning_color"],
            error_color=options["error_color"],
        )
        setting.full_clean()
        setting.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"Configuración institucional creada para {setting.trade_name}."
            )
        )
