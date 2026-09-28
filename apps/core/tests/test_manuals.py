from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login


class ManualsPageTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(
            code=Role.Code.DPD,
            name="Delegado de Protección de Datos",
            description="Rol para consultar manuales.",
            is_active=True,
        )
        self.user = get_user_model().objects.create_user(
            email="manuals-dpd@example.test",
            password="StrongManualPassword!593",
            full_name="Usuario Manuales",
            is_active=True,
        )
        UserRole.objects.create(
            user=self.user,
            role=self.role,
            is_primary=True,
        )
        self.outsider = get_user_model().objects.create_user(
            email="manuals-outsider@example.test",
            password="StrongManualPassword!593",
            full_name="Usuario sin rol",
            is_active=True,
        )

    def test_manuals_page_renders_default_manual(self):
        force_mfa_login(self.client, self.user)
        response = self.client.get(reverse("core:manuals"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manuales")
        self.assertContains(response, "Manual operativo")
        self.assertContains(response, "Guías disponibles")
        self.assertContains(response, "href=\"/manuales/?manual=usuarios\"")

    def test_manuals_page_switches_selected_manual(self):
        force_mfa_login(self.client, self.user)
        response = self.client.get(
            reverse("core:manuals"),
            {"manual": "comunicaciones"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manual para comunicaciones")
        self.assertContains(response, "Registro y seguimiento de comunicaciones")

    def test_manuals_page_requires_internal_role(self):
        force_mfa_login(self.client, self.outsider)
        response = self.client.get(reverse("core:manuals"))

        self.assertEqual(response.status_code, 403)
