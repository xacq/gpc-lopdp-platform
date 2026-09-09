from io import StringIO
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
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
        self.assertEqual(setting.background_color, "#FAF7F7")
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


class ApplyTenantPaletteCommandTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory(dir=settings.BASE_DIR)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        SystemSetting.objects.create(
            legal_name="Empresa de prueba S.A.",
            trade_name="Empresa 2",
            ruc="0000000000002",
            domain="empresa2.local",
            contact_email="privacidad@empresa2.local",
            request_prefix="E2",
            timezone="America/Guayaquil",
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_command_applies_identity_palette_logo_and_favicon(self):
        call_command("apply_tenant_palette", "plusbrand", stdout=StringIO())

        setting = SystemSetting.objects.get(singleton_key=1)
        self.assertEqual(setting.trade_name, "PLUSBRAND")
        self.assertEqual(setting.primary_color, "#A24340")
        self.assertTrue(setting.logo_image.name.startswith("branding/plusbrand-logo"))
        self.assertTrue(setting.favicon_image.name.startswith("branding/plusbrand-favicon"))

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "PLUSBRAND mantiene un programa")
        self.assertContains(response, setting.logo_image.url)
        self.assertContains(response, setting.favicon_image.url)
        self.assertNotContains(response, "VINESA S.A.")
