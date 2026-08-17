import base64

from django.test import TestCase, override_settings

from apps.core.services.crypto import CryptoService
from apps.subjects.models import DataSubject
from apps.subjects.services.subjects import (
    SubjectAlreadyExistsError,
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"C" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"D" * 32
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
class SubjectServiceTests(TestCase):

    def test_create_stores_encrypted_pii(self):
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="171-234-5678",
            full_name="María Elena Terán",
            email="Maria.Teran@Example.com",
            phone="+593 99 123 4567",
        )

        # Fuerza lectura real desde PostgreSQL.
        subject = DataSubject.objects.get(
            pk=subject.pk
        )

        self.assertEqual(
            subject.document_type,
            "CEDULA",
        )

        self.assertEqual(
            subject.subject_type,
            "CUSTOMER",
        )

        self.assertEqual(
            len(
                subject.document_number_lookup_hash
            ),
            64,
        )

        self.assertEqual(
            len(subject.email_lookup_hash),
            64,
        )

        self.assertEqual(
            subject.encryption_key_version,
            1,
        )

        self.assertEqual(
            subject.lookup_key_version,
            1,
        )

        encrypted_document = bytes(
            subject.document_number_encrypted
        )

        encrypted_name = bytes(
            subject.full_name_encrypted
        )

        encrypted_email = bytes(
            subject.email_encrypted
        )

        encrypted_phone = bytes(
            subject.phone_encrypted
        )

        self.assertNotIn(
            b"1712345678",
            encrypted_document,
        )

        self.assertNotIn(
            "María Elena Terán".encode("utf-8"),
            encrypted_name,
        )

        self.assertNotIn(
            b"maria.teran@example.com",
            encrypted_email,
        )

        self.assertNotIn(
            b"+593991234567",
            encrypted_phone,
        )

    def test_create_and_decrypt_round_trip(self):
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="María Elena Terán",
            email="Maria.Teran@Example.com",
            phone="+593 99 123 4567",
        )

        # Importante: descifrar una instancia
        # recuperada nuevamente desde PostgreSQL.
        subject = DataSubject.objects.get(
            pk=subject.pk
        )

        pii = SubjectService.decrypt(
            subject
        )

        self.assertEqual(
            pii.document_number,
            "1712345678",
        )

        self.assertEqual(
            pii.full_name,
            "María Elena Terán",
        )

        self.assertEqual(
            pii.email,
            "maria.teran@example.com",
        )

        self.assertEqual(
            pii.phone,
            "+593991234567",
        )

    def test_find_by_document_uses_normalization(self):
        created = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Test User",
            email="test@example.com",
        )

        found = SubjectService.find_by_document(
            document_type="CEDULA",
            document_number=" 171-234-5678 ",
        )

        self.assertIsNotNone(found)

        self.assertEqual(
            found.id,
            created.id,
        )

    def test_duplicate_document_is_rejected(self):
        first = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="First User",
            email="first@example.com",
        )

        with self.assertRaises(
            SubjectAlreadyExistsError
        ) as context:
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number="171-234-5678",
                full_name="Second User",
                email="second@example.com",
            )

        self.assertEqual(
            context.exception.subject_id,
            first.id,
        )

        self.assertEqual(
            DataSubject.objects.count(),
            1,
        )

    def test_lookup_hash_matches_expected_hmac(self):
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Test User",
            email="TEST@EXAMPLE.COM",
        )

        expected_document = (
            CryptoService.lookup_hash(
                "document:CEDULA:1712345678",
                key_version=1,
            )
        )

        expected_email = (
            CryptoService.lookup_hash(
                "email:test@example.com",
                key_version=1,
            )
        )

        self.assertEqual(
            subject.document_number_lookup_hash,
            expected_document.value,
        )

        self.assertEqual(
            subject.email_lookup_hash,
            expected_email.value,
        )