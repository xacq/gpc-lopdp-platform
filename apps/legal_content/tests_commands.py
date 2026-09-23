from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.legal_content.models import RightCatalog, RightRule


class SeedLopdpRightsCommandTests(TestCase):
    def test_creates_and_updates_the_six_active_rights_with_rules(self):
        output = StringIO()

        call_command("seed_lopdp_rights", stdout=output)
        call_command("seed_lopdp_rights", stdout=output)

        self.assertEqual(RightCatalog.objects.filter(is_active=True).count(), 6)
        self.assertEqual(RightRule.objects.filter(is_active=True).count(), 6)
        self.assertEqual(
            list(RightCatalog.objects.order_by("code").values_list("code", flat=True)),
            [
                "ACCESS",
                "ELIMINATION",
                "OPPOSITION",
                "PORTABILITY",
                "RECTIFICATION_UPDATE",
                "SUSPENSION",
            ],
        )
        self.assertIn("Catálogo LOPDP configurado: 6 derechos.", output.getvalue())
