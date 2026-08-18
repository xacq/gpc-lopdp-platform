import base64

from django.contrib.auth import (
    get_user_model,
)
from django.test import (
    TestCase,
    override_settings,
)

from apps.cases.models import (
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
    InactiveRightError,
)
from apps.cases.services.intake import (
    CaseIntakeService,
    ExistingRepresentativeDataMismatchError,
    ExistingSubjectDataMismatchError,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.subjects.models import (
    DataSubject,
    SubjectRepresentative,
)
from apps.subjects.services.subjects import (
    RepresentativeService,
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"W" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"X" * 32
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
class CaseIntakeServiceTests(
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

        user_model = get_user_model()

        self.actor = (
            user_model.objects
            .create_user(
                email="actor@example.com",
                password=(
                    "TestPassword123!"
                ),
                full_name="Actor Prueba",
                is_active=True,
            )
        )

    def create_request(
        self,
        **overrides,
    ):
        values = {
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
            "right": self.right,
            "request_details": (
                "Solicitud de prueba"
            ),
            "source_channel": (
                RightsRequest
                .SourceChannel
                .EMAIL
            ),
            "actor": self.actor,
        }

        values.update(
            overrides
        )

        return (
            CaseIntakeService
            .create_administrative_request(
                **values
            )
        )

    def test_new_subject_and_request_are_created(self):
        case = self.create_request()

        self.assertEqual(
            DataSubject.objects.count(),
            1,
        )
        self.assertEqual(
            RightsRequest.objects.count(),
            1,
        )

        snapshot = (
            CaseWorkflowService
            .decrypt_subject_snapshot(
                case
            )
        )

        self.assertEqual(
            snapshot.full_name,
            "Titular Prueba",
        )
        self.assertEqual(
            snapshot.email,
            "subject@example.com",
        )
        self.assertEqual(
            case.source_channel,
            RightsRequest
            .SourceChannel
            .EMAIL,
        )

    def test_existing_subject_is_reused(self):
        existing = (
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number=(
                    "1712345678"
                ),
                full_name=(
                    "Titular Prueba"
                ),
                email=(
                    "subject@example.com"
                ),
                phone=(
                    "+593991234567"
                ),
            )
        )

        case = self.create_request()

        self.assertEqual(
            DataSubject.objects.count(),
            1,
        )
        self.assertEqual(
            case.data_subject_id,
            existing.id,
        )

    def test_existing_subject_mismatch_is_rejected(self):
        SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Original",
            email="original@example.com",
        )

        with self.assertRaises(
            ExistingSubjectDataMismatchError
        ):
            self.create_request(
                full_name="Titular Distinto",
                email="different@example.com",
                phone=None,
            )

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )
        self.assertEqual(
            DataSubject.objects.count(),
            1,
        )

    def test_representative_is_created_and_attached(self):
        case = self.create_request(
            representative_name=(
                "Representante Prueba"
            ),
            representative_document_type=(
                "CEDULA"
            ),
            representative_document_number=(
                "0912345678"
            ),
            representative_email=(
                "representative@example.com"
            ),
        )

        self.assertEqual(
            SubjectRepresentative
            .objects.count(),
            1,
        )

        self.assertIsNotNone(
            case.representative_id
        )

        representative = (
            RepresentativeService
            .decrypt(
                case.representative
            )
        )

        self.assertEqual(
            representative
            .representative_name,
            "Representante Prueba",
        )

    def test_existing_representative_mismatch_is_rejected(self):
        subject = (
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number=(
                    "1712345678"
                ),
                full_name=(
                    "Titular Prueba"
                ),
                email=(
                    "subject@example.com"
                ),
                phone=(
                    "+593991234567"
                ),
            )
        )

        RepresentativeService.create(
            data_subject=subject,
            representative_name=(
                "Representante Original"
            ),
            representative_document_type=(
                "CEDULA"
            ),
            representative_document_number=(
                "0912345678"
            ),
        )

        with self.assertRaises(
            ExistingRepresentativeDataMismatchError
        ):
            self.create_request(
                representative_name=(
                    "Representante Distinto"
                ),
                representative_document_type=(
                    "CEDULA"
                ),
                representative_document_number=(
                    "0912345678"
                ),
            )

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )

    def test_request_failure_rolls_back_new_subject(self):
        self.right.is_active = False
        self.right.save(
            update_fields=[
                "is_active",
            ]
        )

        with self.assertRaises(
            InactiveRightError
        ):
            self.create_request()

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )
        self.assertEqual(
            DataSubject.objects.count(),
            0,
        )
