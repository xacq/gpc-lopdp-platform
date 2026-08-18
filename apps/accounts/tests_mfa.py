from __future__ import annotations

from datetime import datetime, timedelta, timezone as datetime_timezone

from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import MFADevice
from apps.accounts.services.mfa import MFARejected, MFAService
from apps.audit.models import AuditLog


@override_settings(
    MFA_TOTP_ISSUER="VINESA",
    MFA_RECOVERY_CODE_COUNT=10,
)
class MFAServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="mfa-service@example.com",
            password="TestPassword123!",
            full_name="Usuario MFA",
            is_active=True,
        )

    def _confirm(self, *, now=None):
        now = now or timezone.now()
        enrollment = MFAService.begin_totp_enrollment(
            user=self.user
        )
        code = MFAService.generate_totp_code(
            enrollment.secret,
            at=now,
        )
        confirmation = MFAService.confirm_totp(
            user=self.user,
            device_id=enrollment.device.pk,
            code=code,
            now=now,
        )
        return enrollment, confirmation

    def test_totp_matches_rfc_6238_sha1_vector(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        at = datetime.fromtimestamp(
            59,
            tz=datetime_timezone.utc,
        )
        self.assertEqual(
            MFAService.generate_totp_code(secret, at=at),
            "287082",
        )

    def test_enrollment_encrypts_secret_with_context(self):
        enrollment = MFAService.begin_totp_enrollment(
            user=self.user
        )
        stored = bytes(enrollment.device.secret_encrypted)
        self.assertNotIn(
            enrollment.secret.encode("ascii"),
            stored,
        )
        self.assertTrue(
            enrollment.provisioning_uri.startswith(
                "otpauth://totp/"
            )
        )
        self.assertIn("issuer=VINESA", enrollment.provisioning_uri)
        self.assertTrue(
            enrollment.qr_data_uri.startswith(
                "data:image/svg+xml;base64,"
            )
        )

    def test_unconfirmed_enrollment_is_reused(self):
        first = MFAService.begin_totp_enrollment(user=self.user)
        second = MFAService.begin_totp_enrollment(user=self.user)
        self.assertEqual(first.device.pk, second.device.pk)
        self.assertEqual(first.secret, second.secret)

    def test_confirmation_creates_recovery_codes_once(self):
        _, confirmation = self._confirm()
        self.assertEqual(len(confirmation.recovery_codes), 10)
        self.assertEqual(
            MFADevice.objects.filter(
                user=self.user,
                device_type=MFADevice.DeviceType.RECOVERY_CODES,
            ).count(),
            1,
        )
        recovery_device = MFADevice.objects.get(
            user=self.user,
            device_type=MFADevice.DeviceType.RECOVERY_CODES,
        )
        for code in confirmation.recovery_codes:
            self.assertNotIn(
                code.encode("ascii"),
                bytes(recovery_device.secret_encrypted),
            )

    def test_totp_cannot_be_replayed_in_same_period(self):
        now = timezone.now()
        enrollment, _ = self._confirm(now=now)
        code = MFAService.generate_totp_code(
            enrollment.secret,
            at=now,
        )
        with self.assertRaises(MFARejected):
            MFAService.verify_totp(
                user=self.user,
                code=code,
                now=now,
            )

    def test_totp_updates_last_used_at(self):
        now = timezone.now()
        enrollment, confirmation = self._confirm(now=now)
        later = now + timedelta(seconds=30)
        code = MFAService.generate_totp_code(
            enrollment.secret,
            at=later,
        )
        device = MFAService.verify_totp(
            user=self.user,
            code=code,
            now=later,
        )
        self.assertEqual(device.pk, confirmation.device.pk)
        self.assertEqual(device.last_used_at, later)

    def test_recovery_code_is_single_use(self):
        _, confirmation = self._confirm()
        recovery_code = confirmation.recovery_codes[0]
        device = MFAService.consume_recovery_code(
            user=self.user,
            code=recovery_code,
        )
        self.assertIsNotNone(device.last_used_at)
        with self.assertRaises(MFARejected):
            MFAService.consume_recovery_code(
                user=self.user,
                code=recovery_code,
            )

    def test_revoke_deactivates_device(self):
        _, confirmation = self._confirm()
        revoked = MFAService.revoke(
            device=confirmation.device,
            actor=self.user,
        )
        self.assertFalse(revoked.is_active)
        self.assertIsNotNone(revoked.revoked_at)

    def test_audit_metadata_never_contains_mfa_material(self):
        enrollment, confirmation = self._confirm()
        entries = AuditLog.objects.filter(
            action="AUTH_MFA_ACCEPTED"
        )
        serialized = str(list(entries.values_list("metadata", flat=True)))
        self.assertNotIn(enrollment.secret, serialized)
        for code in confirmation.recovery_codes:
            self.assertNotIn(code, serialized)


@override_settings(
    MFA_TOTP_ISSUER="VINESA",
    MFA_RECOVERY_CODE_COUNT=3,
)
class MFAHttpTests(TestCase):
    PASSWORD = "TestPassword123!"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="mfa-http@example.com",
            password=self.PASSWORD,
            full_name="Usuario MFA HTTP",
            is_active=True,
        )

    def _primary_login(self):
        return self.client.post(
            reverse("accounts:login"),
            {
                "email": self.user.email,
                "password": self.PASSWORD,
            },
        )

    def _enroll(self):
        self._primary_login()
        response = self.client.get(
            reverse("accounts:mfa_pending")
        )
        secret = response.context["secret"]
        code = MFAService.generate_totp_code(secret)
        return self.client.post(
            reverse("accounts:mfa_pending"),
            {"code": code},
        )

    def test_enrollment_page_does_not_authenticate_user(self):
        self._primary_login()
        response = self.client.get(
            reverse("accounts:mfa_pending")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "otpauth://totp/")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_valid_enrollment_completes_login_and_shows_codes_once(self):
        response = self._enroll()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No volverán a mostrarse")
        self.assertIn(SESSION_KEY, self.client.session)
        self.assertNotIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )

    def test_invalid_enrollment_code_is_generic_and_not_authenticated(self):
        self._primary_login()
        self.client.get(reverse("accounts:mfa_pending"))
        response = self.client.post(
            reverse("accounts:mfa_pending"),
            {"code": "000000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No fue posible verificar el segundo factor.",
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_five_mfa_failures_expire_pending_authentication(self):
        self._primary_login()
        response = self.client.get(
            reverse("accounts:mfa_pending")
        )
        valid = MFAService.generate_totp_code(
            response.context["secret"]
        )
        invalid = valid[:-1] + (
            "0" if valid[-1] != "0" else "1"
        )
        for _ in range(5):
            self.client.post(
                reverse("accounts:mfa_pending"),
                {"code": invalid},
            )
        self.assertNotIn(
            "_gpc_pending_auth_user_id",
            self.client.session,
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_existing_device_requires_challenge_before_login(self):
        self._enroll()
        self.client.post(reverse("accounts:logout"))
        self._primary_login()
        response = self.client.get(reverse("accounts:mfa_pending"))
        self.assertTemplateUsed(response, "accounts/mfa_challenge.html")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_valid_totp_challenge_completes_login(self):
        enrollment_response = self._enroll()
        device = MFADevice.objects.get(
            user=self.user,
            device_type=MFADevice.DeviceType.TOTP,
        )
        device.last_used_at = None
        device.save(update_fields=["last_used_at"])
        self.client.post(reverse("accounts:logout"))
        self._primary_login()
        secret = MFAService._decrypt(device).decode("ascii")
        code = MFAService.generate_totp_code(secret)
        response = self.client.post(
            reverse("accounts:mfa_pending"),
            {"code": code},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(SESSION_KEY, self.client.session)
        self.assertIsNotNone(enrollment_response.context["recovery_codes"])

    def test_recovery_code_completes_login_only_once(self):
        enrollment_response = self._enroll()
        recovery_code = enrollment_response.context["recovery_codes"][0]
        self.client.post(reverse("accounts:logout"))
        self._primary_login()
        first = self.client.post(
            reverse("accounts:mfa_pending"),
            {"code": recovery_code},
        )
        self.assertEqual(first.status_code, 302)
        self.client.post(reverse("accounts:logout"))
        self._primary_login()
        second = self.client.post(
            reverse("accounts:mfa_pending"),
            {"code": recovery_code},
        )
        self.assertEqual(second.status_code, 200)
        self.assertContains(
            second,
            "No fue posible verificar el segundo factor.",
        )
        self.assertNotIn(SESSION_KEY, self.client.session)
