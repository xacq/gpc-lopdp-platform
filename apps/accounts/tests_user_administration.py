from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import MFADevice, Role, UserRole
from apps.accounts.services.users import (
    UserAdministrationConflict,
    UserAdministrationPermissionError,
    UserAdministrationService,
    UserAdministrationValidationError,
)
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog


class UserAdministrationBase(TestCase):
    PASSWORD = "StrongInitialPassword!483"
    NEW_PASSWORD = "DifferentSecurePassword!927"

    def setUp(self):
        self.roles = {
            code: Role.objects.create(
                code=code,
                name=label,
                is_active=True,
            )
            for code, label in Role.Code.choices
        }
        self.admin = self._user(
            "admin@example.com",
            Role.Code.ADMIN,
        )
        self.operator = self._user(
            "operator@example.com",
            Role.Code.OPERADOR,
        )

    def _user(self, email, role_code, *, is_active=True):
        user = get_user_model().objects.create_user(
            email=email,
            password=self.PASSWORD,
            full_name="Usuario de Prueba",
            is_active=is_active,
        )
        UserRole.objects.create(
            user=user,
            role=self.roles[role_code],
            is_primary=True,
            assigned_by=(
                self.admin
                if hasattr(self, "admin")
                else None
            ),
        )
        return user

    def _mfa_device(self, user):
        now = timezone.now()
        return MFADevice.objects.create(
            user=user,
            device_name="Test TOTP",
            device_type=MFADevice.DeviceType.TOTP,
            secret_encrypted=b"encrypted-test-secret",
            encryption_key_version=1,
            is_confirmed=True,
            is_active=True,
            confirmed_at=now,
        )


class UserAdministrationServiceTests(UserAdministrationBase):
    def test_create_user_hashes_password_and_assigns_primary_role(self):
        created = UserAdministrationService.create_user(
            email="new.user@example.com",
            full_name="Nueva Persona",
            password=self.NEW_PASSWORD,
            role=self.roles[Role.Code.AUDITOR],
            actor=self.admin,
        )
        self.assertTrue(created.check_password(self.NEW_PASSWORD))
        assignment = UserRole.objects.get(
            user=created,
            revoked_at__isnull=True,
        )
        self.assertTrue(assignment.is_primary)
        self.assertEqual(assignment.role.code, Role.Code.AUDITOR)

    def test_create_user_rejects_weak_password_without_partial_user(self):
        with self.assertRaises(UserAdministrationValidationError):
            UserAdministrationService.create_user(
                email="weak@example.com",
                full_name="Clave Débil",
                password="123",
                role=self.roles[Role.Code.AUDITOR],
                actor=self.admin,
            )
        self.assertFalse(
            get_user_model().objects.filter(
                email="weak@example.com"
            ).exists()
        )

    def test_non_admin_cannot_create_user(self):
        with self.assertRaises(UserAdministrationPermissionError):
            UserAdministrationService.create_user(
                email="forbidden@example.com",
                full_name="No Permitido",
                password=self.NEW_PASSWORD,
                role=self.roles[Role.Code.AUDITOR],
                actor=self.operator,
            )

    def test_change_role_revokes_previous_assignments(self):
        UserAdministrationService.change_primary_role(
            user=self.operator,
            role=self.roles[Role.Code.AUDITOR],
            actor=self.admin,
        )
        active = UserRole.objects.get(
            user=self.operator,
            revoked_at__isnull=True,
        )
        self.assertEqual(active.role.code, Role.Code.AUDITOR)
        self.assertTrue(active.is_primary)
        self.assertEqual(
            UserRole.objects.filter(
                user=self.operator,
                revoked_at__isnull=False,
            ).count(),
            1,
        )

    def test_last_administrator_cannot_be_demoted(self):
        with self.assertRaises(UserAdministrationConflict):
            UserAdministrationService.change_primary_role(
                user=self.admin,
                role=self.roles[Role.Code.AUDITOR],
                actor=self.admin,
            )

    def test_admin_role_cannot_manage_superuser(self):
        superuser = get_user_model().objects.create_superuser(
            email="root@example.com",
            password=self.PASSWORD,
            full_name="Root",
        )
        with self.assertRaises(UserAdministrationPermissionError):
            UserAdministrationService.unlock(
                user=superuser,
                actor=self.admin,
            )

    def test_administrator_cannot_deactivate_self(self):
        with self.assertRaises(UserAdministrationConflict):
            UserAdministrationService.set_active(
                user=self.admin,
                is_active=False,
                actor=self.admin,
            )

    def test_deactivation_revokes_mfa_devices(self):
        device = self._mfa_device(self.operator)
        UserAdministrationService.set_active(
            user=self.operator,
            is_active=False,
            actor=self.admin,
        )
        self.operator.refresh_from_db()
        device.refresh_from_db()
        self.assertFalse(self.operator.is_active)
        self.assertFalse(device.is_active)
        self.assertIsNotNone(device.revoked_at)

    def test_activation_clears_login_lock(self):
        self.operator.is_active = False
        self.operator.failed_login_attempts = 5
        self.operator.locked_until = timezone.now() + timedelta(minutes=10)
        self.operator.save()
        UserAdministrationService.set_active(
            user=self.operator,
            is_active=True,
            actor=self.admin,
        )
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.is_active)
        self.assertEqual(self.operator.failed_login_attempts, 0)
        self.assertIsNone(self.operator.locked_until)

    def test_unlock_clears_failed_attempts(self):
        self.operator.failed_login_attempts = 5
        self.operator.locked_until = timezone.now() + timedelta(minutes=10)
        self.operator.save()
        UserAdministrationService.unlock(
            user=self.operator,
            actor=self.admin,
        )
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.failed_login_attempts, 0)
        self.assertIsNone(self.operator.locked_until)

    def test_password_reset_revokes_mfa_and_never_audits_password(self):
        device = self._mfa_device(self.operator)
        UserAdministrationService.reset_password(
            user=self.operator,
            password=self.NEW_PASSWORD,
            actor=self.admin,
        )
        self.operator.refresh_from_db()
        device.refresh_from_db()
        self.assertTrue(self.operator.check_password(self.NEW_PASSWORD))
        self.assertFalse(device.is_active)
        audit = AuditLog.objects.get(action="USER_PASSWORD_RESET")
        serialized = str(audit.metadata)
        self.assertNotIn(self.NEW_PASSWORD, serialized)
        self.assertNotIn(self.operator.email, serialized)

    def test_create_audit_contains_role_but_no_pii(self):
        created = UserAdministrationService.create_user(
            email="audit-target@example.com",
            full_name="Persona Auditada",
            password=self.NEW_PASSWORD,
            role=self.roles[Role.Code.DPD],
            actor=self.admin,
        )
        audit = AuditLog.objects.get(action="USER_CREATED")
        self.assertEqual(audit.entity_pk, str(created.pk))
        self.assertEqual(audit.metadata["role_code"], Role.Code.DPD)
        serialized = str(audit.metadata)
        self.assertNotIn(created.email, serialized)
        self.assertNotIn(created.full_name, serialized)


class UserAdministrationHttpTests(UserAdministrationBase):
    def _login_admin(self, *, sensitive=True):
        force_mfa_login(
            self.client,
            self.admin,
            sensitive=sensitive,
        )

    def test_unauthenticated_user_list_redirects_to_login(self):
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_non_admin_cannot_view_users(self):
        force_mfa_login(self.client, self.operator)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    def test_user_list_requires_recent_reauthentication(self):
        self._login_admin(sensitive=False)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:reauth"), response["Location"])

    def test_admin_can_view_user_list(self):
        self._login_admin()
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.operator.email)

    def test_admin_can_create_user(self):
        self._login_admin()
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "email": "http-created@example.com",
                "full_name": "Creado por HTTP",
                "role": str(self.roles[Role.Code.AUDITOR].pk),
                "password1": self.NEW_PASSWORD,
                "password2": self.NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            get_user_model().objects.filter(
                email="http-created@example.com"
            ).exists()
        )

    def test_duplicate_email_returns_generic_form_error(self):
        self._login_admin()
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "email": self.operator.email,
                "full_name": "Duplicado",
                "role": str(self.roles[Role.Code.AUDITOR].pk),
                "password1": self.NEW_PASSWORD,
                "password2": self.NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fue posible crear el usuario")

    def test_admin_can_change_primary_role(self):
        self._login_admin()
        response = self.client.post(
            reverse(
                "accounts:user_change_role",
                kwargs={"user_id": self.operator.pk},
            ),
            {"role": str(self.roles[Role.Code.AUDITOR].pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.operator,
                role__code=Role.Code.AUDITOR,
                revoked_at__isnull=True,
                is_primary=True,
            ).exists()
        )

    def test_deactivation_requires_post(self):
        self._login_admin()
        response = self.client.get(
            reverse(
                "accounts:user_deactivate",
                kwargs={"user_id": self.operator.pk},
            )
        )
        self.assertEqual(response.status_code, 405)

    def test_admin_can_deactivate_user(self):
        self._login_admin()
        response = self.client.post(
            reverse(
                "accounts:user_deactivate",
                kwargs={"user_id": self.operator.pk},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.operator.refresh_from_db()
        self.assertFalse(self.operator.is_active)

    def test_admin_cannot_deactivate_self(self):
        self._login_admin()
        response = self.client.post(
            reverse(
                "accounts:user_deactivate",
                kwargs={"user_id": self.admin.pk},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_unlock_user(self):
        self.operator.failed_login_attempts = 5
        self.operator.locked_until = timezone.now() + timedelta(minutes=5)
        self.operator.save()
        self._login_admin()
        response = self.client.post(
            reverse(
                "accounts:user_unlock",
                kwargs={"user_id": self.operator.pk},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.failed_login_attempts, 0)

    def test_admin_can_reset_password(self):
        self._mfa_device(self.operator)
        self._login_admin()
        response = self.client.post(
            reverse(
                "accounts:user_reset_password",
                kwargs={"user_id": self.operator.pk},
            ),
            {
                "password1": self.NEW_PASSWORD,
                "password2": self.NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.check_password(self.NEW_PASSWORD))
        self.assertFalse(
            MFADevice.objects.filter(
                user=self.operator,
                is_active=True,
            ).exists()
        )
