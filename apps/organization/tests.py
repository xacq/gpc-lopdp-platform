from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.organization.models import SystemSetting
from apps.organization.services import (
    SystemSettingsPermissionError,
    SystemSettingsService,
    SystemSettingsValidationError,
)


class SystemSettingsBase(TestCase):
    PASSWORD = "StrongConfigurationPassword!593"

    def setUp(self):
        self.admin_role = Role.objects.create(
            code=Role.Code.ADMIN,
            name="Administrador",
            is_active=True,
        )
        self.operator_role = Role.objects.create(
            code=Role.Code.OPERADOR,
            name="Operador",
            is_active=True,
        )
        self.admin = self._user(
            "settings-admin@example.com",
            self.admin_role,
        )
        self.operator = self._user(
            "settings-operator@example.com",
            self.operator_role,
        )

    def _user(self, email, role):
        user = get_user_model().objects.create_user(
            email=email,
            password=self.PASSWORD,
            full_name="Usuario Configuración",
            is_active=True,
        )
        UserRole.objects.create(
            user=user,
            role=role,
            is_primary=True,
        )
        return user

    def values(self, **overrides):
        values = {
            "legal_name": "VINOS Y ESPIRITUOSOS VINESA S.A.",
            "trade_name": "VINESA",
            "ruc": "1792049598001",
            "domain": "PRIVACIDAD.VINESA.TEST.",
            "address": "Quito, Ecuador",
            "phone": "+593 2 000 0000",
            "contact_email": "Privacidad@Vinesa.com.ec",
            "controller_name": "Responsable VINESA",
            "controller_email": "Responsable@Vinesa.com.ec",
            "controller_phone": "+593 2 111 1111",
            "dpd_name": "DPD VINESA",
            "dpd_email": "DPD@Vinesa.com.ec",
            "dpd_phone": "+593 2 222 2222",
            "complaint_authority_name": (
                "Superintendencia de Protección de Datos Personales"
            ),
            "complaint_channel_url": "https://spdp.gob.ec/reclamos",
            "complaint_instructions": "Presentar el reclamo en línea.",
            "request_prefix": "vinesa",
            "timezone": "America/Guayaquil",
            "logo_url": "https://assets.vinesa.test/logo.svg",
            "favicon_url": "https://assets.vinesa.test/favicon.ico",
            "primary_color": "#aabbcc",
            "secondary_color": "#112233",
            "accent_color": "#445566",
        }
        values.update(overrides)
        return values

    def create_setting(self):
        return SystemSettingsService.save(
            values=self.values(),
            actor=self.admin,
        )


class SystemSettingsServiceTests(SystemSettingsBase):
    def test_create_normalizes_and_persists_singleton(self):
        setting = self.create_setting()
        self.assertEqual(setting.singleton_key, 1)
        self.assertEqual(setting.domain, "privacidad.vinesa.test")
        self.assertEqual(setting.request_prefix, "VINESA")
        self.assertEqual(setting.primary_color, "#AABBCC")
        self.assertEqual(
            setting.contact_email,
            "privacidad@vinesa.com.ec",
        )
        self.assertEqual(SystemSetting.objects.count(), 1)

    def test_update_reuses_singleton(self):
        original = self.create_setting()
        updated = SystemSettingsService.save(
            values=self.values(trade_name="VINESA PRIVACIDAD"),
            actor=self.admin,
        )
        self.assertEqual(updated.pk, original.pk)
        self.assertEqual(updated.trade_name, "VINESA PRIVACIDAD")
        self.assertEqual(SystemSetting.objects.count(), 1)

    def test_unchanged_save_is_idempotent(self):
        self.create_setting()
        audit_count = AuditLog.objects.count()
        SystemSettingsService.save(
            values=self.values(),
            actor=self.admin,
        )
        self.assertEqual(AuditLog.objects.count(), audit_count)

    def test_non_admin_cannot_update_configuration(self):
        with self.assertRaises(SystemSettingsPermissionError):
            SystemSettingsService.save(
                values=self.values(),
                actor=self.operator,
            )

    def test_invalid_domain_rules_are_rejected(self):
        invalid_values = (
            {"ruc": "123"},
            {"domain": "https://vinesa.test/path"},
            {"request_prefix": "INVALID PREFIX"},
            {"timezone": "Mars/Olympus"},
            {"logo_url": "http://assets.vinesa.test/logo.svg"},
            {"primary_color": "blue"},
        )
        for override in invalid_values:
            with self.subTest(override=override):
                with self.assertRaises(SystemSettingsValidationError):
                    SystemSettingsService.save(
                        values=self.values(**override),
                        actor=self.admin,
                    )
        self.assertFalse(SystemSetting.objects.exists())

    def test_audit_contains_field_names_but_no_configuration_values(self):
        setting = self.create_setting()
        audit = AuditLog.objects.get(
            action="SYSTEM_SETTINGS_CREATED"
        )
        self.assertEqual(audit.entity_pk, str(setting.pk))
        self.assertGreater(audit.metadata["changed_field_count"], 0)
        serialized = str(audit.metadata)
        for sensitive_value in (
            setting.legal_name,
            setting.ruc,
            setting.address,
            setting.contact_email,
            setting.dpd_name,
        ):
            self.assertNotIn(sensitive_value, serialized)


class SystemSettingsHttpTests(SystemSettingsBase):
    def setUp(self):
        super().setUp()
        self.setting = self.create_setting()
        AuditLog.objects.all().delete()

    def post_values(self, **overrides):
        values = self.values(**overrides)
        return {
            key: value if value is not None else ""
            for key, value in values.items()
        }

    def test_unauthenticated_request_redirects_to_login(self):
        response = self.client.get(
            reverse("organization:system_settings")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_non_admin_cannot_view_configuration(self):
        force_mfa_login(self.client, self.operator)
        response = self.client.get(
            reverse("organization:system_settings")
        )
        self.assertEqual(response.status_code, 403)

    def test_configuration_requires_recent_reauthentication(self):
        force_mfa_login(
            self.client,
            self.admin,
            sensitive=False,
        )
        response = self.client.get(
            reverse("organization:system_settings")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:reauth"), response["Location"])

    def test_admin_can_view_configuration(self):
        force_mfa_login(self.client, self.admin)
        response = self.client.get(
            reverse("organization:system_settings")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.setting.legal_name)

    def test_admin_can_update_configuration(self):
        force_mfa_login(self.client, self.admin)
        response = self.client.post(
            reverse("organization:system_settings"),
            self.post_values(trade_name="VINESA ACTUALIZADA"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "guardada correctamente")
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.trade_name, "VINESA ACTUALIZADA")

    def test_invalid_https_url_does_not_mutate_configuration(self):
        force_mfa_login(self.client, self.admin)
        response = self.client.post(
            reverse("organization:system_settings"),
            self.post_values(logo_url="http://unsafe.example/logo.svg"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fue posible guardar")
        self.setting.refresh_from_db()
        self.assertEqual(
            self.setting.logo_url,
            "https://assets.vinesa.test/logo.svg",
        )

    def test_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        force_mfa_login(csrf_client, self.admin)
        response = csrf_client.post(
            reverse("organization:system_settings"),
            self.post_values(),
        )
        self.assertEqual(response.status_code, 403)
