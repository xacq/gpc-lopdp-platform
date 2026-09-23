from django.test import TestCase, override_settings
from django.urls import reverse

from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting


class PublicHomeTests(TestCase):
    @override_settings(DEBUG=False)
    def test_unknown_route_uses_branded_404_page(self):
        response = self.client.get("/ruta-que-no-existe/")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(
            response,
            "No encontramos la página que buscas",
            status_code=404,
        )
        self.assertNotContains(
            response,
            "Using the URLconf",
            status_code=404,
        )

    def test_root_renders_public_home(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, "Tus datos")
        self.assertContains(response, 'class="brand-hero-image"')
        self.assertNotContains(response, 'class="privacy-shield"')

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

    def test_home_uses_lopdp_rights_when_catalog_is_empty(self):
        response = self.client.get(reverse("core:home"))

        for right in (
            "Acceso",
            "Rectificación y actualización",
            "Eliminación",
            "Oposición",
            "Portabilidad",
            "Suspensión del tratamiento",
        ):
            self.assertContains(response, right)

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

    def test_cookie_banner_is_present_on_public_pages(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="cookieBanner"')
        self.assertContains(response, "Uso de cookies y protección de datos")
        self.assertContains(response, "LOPDP del Ecuador")
        self.assertContains(response, reverse("legal_content:public_document", args=["cookies"]))
        self.assertContains(response, "/static/js/cookie-consent.js")
        self.assertContains(response, "Gestión de cookies")


class PublicInformationPageTests(TestCase):
    def test_rights_page_uses_lopdp_catalog_when_database_is_empty(self):
        response = self.client.get(reverse("core:rights"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/rights.html")
        self.assertContains(response, "Derechos reconocidos por la LOPDP")
        for right in (
            "Acceso",
            "Rectificación y actualización",
            "Eliminación",
            "Oposición",
            "Portabilidad",
            "Suspensión del tratamiento",
        ):
            self.assertContains(response, right)

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
        self.assertNotContains(response, "Derechos reconocidos por la LOPDP")

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
