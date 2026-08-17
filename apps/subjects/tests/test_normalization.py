from django.test import SimpleTestCase

from apps.subjects.services.normalization import (
    normalize_document_number,
    normalize_email,
    normalize_full_name,
    normalize_phone,
)


class SubjectNormalizationTests(
    SimpleTestCase
):

    def test_normalizes_cedula(self):
        self.assertEqual(
            normalize_document_number(
                "CEDULA",
                " 171-234-5678 ",
            ),
            "1712345678",
        )

    def test_normalizes_passport(self):
        self.assertEqual(
            normalize_document_number(
                "PASSPORT",
                " ab  12345 ",
            ),
            "AB 12345",
        )

    def test_normalizes_email(self):
        self.assertEqual(
            normalize_email(
                " USER@Example.COM "
            ),
            "user@example.com",
        )

    def test_normalizes_name(self):
        self.assertEqual(
            normalize_full_name(
                " María   Elena  Terán "
            ),
            "María Elena Terán",
        )

    def test_normalizes_phone(self):
        self.assertEqual(
            normalize_phone(
                "+593 (99) 123-4567"
            ),
            "+593991234567",
        )