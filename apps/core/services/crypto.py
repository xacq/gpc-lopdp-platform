import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


AES_KEY_SIZE_BYTES = 32
AES_GCM_NONCE_SIZE_BYTES = 12

# Permite cambiar posteriormente el formato físico del blob
# sin confundir ciphertexts antiguos con nuevos.
PAYLOAD_FORMAT_VERSION = 1


class CryptoError(Exception):
    """Base exception for application cryptography."""


class CryptoConfigurationError(CryptoError):
    """Invalid or unavailable cryptographic key configuration."""


class CryptoDecryptionError(CryptoError):
    """Ciphertext authentication or decryption failed."""


@dataclass(frozen=True)
class EncryptedPayload:
    data: bytes
    key_version: int


@dataclass(frozen=True)
class LookupDigest:
    value: str
    key_version: int


def _decode_base64_key(
    encoded_key: str,
    *,
    key_name: str,
) -> bytes:
    if not encoded_key:
        raise CryptoConfigurationError(
            f"{key_name} is not configured."
        )

    try:
        key = base64.b64decode(
            encoded_key,
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise CryptoConfigurationError(
            f"{key_name} is not valid Base64."
        ) from exc

    if len(key) != AES_KEY_SIZE_BYTES:
        raise CryptoConfigurationError(
            f"{key_name} must decode to exactly "
            f"{AES_KEY_SIZE_BYTES} bytes."
        )

    return key


def _get_encryption_key(
    version: int,
) -> bytes:
    encoded_key = settings.PII_ENCRYPTION_KEYS.get(
        version
    )

    return _decode_base64_key(
        encoded_key,
        key_name=f"PII_ENCRYPTION_KEY_V{version}",
    )


def _get_lookup_key(
    version: int,
) -> bytes:
    encoded_key = settings.LOOKUP_HMAC_KEYS.get(
        version
    )

    return _decode_base64_key(
        encoded_key,
        key_name=f"LOOKUP_HMAC_KEY_V{version}",
    )


def _aad_bytes(aad: str | bytes) -> bytes:
    if isinstance(aad, bytes):
        if not aad:
            raise ValueError("AAD cannot be empty.")
        return aad

    if isinstance(aad, str):
        if not aad:
            raise ValueError("AAD cannot be empty.")
        return aad.encode("utf-8")

    raise TypeError(
        "AAD must be str or bytes."
    )


class CryptoService:
    """
    Application cryptographic service.

    Encryption:
        AES-256-GCM.

    Physical BYTEA format:
        1 byte format version
        + 12 byte nonce
        + ciphertext
        + 16 byte GCM authentication tag

    The AES key version itself is stored separately in the
    corresponding database column.
    """

    @classmethod
    def encrypt_bytes(
        cls,
        plaintext: bytes,
        *,
        aad: str | bytes,
        key_version: int | None = None,
    ) -> EncryptedPayload:
        if not isinstance(plaintext, bytes):
            raise TypeError(
                "plaintext must be bytes."
            )

        if key_version is None:
            key_version = (
                settings.PII_ENCRYPTION_ACTIVE_VERSION
            )

        key = _get_encryption_key(key_version)

        nonce = os.urandom(
            AES_GCM_NONCE_SIZE_BYTES
        )

        aesgcm = AESGCM(key)

        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext,
            _aad_bytes(aad),
        )

        payload = (
            bytes([PAYLOAD_FORMAT_VERSION])
            + nonce
            + ciphertext
        )

        return EncryptedPayload(
            data=payload,
            key_version=key_version,
        )

    @classmethod
    def decrypt_bytes(
        cls,
        payload: bytes,
        *,
        aad: str | bytes,
        key_version: int,
    ) -> bytes:
        if not isinstance(payload, bytes):
            raise TypeError(
                "payload must be bytes."
            )

        minimum_length = (
            1
            + AES_GCM_NONCE_SIZE_BYTES
            + 16
        )

        if len(payload) < minimum_length:
            raise CryptoDecryptionError(
                "Encrypted payload is invalid."
            )

        format_version = payload[0]

        if format_version != PAYLOAD_FORMAT_VERSION:
            raise CryptoDecryptionError(
                "Unsupported encrypted payload format."
            )

        nonce_start = 1
        nonce_end = (
            nonce_start
            + AES_GCM_NONCE_SIZE_BYTES
        )

        nonce = payload[
            nonce_start:nonce_end
        ]

        ciphertext = payload[
            nonce_end:
        ]

        key = _get_encryption_key(
            key_version
        )

        aesgcm = AESGCM(key)

        try:
            return aesgcm.decrypt(
                nonce,
                ciphertext,
                _aad_bytes(aad),
            )
        except InvalidTag as exc:
            raise CryptoDecryptionError(
                "Encrypted payload authentication failed."
            ) from exc

    @classmethod
    def encrypt_text(
        cls,
        plaintext: str,
        *,
        aad: str | bytes,
        key_version: int | None = None,
    ) -> EncryptedPayload:
        if not isinstance(plaintext, str):
            raise TypeError(
                "plaintext must be str."
            )

        return cls.encrypt_bytes(
            plaintext.encode("utf-8"),
            aad=aad,
            key_version=key_version,
        )

    @classmethod
    def decrypt_text(
        cls,
        payload: bytes,
        *,
        aad: str | bytes,
        key_version: int,
    ) -> str:
        plaintext = cls.decrypt_bytes(
            payload,
            aad=aad,
            key_version=key_version,
        )

        try:
            return plaintext.decode(
                "utf-8"
            )
        except UnicodeDecodeError as exc:
            raise CryptoDecryptionError(
                "Decrypted payload is not valid UTF-8."
            ) from exc

    @classmethod
    def lookup_hash(
        cls,
        value: str | bytes,
        *,
        key_version: int | None = None,
    ) -> LookupDigest:
        """
        Generate HMAC-SHA-256 hexadecimal lookup digest.

        IMPORTANT:
        This method deliberately does not normalize values.
        Domain services must canonicalize identifiers/emails
        before calling it.
        """

        if key_version is None:
            key_version = (
                settings.LOOKUP_HMAC_ACTIVE_VERSION
            )

        key = _get_lookup_key(
            key_version
        )

        if isinstance(value, str):
            value_bytes = value.encode(
                "utf-8"
            )
        elif isinstance(value, bytes):
            value_bytes = value
        else:
            raise TypeError(
                "value must be str or bytes."
            )

        digest = hmac.new(
            key,
            value_bytes,
            hashlib.sha256,
        ).hexdigest()

        return LookupDigest(
            value=digest,
            key_version=key_version,
        )