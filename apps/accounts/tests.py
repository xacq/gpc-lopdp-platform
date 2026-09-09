from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.accounts.tests_helpers import force_mfa_login


@override_settings(
    ACCOUNT_LOGIN_MAX_FAILURES=5,
    ACCOUNT_LOGIN_LOCK_SECONDS=900,
    AUTH_PENDING_MFA_TTL_SECONDS=300,
    AUTH_SESSION_ABSOLUTE_SECONDS=8 * 60 * 60,
    AUTH_SESSION_IDLE_SECONDS=30 * 60,
)
class AuthenticationHttpTests(TestCase):
    PASSWORD = "TestPassword123!"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="admin@example.com",
            password=self.PASSWORD,
            full_name="Administrador Prueba",
            is_active=True,
        )

    def _post_login(
        self,
        *,
        email="admin@example.com",
        password=None,
        next_url="",
    ):
        return self.client.post(
            reverse("accounts:login"),
            {
                "email": email,
                "password": (
                    password
                    if password is not None
                    else self.PASSWORD
                ),
                "next": next_url,
            },
        )

    def test_login_page_is_available(self):
        response = self.client.get(
            reverse("accounts:login")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Correo electrónico",
        )
        self.assertContains(response, 'class="brand-hero-image"')
        self.assertNotContains(response, 'class="privacy-shield"')

    def test_correct_password_creates_pending_mfa_not_full_login(self):
        response = self._post_login()

        self.assertRedirects(
            response,
            reverse("accounts:mfa_pending"),
            fetch_redirect_response=False,
        )

        session = self.client.session
        self.assertEqual(
            session.get("_gpc_pending_auth_user_id"),
            str(self.user.pk),
        )
        self.assertNotIn(
            SESSION_KEY,
            session,
        )

    def test_wrong_password_returns_generic_error(self):
        response = self._post_login(
            password="WrongPassword!"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No fue posible iniciar sesión con las credenciales proporcionadas.",
        )
        self.assertNotIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )

    def test_unknown_account_returns_same_generic_error(self):
        response = self._post_login(
            email="unknown@example.com",
            password="WrongPassword!",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No fue posible iniciar sesión con las credenciales proporcionadas.",
        )
        self.assertNotIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )

    def test_fifth_failure_locks_account(self):
        for _ in range(5):
            response = self._post_login(
                password="WrongPassword!"
            )
            self.assertEqual(
                response.status_code,
                200,
            )

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.failed_login_attempts,
            5,
        )
        self.assertIsNotNone(
            self.user.locked_until
        )
        self.assertGreater(
            self.user.locked_until,
            timezone.now(),
        )

    def test_locked_account_rejects_correct_password(self):
        self.user.failed_login_attempts = 5
        self.user.locked_until = (
            timezone.now()
            + timedelta(minutes=10)
        )
        self.user.save(
            update_fields=[
                "failed_login_attempts",
                "locked_until",
                "updated_at",
            ]
        )

        response = self._post_login()
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No fue posible iniciar sesión con las credenciales proporcionadas.",
        )

    def test_success_resets_previous_failures(self):
        self.user.failed_login_attempts = 2
        self.user.save(
            update_fields=[
                "failed_login_attempts",
                "updated_at",
            ]
        )

        response = self._post_login()
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.failed_login_attempts,
            0,
        )
        self.assertIsNone(
            self.user.locked_until
        )

    def test_inactive_account_is_rejected(self):
        self.user.is_active = False
        self.user.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        response = self._post_login()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )

    def test_safe_next_is_preserved_for_mfa_phase(self):
        response = self._post_login(
            next_url="/cases/"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get(
                "_gpc_pending_auth_next"
            ),
            "/cases/",
        )

    def test_external_next_is_not_preserved(self):
        response = self._post_login(
            next_url="https://evil.example/steal"
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(
            "_gpc_pending_auth_next",
            self.client.session,
        )

    def test_mfa_pending_requires_primary_factor_state(self):
        response = self.client.get(
            reverse("accounts:mfa_pending")
        )
        self.assertRedirects(
            response,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )

    def test_pending_mfa_state_expires(self):
        self._post_login()
        session = self.client.session
        session["_gpc_pending_auth_started_at"] = (
            int(timezone.now().timestamp())
            - 301
        )
        session.save()

        response = self.client.get(
            reverse("accounts:mfa_pending")
        )
        self.assertRedirects(
            response,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )

    def test_logout_requires_post(self):
        response = self.client.get(
            reverse("accounts:logout")
        )
        self.assertEqual(response.status_code, 405)

    def test_logout_clears_pending_authentication(self):
        self._post_login()
        self.assertIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )

        response = self.client.post(
            reverse("accounts:logout")
        )
        self.assertRedirects(
            response,
            "/accounts/login/",
            fetch_redirect_response=False,
        )
        self.assertNotIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )

    def test_idle_authenticated_session_is_terminated(self):
        force_mfa_login(self.client, self.user)
        now_epoch = int(
            timezone.now().timestamp()
        )
        session = self.client.session
        session["_gpc_auth_started_at"] = (
            now_epoch - 100
        )
        session["_gpc_auth_last_activity_at"] = (
            now_epoch - 1801
        )
        session.save()

        response = self.client.get(
            reverse("accounts:login")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            SESSION_KEY,
            self.client.session,
        )

    def test_absolute_authenticated_session_is_terminated(self):
        force_mfa_login(self.client, self.user)
        now_epoch = int(
            timezone.now().timestamp()
        )
        session = self.client.session
        session["_gpc_auth_started_at"] = (
            now_epoch - (8 * 60 * 60) - 1
        )
        session["_gpc_auth_last_activity_at"] = (
            now_epoch
        )
        session.save()

        response = self.client.get(
            reverse("accounts:login")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            SESSION_KEY,
            self.client.session,
        )

    def test_active_authenticated_session_is_kept(self):
        force_mfa_login(self.client, self.user)
        now_epoch = int(
            timezone.now().timestamp()
        )
        session = self.client.session
        session["_gpc_auth_started_at"] = (
            now_epoch - 60
        )
        session["_gpc_auth_last_activity_at"] = (
            now_epoch - 10
        )
        session.save()

        response = self.client.get(
            reverse("accounts:login")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            SESSION_KEY,
            self.client.session,
        )

    def test_failed_login_is_audited_without_email_metadata(self):
        self._post_login(
            password="WrongPassword!"
        )

        entry = AuditLog.objects.get(
            action="AUTH_PRIMARY_FACTOR_REJECTED"
        )
        self.assertEqual(
            entry.metadata["reason_code"],
            "INVALID_CREDENTIALS",
        )
        self.assertNotIn(
            "admin@example.com",
            str(entry.metadata),
        )

    def test_successful_primary_factor_is_audited(self):
        self._post_login()

        entry = AuditLog.objects.get(
            action="AUTH_PRIMARY_FACTOR_ACCEPTED"
        )
        self.assertEqual(
            entry.actor_user_id,
            self.user.pk,
        )
        self.assertEqual(
            entry.metadata[
                "authentication_stage"
            ],
            "PASSWORD",
        )
