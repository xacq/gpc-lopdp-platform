from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.legal_content.models import LegalDocument, RightCatalog, RightRule
from apps.organization.models import SystemSetting


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


class ImportPublicLegalDocumentsCommandTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name="SERVMULTIMARC S.A.",
            trade_name="SERVMULTIMARC",
            ruc="0999999999001",
            domain="laguarda.com.ec",
            address="Quito",
            phone="0999999999",
            contact_email="privacidad-servmultimarc@laguarda.com.ec",
            request_prefix="SM",
            timezone="America/Guayaquil",
        )
        get_user_model().objects.create_superuser(
            email="admin@example.test",
            password="TestPassword123!",
            full_name="Admin",
        )

    def test_imports_and_publishes_repository_templates(self):
        output = StringIO()

        call_command(
            "import_public_legal_documents",
            legal_version="1.0",
            publish=True,
            stdout=output,
        )

        self.assertEqual(LegalDocument.objects.filter(is_published=True).count(), 6)
        privacy = LegalDocument.objects.get(
            document_type=LegalDocument.DocumentType.PRIVACY_POLICY
        )
        self.assertIn("SERVMULTIMARC S.A.", privacy.content_html)
        self.assertIn(
            "privacidad-servmultimarc@laguarda.com.ec",
            privacy.content_html,
        )
        self.assertNotIn("privacidad@cvl.com.ec", privacy.content_html)
        self.assertIn(
            "6 creados, 6 publicados, 0 omitidos",
            output.getvalue(),
        )

    def test_import_is_idempotent_for_same_version(self):
        call_command("import_public_legal_documents", legal_version="1.0", publish=True)
        output = StringIO()

        call_command(
            "import_public_legal_documents",
            legal_version="1.0",
            publish=True,
            stdout=output,
        )

        self.assertEqual(LegalDocument.objects.count(), 6)
        self.assertIn(
            "0 creados, 0 publicados, 6 omitidos",
            output.getvalue(),
        )
