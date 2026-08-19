from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.organization.models import SystemSetting


class SeedVinesaSettingsCommandTests(TestCase):
    def test_command_creates_confirmed_institutional_settings(self):
        output = StringIO()

        call_command("seed_vinesa_settings", stdout=output)

        setting = SystemSetting.objects.get(singleton_key=1)
        self.assertEqual(
            setting.legal_name,
            "VINOS Y ESPIRITUOSOS VINESA S.A.",
        )
        self.assertEqual(setting.ruc, "1792049598001")
        self.assertEqual(
            setting.contact_email,
            "privacidad@vinesa.com.ec",
        )
        self.assertEqual(setting.primary_color, "#C8393C")
        self.assertIn("creada", output.getvalue())

        response = self.client.get(reverse("core:contact"))
        self.assertContains(response, "VINOS Y ESPIRITUOSOS VINESA S.A.")
        self.assertContains(response, "1792049598001")
        self.assertContains(response, "privacidad@vinesa.com.ec")
        self.assertContains(response, "formato pendiente de normalización")
        self.assertContains(response, "María Elena Terán")

    def test_command_does_not_overwrite_existing_settings(self):
        SystemSetting.objects.create(
            legal_name="Configuración aprobada",
            trade_name="Aprobada",
            ruc="0000000000001",
            domain="approved.example.test",
            contact_email="approved@example.test",
            request_prefix="OK",
            timezone="America/Guayaquil",
        )

        call_command("seed_vinesa_settings", stdout=StringIO())

        setting = SystemSetting.objects.get(singleton_key=1)
        self.assertEqual(setting.legal_name, "Configuración aprobada")
        self.assertEqual(setting.contact_email, "approved@example.test")
