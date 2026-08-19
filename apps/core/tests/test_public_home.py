from django.test import TestCase
from django.urls import reverse

from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting


class PublicHomeTests(TestCase):
    def test_root_renders_public_home(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, "Tus datos")

    def test_primary_actions_use_existing_public_routes(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(
            response,
            reverse("cases:public_request_create"),
        )
        self.assertContains(
            response,
            reverse("cases:public_tracking"),
        )

    def test_home_uses_confirmed_rights_without_hardcoded_portability(self):
        response = self.client.get(reverse("core:home"))

        for right in ("Acceso", "Rectificación", "Eliminación", "Oposición"):
            self.assertContains(response, right)
        self.assertNotContains(response, "Portabilidad")

    def test_home_prefers_active_rights_catalog(self):
        RightCatalog.objects.create(
            code="APPROVED",
            name="Derecho aprobado para inicio",
            description="Descripción configurada para inicio.",
            is_active=True,
        )
        RightCatalog.objects.create(
            code="INACTIVE",
            name="Derecho inactivo",
            is_active=False,
        )

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "Derecho aprobado para inicio")
        self.assertContains(response, "Descripción configurada para inicio")
        self.assertNotContains(response, "Derecho inactivo")
        self.assertNotContains(response, "Eliminación")

    def test_uses_official_logo_and_favicon_assets(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "/static/images/vinesa-logo.png")
        self.assertContains(response, "/static/images/vinesa-favicon.png")
        self.assertNotContains(response, 'class="vinesa-brand__mark"')

    def test_navigation_uses_real_information_pages(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("core:rights"))
        self.assertContains(response, reverse("legal_content:public_index"))
        self.assertContains(response, reverse("core:contact"))


class PublicInformationPageTests(TestCase):
    def test_rights_page_uses_preliminary_catalog_when_database_is_empty(self):
        response = self.client.get(reverse("core:rights"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/rights.html")
        self.assertContains(response, "Derechos actualmente comunicados")
        self.assertContains(response, "Eliminación")
        self.assertContains(
            response,
            "No constituyen todavía el catálogo jurídico completo",
        )

    def test_rights_page_uses_active_catalog_data(self):
        RightCatalog.objects.create(
            code="ACCESS",
            name="Derecho de prueba aprobado",
            description="Descripción pública configurada.",
            legal_reference="Referencia aprobada",
            is_active=True,
        )
        RightCatalog.objects.create(
            code="INACTIVE",
            name="No publicar",
            is_active=False,
        )

        response = self.client.get(reverse("core:rights"))

        self.assertContains(response, "Derecho de prueba aprobado")
        self.assertContains(response, "Descripción pública configurada.")
        self.assertNotContains(response, "No publicar")
        self.assertNotContains(response, "Derechos actualmente comunicados")

    def test_contact_page_marks_missing_settings_as_pending(self):
        response = self.client.get(reverse("core:contact"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/contact.html")
        self.assertContains(response, "Datos institucionales pendientes")
        self.assertContains(response, "María Elena Terán")
        self.assertContains(response, "VINOS Y ESPIRITUOSOS VINESA S.A.")
        self.assertContains(response, "1792049598001")
        self.assertContains(response, "privacidad@vinesa.com.ec")
        self.assertContains(response, "formato pendiente de normalización")
        self.assertContains(response, "no se atribuye personalmente al DPD")

    def test_contact_page_uses_configured_institutional_channels(self):
        SystemSetting.objects.create(
            legal_name="VINESA PRUEBA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.example.test",
            contact_email="privacidad@example.test",
            phone="+593 2 000 0000",
            controller_name="Responsable de prueba",
            controller_email="responsable@example.test",
            dpd_name="DPD de prueba",
            dpd_email="dpd@example.test",
            complaint_channel_url="https://example.test/reclamos",
            request_prefix="VINESA",
            timezone="America/Guayaquil",
        )

        response = self.client.get(reverse("core:contact"))

        self.assertContains(response, "privacidad@example.test")
        self.assertContains(response, "Responsable de prueba")
        self.assertContains(response, "DPD de prueba")
        self.assertContains(response, "https://example.test/reclamos")
        self.assertNotContains(response, "María Elena Terán")
