import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.legal_content.models import LegalDocument


class LegalDocumentAdminHttpTests(TestCase):
    def setUp(self):
        self.dpd = self._user("dpd-legal@example.test", Role.Code.DPD)
        self.admin = self._user("admin-legal@example.test", Role.Code.ADMIN)
        self.responsible = self._user(
            "responsible-legal@example.test", Role.Code.RESPONSABLE
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongLegalPassword!593",
            full_name=f"Usuario {role_code}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def _create(self, version="1.0", effective_from=None, content=None):
        return self.client.post(
            reverse("legal_content:manage_create"),
            data=json.dumps(
                {
                    "document_type": "PRIVACY_POLICY",
                    "title": "Política de Privacidad",
                    "slug": "privacidad",
                    "version": version,
                    "content_html": content
                    or "<h2>Privacidad</h2><p>Contenido aprobado.</p>",
                    "effective_from": (
                        effective_from or timezone.now()
                    ).isoformat(),
                }
            ),
            content_type="application/json",
        )

    def test_dpd_creates_sanitized_draft_and_lists_it(self):
        force_mfa_login(self.client, self.dpd)
        created = self._create(
            content=(
                '<script>alert("x")</script><h2>Privacidad</h2>'
                '<p><a href="javascript:alert(1)">Texto</a></p>'
            )
        )
        listing = self.client.get(
            reverse("legal_content:manage_list"),
            {"document_type": "PRIVACY_POLICY", "published": "false"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("<script", created.json()["content_html"])
        self.assertNotIn("javascript:", created.json()["content_html"])
        self.assertEqual(listing.json()["results"][0]["version"], "1.0")
        self.assertTrue(
            AuditLog.objects.filter(action="LEGAL_DOCUMENT_DRAFT_CREATED").exists()
        )

    def test_publish_makes_document_available_on_public_page(self):
        force_mfa_login(self.client, self.admin)
        created = self._create()
        published = self.client.post(
            reverse(
                "legal_content:manage_publish", args=[created.json()["id"]]
            )
        )
        public = self.client.get(
            reverse("legal_content:public_document", args=["privacidad"])
        )
        self.assertEqual(published.status_code, 200)
        self.assertTrue(published.json()["is_published"])
        self.assertContains(public, "Contenido aprobado")

    def test_management_panel_creates_and_publishes_with_redirects(self):
        force_mfa_login(self.client, self.dpd)
        effective_from = timezone.now().replace(microsecond=0)

        created = self.client.post(
            reverse("legal_content:manage_panel"),
            {
                "document_type": "RIGHTS_NOTICE",
                "title": "Aviso de derechos",
                "slug": "derechos-panel",
                "version": "1.0-panel",
                "content_html": "<h2>Derechos</h2><p>Contenido temporal.</p>",
                "effective_from": effective_from.isoformat(),
            },
        )

        self.assertEqual(created.status_code, 302)
        document = LegalDocument.objects.get(version="1.0-panel")
        panel = self.client.get(reverse("legal_content:manage_panel"))
        self.assertContains(panel, "Aviso de derechos")
        published = self.client.post(
            reverse("legal_content:manage_publish", args=[document.id]),
            {"return_to": "panel"},
        )
        self.assertEqual(published.status_code, 302)
        document.refresh_from_db()
        self.assertTrue(document.is_published)
        self.assertIn("no-cache", panel["Cache-Control"])

    def test_new_publication_supersedes_open_version(self):
        force_mfa_login(self.client, self.admin)
        first = self._create(
            version="1.0", effective_from=timezone.now() - timedelta(days=1)
        )
        self.client.post(
            reverse("legal_content:manage_publish", args=[first.json()["id"]])
        )
        second_time = timezone.now() + timedelta(days=1)
        second = self._create(version="2.0", effective_from=second_time)
        response = self.client.post(
            reverse("legal_content:manage_publish", args=[second.json()["id"]])
        )
        old = LegalDocument.objects.get(pk=first.json()["id"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(old.effective_to, second_time)

    def test_responsible_cannot_manage_legal_documents(self):
        force_mfa_login(self.client, self.responsible)
        self.assertEqual(
            self.client.get(reverse("legal_content:manage_list")).status_code,
            403,
        )
        self.assertEqual(self._create().status_code, 403)

    def test_invalid_payload_is_rejected(self):
        force_mfa_login(self.client, self.admin)
        response = self.client.post(
            reverse("legal_content:manage_create"),
            data=json.dumps({"document_type": "INVALID"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
