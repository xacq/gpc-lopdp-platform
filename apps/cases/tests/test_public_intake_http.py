import base64
from datetime import timedelta
import re
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.cases.models import RequestAccessToken, RightsRequest
from apps.cases.services.public_intake import (
    PublicEmailVerificationAccessError,
    PublicEmailVerificationService,
    PublicIntakeService,
)
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import (
    NotificationService,
    NotificationServiceError,
)
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting


ENCRYPTION_KEY = base64.b64encode(b"W" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"X" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    PUBLIC_EMAIL_VERIFICATION_TTL_SECONDS=24 * 60 * 60,
    PUBLIC_TRACKING_TTL_SECONDS=90 * 24 * 60 * 60,
)
class PublicIntakeTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name="VINOS Y ESPIRITUOSOS VINESA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
            contact_email="privacidad@vinesa.com.ec",
            request_prefix="VINESA",
            timezone="America/Guayaquil",
        )
        self.right = RightCatalog.objects.create(
            code="PUBLIC_INTAKE_TEST",
            name="Derecho público de prueba",
            is_active=True,
        )
        self.values = {
            "subject_type": "CUSTOMER",
            "document_type": "CEDULA",
            "document_number": "1712345678",
            "full_name": "Titular Público",
            "email": "public-subject@example.com",
            "phone": "+593 99 123 4567",
            "right": self.right,
            "request_details": "Solicitud pública confidencial",
        }

    def submit(self, **overrides):
        values = dict(self.values)
        values.update(overrides)
        return PublicIntakeService.submit(**values)

    def tokens_from_message(self, result):
        payload = NotificationService.decrypt_payload(result.communication)
        verification = re.search(
            r"Código de verificación: (\S+)", payload["body"]
        ).group(1)
        tracking = re.search(
            r"Código de seguimiento: (\S+)", payload["body"]
        ).group(1)
        return verification, tracking, payload

    def test_service_creates_pending_case_tokens_and_encrypted_outbox(self):
        result = self.submit()
        verification, tracking, payload = self.tokens_from_message(result)

        self.assertEqual(result.request.source_channel, RightsRequest.SourceChannel.WEB)
        self.assertEqual(
            result.request.identity_status,
            RightsRequest.IdentityStatus.PENDING,
        )
        self.assertEqual(result.communication.delivery_status, "PENDING")
        self.assertFalse(result.communication.visible_to_subject)
        self.assertEqual(
            set(result.request.access_tokens.values_list("purpose", flat=True)),
            {
                RequestAccessToken.Purpose.EMAIL_VERIFICATION,
                RequestAccessToken.Purpose.TRACKING,
            },
        )
        self.assertIn(result.request.reference_number, payload["body"])
        self.assertIn("https://privacidad.vinesa.test/", payload["body"])
        self.assertIn("VINESA", payload["body"])
        self.assertIn(
            "Plataforma de Privacidad y Gestión de Solicitudes LOPDP",
            payload["body"],
        )
        self.assertIn("Paso 1: verifica tu correo electrónico", payload["body"])
        self.assertIn(
            "Paso 2: consulta el seguimiento de tu trámite",
            payload["body"],
        )
        self.assertNotIn(
            verification.encode(),
            bytes(result.communication.body_encrypted),
        )
        self.assertNotIn(
            tracking.encode(),
            bytes(result.communication.body_encrypted),
        )

    def test_email_verification_is_single_use_and_keeps_identity_pending(self):
        result = self.submit()
        verification, _, _ = self.tokens_from_message(result)

        verified = PublicEmailVerificationService.verify(
            reference_number=result.request.reference_number.lower(),
            token=verification,
        )
        self.assertEqual(verified.reference_number, result.request.reference_number)
        result.request.refresh_from_db()
        self.assertEqual(
            result.request.identity_status,
            RightsRequest.IdentityStatus.PENDING,
        )
        token = result.request.access_tokens.get(
            purpose=RequestAccessToken.Purpose.EMAIL_VERIFICATION
        )
        self.assertIsNotNone(token.revoked_at)
        self.assertTrue(
            AuditLog.objects.filter(
                action="PUBLIC_REQUEST_EMAIL_VERIFIED",
                entity_pk=str(result.request.id),
            ).exists()
        )

        with self.assertRaises(PublicEmailVerificationAccessError):
            PublicEmailVerificationService.verify(
                reference_number=result.request.reference_number,
                token=verification,
            )

    def test_failed_outbox_queue_rolls_back_entire_submission(self):
        with patch.object(
            NotificationService,
            "queue_email",
            side_effect=NotificationServiceError("simulated"),
        ):
            with self.assertRaises(NotificationServiceError):
                self.submit()

        self.assertFalse(RightsRequest.objects.exists())
        self.assertFalse(RequestAccessToken.objects.exists())
        self.assertFalse(RequestCommunication.objects.exists())

    def test_audit_never_contains_pii_or_access_codes(self):
        result = self.submit()
        verification, tracking, _ = self.tokens_from_message(result)
        PublicEmailVerificationService.verify(
            reference_number=result.request.reference_number,
            token=verification,
        )
        serialized = str(
            list(
                AuditLog.objects.values(
                    "description",
                    "metadata",
                )
            )
        )
        for forbidden in (
            self.values["full_name"],
            self.values["email"],
            self.values["document_number"],
            self.values["request_details"],
            verification,
            tracking,
        ):
            self.assertNotIn(forbidden, serialized)

    @override_settings(PUBLIC_SITE_URL="http://localhost:8080")
    def test_acknowledgement_uses_configured_public_site_url(self):
        result = self.submit()
        payload = NotificationService.decrypt_payload(result.communication)

        self.assertIn(
            "http://localhost:8080/cases/public/verify-email/",
            payload["body"],
        )
        self.assertIn(
            "http://localhost:8080/cases/public/tracking/",
            payload["body"],
        )


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    PUBLIC_EMAIL_VERIFICATION_TTL_SECONDS=24 * 60 * 60,
    PUBLIC_TRACKING_TTL_SECONDS=90 * 24 * 60 * 60,
)
class PublicIntakeHttpTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name="VINOS Y ESPIRITUOSOS VINESA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
            contact_email="privacidad@vinesa.com.ec",
            request_prefix="VINESA",
            timezone="America/Guayaquil",
        )
        self.right = RightCatalog.objects.create(
            code="PUBLIC_INTAKE_HTTP",
            name="Acceso HTTP",
            is_active=True,
        )
        self.post_data = {
            "subject_type": "CUSTOMER",
            "document_type": "CEDULA",
            "document_number": "1723456789",
            "full_name": "Titular Formulario",
            "email": "form-subject@example.com",
            "phone": "+593 98 000 0000",
            "right": str(self.right.id),
            "request_details": "Detalle secreto desde formulario",
            "has_representative": "",
            "representative_name": "",
            "representative_document_type": "",
            "representative_document_number": "",
            "representative_email": "",
            "privacy_acknowledgement": "on",
            "website": "",
        }

    def assert_private_headers(self, response):
        self.assertEqual(response["Cache-Control"], "no-store, max-age=0")
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_public_request_form_is_anonymous_and_excludes_source_channel(self):
        response = self.client.get(reverse("cases:public_request_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Presentar una solicitud")
        self.assertContains(response, "Guía rápida")
        self.assertContains(response, "¿Cómo se presenta la solicitud?")
        self.assertContains(response, "Registra tus datos")
        self.assertContains(response, "Envía y verifica tu correo")
        self.assertContains(response, "Seleccionar archivo", count=3)
        self.assertContains(response, "Ningún archivo seleccionado", count=3)
        self.assertContains(
            response,
            "Tamaño máximo por archivo: 25 MB",
            count=3,
        )
        self.assertContains(
            response,
            "También acepto la",
        )
        self.assertContains(response, "Política de Privacidad")
        self.assertContains(response, "de VINESA y autorizo")
        self.assertContains(
            response,
            "Si tienes más documentación que no puedas adjuntar",
        )
        self.assertNotContains(response, 'name="source_channel"')
        self.assertContains(response, 'name="website"', html=False)
        self.assertNotContains(response, "novalidate")
        html = response.content.decode()
        for field_name in (
            "subject_type",
            "document_type",
            "document_number",
            "full_name",
            "email",
            "right",
            "request_details",
            "privacy_acknowledgement",
        ):
            self.assertRegex(
                html,
                rf'<(?:input|select|textarea)[^>]*name="{field_name}"[^>]*required',
            )
        for field_name in (
            "phone",
            "representative_name",
            "representative_document_type",
            "representative_document_number",
            "representative_email",
            "identity_document",
            "authority_document",
            "supporting_document",
        ):
            self.assertNotRegex(
                html,
                rf'<(?:input|select|textarea)[^>]*name="{field_name}"[^>]*required',
            )
        self.assert_private_headers(response)

    def test_public_tracking_guides_email_verification_before_status_lookup(self):
        response = self.client.get(reverse("cases:public_tracking"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Consulta tu solicitud")
        self.assertContains(response, "Antes de consultar el estado")
        self.assertContains(
            response,
            "Si todavía no has validado tu correo electrónico",
        )
        self.assertContains(response, "Verificar correo")
        self.assertContains(
            response,
            reverse("cases:public_email_verification"),
        )
        self.assert_private_headers(response)

    def test_valid_submission_uses_prg_and_queues_encrypted_email(self):
        response = self.client.post(
            reverse("cases:public_request_create"), self.post_data
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response["Location"], reverse("cases:public_request_received")
        )
        self.assertEqual(RightsRequest.objects.count(), 1)
        self.assertEqual(RequestCommunication.objects.count(), 1)
        self.assertNotIn(self.post_data["email"], response.content.decode())
        self.assert_private_headers(response)

        confirmation = self.client.get(response["Location"])
        self.assertContains(confirmation, "Revisa tu correo electrónico")
        self.assertNotContains(confirmation, self.post_data["email"])
        self.assertNotContains(confirmation, self.post_data["document_number"])

    def test_invalid_form_does_not_create_request(self):
        data = dict(self.post_data)
        data["privacy_acknowledgement"] = ""
        response = self.client.post(
            reverse("cases:public_request_create"), data
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo es obligatorio")
        self.assertFalse(RightsRequest.objects.exists())

    def test_missing_basic_request_data_shows_field_errors(self):
        data = dict(self.post_data)
        for field_name in (
            "subject_type",
            "document_type",
            "document_number",
            "full_name",
            "email",
            "right",
            "request_details",
            "privacy_acknowledgement",
        ):
            data[field_name] = ""

        response = self.client.post(
            reverse("cases:public_request_create"), data
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo es obligatorio", count=8)
        self.assertFalse(RightsRequest.objects.exists())

    def test_existing_subject_mismatch_uses_same_generic_confirmation(self):
        first = self.client.post(
            reverse("cases:public_request_create"), self.post_data
        )
        mismatched = dict(self.post_data)
        mismatched["email"] = "different-owner@example.com"
        second = self.client.post(
            reverse("cases:public_request_create"), mismatched
        )

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(first["Location"], second["Location"])
        self.assertEqual(RightsRequest.objects.count(), 1)
        self.assertEqual(RequestCommunication.objects.count(), 1)

    def test_honeypot_rejects_automated_submission(self):
        data = dict(self.post_data)
        data["website"] = "https://spam.example"
        response = self.client.post(
            reverse("cases:public_request_create"), data
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fue posible procesar")
        self.assertFalse(RightsRequest.objects.exists())

    def test_email_verification_http_consumes_code_without_echoing_it(self):
        self.client.post(reverse("cases:public_request_create"), self.post_data)
        communication = RequestCommunication.objects.get()
        payload = NotificationService.decrypt_payload(communication)
        verification = re.search(
            r"Código de verificación: (\S+)", payload["body"]
        ).group(1)
        reference = communication.request.reference_number

        response = self.client.post(
            reverse("cases:public_email_verification"),
            {"reference_number": reference, "token": verification},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "verificado correctamente")
        self.assertNotContains(response, verification)
        self.assert_private_headers(response)

    def test_verification_errors_are_generic_and_do_not_echo_codes(self):
        invalid_code = "invalid-verification-code"
        response = self.client.post(
            reverse("cases:public_email_verification"),
            {
                "reference_number": "VINESA-2099-999999",
                "token": invalid_code,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fue posible verificar")
        self.assertNotContains(response, invalid_code)
        self.assertNotContains(response, "VINESA-2099-999999")
        self.assert_private_headers(response)

    @override_settings(PUBLIC_TRACKING_RESEND_COOLDOWN_SECONDS=60)
    def test_tracking_code_resend_queues_email_without_echoing_pii(self):
        self.client.post(reverse("cases:public_request_create"), self.post_data)
        first = RequestCommunication.objects.get()
        tracking_token = first.request.access_tokens.get(
            purpose=RequestAccessToken.Purpose.TRACKING
        )
        tracking_token.created_at = timezone.now() - timedelta(minutes=2)
        tracking_token.save(update_fields=["created_at"])

        response = self.client.post(
            reverse("cases:public_tracking_code_resend"),
            {
                "reference_number": first.request.reference_number,
                "email": self.post_data["email"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "recibirás un nuevo código")
        self.assertNotContains(response, first.request.reference_number)
        self.assertNotContains(response, self.post_data["email"])
        self.assertEqual(RequestCommunication.objects.count(), 2)
        self.assert_private_headers(response)

    def test_public_intake_and_verification_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        intake_response = client.post(
            reverse("cases:public_request_create"), self.post_data
        )
        verify_response = client.post(
            reverse("cases:public_email_verification"),
            {"reference_number": "X", "token": "Y"},
        )
        self.assertEqual(intake_response.status_code, 403)
        self.assertEqual(verify_response.status_code, 403)

    def test_public_intake_accepts_csrf_from_http_application_origin(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("cases:public_request_create")
        client.get(url)
        data = {
            **self.post_data,
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }

        response = client.post(
            url,
            data,
            HTTP_ORIGIN="http://testserver",
        )

        self.assertEqual(response.status_code, 303)
