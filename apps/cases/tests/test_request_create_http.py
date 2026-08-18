import base64

from django.contrib.auth import (
    get_user_model,
)
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from apps.accounts.models import (
    Role,
    UserRole,
)
from apps.accounts.tests_helpers import force_mfa_login
from apps.cases.models import (
    RightsRequest,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.subjects.models import (
    DataSubject,
)


ENCRYPTION_KEY = base64.b64encode(
    b"Y" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"Z" * 32
).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={
        1: ENCRYPTION_KEY,
    },
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={
        1: LOOKUP_KEY,
    },
)
class RequestCreateHttpTests(
    TestCase
):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name=(
                "VINOS Y ESPIRITUOSOS "
                "VINESA S.A."
            ),
            trade_name="VINESA",
            ruc="1792049598001",
            domain=(
                "privacidad.vinesa.test"
            ),
            contact_email=(
                "privacidad@vinesa.com.ec"
            ),
            request_prefix="VINESA",
            timezone=(
                "America/Guayaquil"
            ),
        )

        self.right = (
            RightCatalog.objects.create(
                code="TEST_RIGHT",
                name="Derecho de prueba",
                is_active=True,
            )
        )

        self.inactive_right = (
            RightCatalog.objects.create(
                code="INACTIVE_RIGHT",
                name="Derecho inactivo",
                is_active=False,
            )
        )

        self.manager = (
            self.create_user_with_role(
                email="manager-create@example.com",
                role_code=(
                    Role.Code.RESPONSABLE
                ),
            )
        )

        self.operator = (
            self.create_user_with_role(
                email="operator-create@example.com",
                role_code=(
                    Role.Code.OPERADOR
                ),
            )
        )

    def create_user_with_role(
        self,
        *,
        email,
        role_code,
    ):
        user_model = get_user_model()

        user = (
            user_model.objects
            .create_user(
                email=email,
                password=(
                    "TestPassword123!"
                ),
                full_name=(
                    "Usuario Prueba"
                ),
                is_active=True,
            )
        )

        role, _ = (
            Role.objects.get_or_create(
                code=role_code,
                defaults={
                    "name": role_code,
                    "is_active": True,
                },
            )
        )

        UserRole.objects.create(
            user=user,
            role=role,
            is_primary=True,
        )

        return user

    def valid_payload(self):
        return {
            "subject_type": (
                "CUSTOMER"
            ),
            "document_type": (
                "CEDULA"
            ),
            "document_number": (
                "1712345678"
            ),
            "full_name": (
                "Titular Prueba"
            ),
            "email": (
                "subject@example.com"
            ),
            "phone": (
                "+593991234567"
            ),
            "right": str(
                self.right.id
            ),
            "request_details": (
                "Necesito ejercer "
                "mi derecho."
            ),
            "source_channel": (
                RightsRequest
                .SourceChannel
                .EMAIL
            ),
        }

    def test_unauthenticated_create_redirects_to_login(self):
        response = self.client.get(
            reverse(
                "cases:request_create"
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_operator_cannot_open_create_form(self):
        force_mfa_login(self.client,
            self.operator
        )

        response = self.client.get(
            reverse(
                "cases:request_create"
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_create_form_lists_only_active_rights(self):
        force_mfa_login(self.client,
            self.manager
        )

        response = self.client.get(
            reverse(
                "cases:request_create"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        field = (
            response.context[
                "form"
            ]
            .fields["right"]
        )

        right_ids = set(
            field.queryset.values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(
            self.right.id,
            right_ids,
        )
        self.assertNotIn(
            self.inactive_right.id,
            right_ids,
        )

    def test_manager_can_create_request(self):
        force_mfa_login(self.client,
            self.manager
        )

        response = self.client.post(
            reverse(
                "cases:request_create"
            ),
            self.valid_payload(),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            RightsRequest.objects.count(),
            1,
        )
        self.assertEqual(
            DataSubject.objects.count(),
            1,
        )

        case = (
            RightsRequest.objects.get()
        )

        self.assertEqual(
            case.status,
            RightsRequest
            .Status
            .RECEIVED,
        )

        self.assertEqual(
            case.source_channel,
            RightsRequest
            .SourceChannel
            .EMAIL,
        )

    def test_incomplete_representative_is_rejected_by_form(self):
        force_mfa_login(self.client,
            self.manager
        )

        payload = (
            self.valid_payload()
        )

        payload.update(
            {
                "has_representative": (
                    "on"
                ),
                "representative_name": (
                    "Representante Prueba"
                ),
            }
        )

        response = self.client.post(
            reverse(
                "cases:request_create"
            ),
            payload,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )

        self.assertTrue(
            response.context[
                "form"
            ].errors
        )

    def test_existing_subject_mismatch_does_not_create_case(self):
        from apps.subjects.services.subjects import (
            SubjectService,
        )

        SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number=(
                "1712345678"
            ),
            full_name=(
                "Titular Original"
            ),
            email=(
                "original@example.com"
            ),
        )

        force_mfa_login(self.client,
            self.manager
        )

        response = self.client.post(
            reverse(
                "cases:request_create"
            ),
            self.valid_payload(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )
        self.assertEqual(
            DataSubject.objects.count(),
            1,
        )

        self.assertTrue(
            response.context[
                "form"
            ].non_field_errors()
        )
