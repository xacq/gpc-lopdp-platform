from django.test import SimpleTestCase
from django.urls import reverse


class PublicHomeTests(SimpleTestCase):
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

    def test_uses_official_logo_and_favicon_assets(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "/static/images/vinesa-logo.png")
        self.assertContains(response, "/static/images/vinesa-favicon.png")
        self.assertNotContains(response, 'class="vinesa-brand__mark"')
