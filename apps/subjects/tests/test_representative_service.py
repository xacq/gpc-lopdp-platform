import base64

from django.test import TestCase, override_settings

from apps.subjects.models import (
    DataSubject,
    SubjectRepresentative,
)
from apps.subjects.services.subjects import (
    RepresentativeAlreadyExistsError,
    RepresentativeService,
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"E" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"F" * 32
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
class RepresentativeServiceTests(TestCase):

    def create_subject(
        self,
        document_number="1712345678",
        email="subject@example.com",
    ):
        return SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number=document_number,
            full_name="Titular Prueba",
            email=email,
        )

    def test_create_and_decrypt_round_trip(self):
        subject = self.create_subject()

        representative = (
            RepresentativeService.create(
                data_subject=subject,
                representative_name=(
                    "María Representante"
                ),
                representative_document_type=(
                    "CEDULA"
                ),
                representative_document_number=(
                    "091-234-5678"
                ),
                representative_email=(
                    "REP@EXAMPLE.COM"
                ),
            )
        )

        representative = (
            SubjectRepresentative.objects.get(
                pk=representative.pk
            )
        )

        pii = RepresentativeService.decrypt(
            representative
        )

        self.assertEqual(
            pii.representative_name,
            "María Representante",
        )

        self.assertEqual(
            pii.representative_document_number,
            "0912345678",
        )

        self.assertEqual(
            pii.representative_email,
            "rep@example.com",
        )

        self.assertEqual(
            pii.verification_status,
            "PENDING",
        )

    def test_pii_is_encrypted_in_database(self):
        subject = self.create_subject()

        representative = (
            RepresentativeService.create(
                data_subject=subject,
                representative_name="Test Rep",
                representative_document_type="CEDULA",
                representative_document_number="0912345678",
                representative_email="rep@example.com",
            )
        )

        representative = (
            SubjectRepresentative.objects.get(
                pk=representative.pk
            )
        )

        self.assertNotIn(
            b"0912345678",
            bytes(
                representative
                .representative_document_encrypted
            ),
        )

        encrypted_email = (
            representative
            .representative_email_encrypted
        )

        assert encrypted_email is not None

        self.assertNotIn(
            b"rep@example.com",
            bytes(encrypted_email),
        )

        self.assertEqual(
            len(
                representative
                .representative_document_lookup_hash
            ),
            64,
        )

    def test_find_uses_normalization(self):
        subject = self.create_subject()

        created = RepresentativeService.create(
            data_subject=subject,
            representative_name="Test Rep",
            representative_document_type="CEDULA",
            representative_document_number="0912345678",
        )

        found = RepresentativeService.find_by_document(
            data_subject=subject,
            document_type="CEDULA",
            document_number=" 091-234-5678 ",
        )

        self.assertIsNotNone(found)
        self.assertEqual(
            found.id,
            created.id,
        )

    def test_duplicate_for_same_subject_is_rejected(self):
        subject = self.create_subject()

        first = RepresentativeService.create(
            data_subject=subject,
            representative_name="First Rep",
            representative_document_type="CEDULA",
            representative_document_number="0912345678",
        )

        with self.assertRaises(
            RepresentativeAlreadyExistsError
        ) as context:
            RepresentativeService.create(
                data_subject=subject,
                representative_name="Second Rep",
                representative_document_type="CEDULA",
                representative_document_number="091-234-5678",
            )

        self.assertEqual(
            context.exception.representative_id,
            first.id,
        )

        self.assertEqual(
            SubjectRepresentative.objects.count(),
            1,
        )

    def test_same_document_allowed_for_different_subjects(self):
        first_subject = self.create_subject(
            document_number="1712345678",
            email="first@example.com",
        )

        second_subject = self.create_subject(
            document_number="1712345679",
            email="second@example.com",
        )

        first = RepresentativeService.create(
            data_subject=first_subject,
            representative_name="Same Rep",
            representative_document_type="CEDULA",
            representative_document_number="0912345678",
        )

        second = RepresentativeService.create(
            data_subject=second_subject,
            representative_name="Same Rep",
            representative_document_type="CEDULA",
            representative_document_number="0912345678",
        )

        self.assertNotEqual(
            first.id,
            second.id,
        )

        self.assertNotEqual(
            first.representative_document_lookup_hash,
            second.representative_document_lookup_hash,
        )

        self.assertEqual(
            SubjectRepresentative.objects.count(),
            2,
        )