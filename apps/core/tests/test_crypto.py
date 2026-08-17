import base64

from django.test import SimpleTestCase, override_settings

from apps.core.services.crypto import (
    CryptoDecryptionError,
    CryptoService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"A" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"B" * 32
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
class CryptoServiceTests(SimpleTestCase):

    def test_encrypt_decrypt_text_round_trip(self):
        plaintext = "1712345678"

        encrypted = CryptoService.encrypt_text(
            plaintext,
            aad="subject:123:document_number",
        )

        self.assertEqual(
            encrypted.key_version,
            1,
        )

        self.assertNotIn(
            plaintext.encode("utf-8"),
            encrypted.data,
        )

        decrypted = CryptoService.decrypt_text(
            encrypted.data,
            aad="subject:123:document_number",
            key_version=encrypted.key_version,
        )

        self.assertEqual(
            decrypted,
            plaintext,
        )

    def test_wrong_aad_fails_authentication(self):
        encrypted = CryptoService.encrypt_text(
            "personal data",
            aad="field:a",
        )

        with self.assertRaises(
            CryptoDecryptionError
        ):
            CryptoService.decrypt_text(
                encrypted.data,
                aad="field:b",
                key_version=1,
            )

    def test_modified_ciphertext_fails(self):
        encrypted = CryptoService.encrypt_text(
            "personal data",
            aad="field:a",
        )

        tampered = bytearray(
            encrypted.data
        )

        tampered[-1] ^= 1

        with self.assertRaises(
            CryptoDecryptionError
        ):
            CryptoService.decrypt_text(
                bytes(tampered),
                aad="field:a",
                key_version=1,
            )

    def test_lookup_hash_is_deterministic(self):
        first = CryptoService.lookup_hash(
            "canonical-value"
        )

        second = CryptoService.lookup_hash(
            "canonical-value"
        )

        self.assertEqual(
            first.value,
            second.value,
        )

        self.assertEqual(
            len(first.value),
            64,
        )

        self.assertEqual(
            first.key_version,
            1,
        )

    def test_different_values_have_different_hashes(self):
        first = CryptoService.lookup_hash(
            "value-a"
        )

        second = CryptoService.lookup_hash(
            "value-b"
        )

        self.assertNotEqual(
            first.value,
            second.value,
        )