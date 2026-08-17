from __future__ import annotations

import base64
import os
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.ciphers.aead import (
    AESGCM,
)
from django.conf import settings


class PrivateStorageError(Exception):
    pass


class StorageConfigurationError(
    PrivateStorageError
):
    pass


class UnsafeStorageKeyError(
    PrivateStorageError
):
    pass


class StorageObjectNotFoundError(
    PrivateStorageError
):
    pass


class LocalPrivateStorageService:
    FORMAT_VERSION = 1
    NONCE_SIZE = 12

    @classmethod
    def _root(cls) -> Path:
        configured = getattr(
            settings,
            "PRIVATE_STORAGE_ROOT",
            None,
        )

        if not configured:
            raise StorageConfigurationError(
                "PRIVATE_STORAGE_ROOT is required."
            )

        root = Path(
            configured
        ).expanduser().resolve()

        forbidden_roots = []

        for setting_name in (
            "MEDIA_ROOT",
            "STATIC_ROOT",
        ):
            value = getattr(
                settings,
                setting_name,
                None,
            )

            if value:
                forbidden_roots.append(
                    Path(value)
                    .expanduser()
                    .resolve()
                )

        for forbidden in forbidden_roots:
            try:
                root.relative_to(forbidden)
            except ValueError:
                continue

            raise StorageConfigurationError(
                "Private storage cannot be "
                "inside MEDIA_ROOT or STATIC_ROOT."
            )

        root.mkdir(
            parents=True,
            exist_ok=True,
        )

        return root

    @classmethod
    def _normalize_key(
        cls,
        storage_key: str,
    ) -> str:
        if not isinstance(
            storage_key,
            str,
        ):
            raise UnsafeStorageKeyError(
                "Invalid storage key."
            )

        storage_key = (
            storage_key
            .strip()
            .replace("\\", "/")
        )

        if not storage_key:
            raise UnsafeStorageKeyError(
                "Invalid storage key."
            )

        pure = PurePosixPath(
            storage_key
        )

        if (
            pure.is_absolute()
            or ".." in pure.parts
            or "." in pure.parts
        ):
            raise UnsafeStorageKeyError(
                "Invalid storage key."
            )

        return str(pure)

    @classmethod
    def _path(
        cls,
        storage_key: str,
    ) -> Path:
        storage_key = cls._normalize_key(
            storage_key
        )

        root = cls._root()
        path = (
            root / storage_key
        ).resolve()

        try:
            path.relative_to(root)
        except ValueError as exc:
            raise UnsafeStorageKeyError(
                "Invalid storage key."
            ) from exc

        return path

    @classmethod
    def _key(
        cls,
        *,
        key_version: int,
    ) -> bytes:
        keys = getattr(
            settings,
            "PII_ENCRYPTION_KEYS",
            {},
        )

        encoded = keys.get(
            key_version
        )

        if not encoded:
            raise StorageConfigurationError(
                "Encryption key version "
                f"{key_version} is not configured."
            )

        try:
            raw = base64.b64decode(
                encoded,
                validate=True,
            )
        except Exception as exc:
            raise StorageConfigurationError(
                "Invalid encryption key encoding."
            ) from exc

        if len(raw) != 32:
            raise StorageConfigurationError(
                "AES-256-GCM requires "
                "a 32-byte key."
            )

        return raw

    @classmethod
    def _aad(
        cls,
        storage_key: str,
    ) -> bytes:
        return (
            "private_storage:"
            f"{storage_key}"
        ).encode("utf-8")

    @classmethod
    def encrypt_bytes(
        cls,
        *,
        storage_key: str,
        plaintext: bytes,
        key_version: int,
    ) -> bytes:
        storage_key = cls._normalize_key(
            storage_key
        )

        if not isinstance(
            plaintext,
            bytes,
        ):
            raise TypeError(
                "plaintext must be bytes."
            )

        if not (
            1 <= key_version <= 255
        ):
            raise StorageConfigurationError(
                "Storage envelope supports "
                "key versions 1..255."
            )

        nonce = os.urandom(
            cls.NONCE_SIZE
        )

        ciphertext = AESGCM(
            cls._key(
                key_version=key_version
            )
        ).encrypt(
            nonce,
            plaintext,
            cls._aad(storage_key),
        )

        return (
            bytes([
                cls.FORMAT_VERSION
            ])
            + bytes([key_version])
            + nonce
            + ciphertext
        )

    @classmethod
    def decrypt_bytes(
        cls,
        *,
        storage_key: str,
        envelope: bytes,
        expected_key_version: (
            int | None
        ) = None,
    ) -> bytes:
        storage_key = cls._normalize_key(
            storage_key
        )

        minimum_length = (
            2
            + cls.NONCE_SIZE
            + 16
        )

        if len(envelope) < minimum_length:
            raise PrivateStorageError(
                "Invalid encrypted storage object."
            )

        format_version = envelope[0]
        key_version = envelope[1]

        if (
            format_version
            != cls.FORMAT_VERSION
        ):
            raise PrivateStorageError(
                "Unsupported storage "
                "envelope version."
            )

        if (
            expected_key_version
            is not None
            and key_version
            != expected_key_version
        ):
            raise PrivateStorageError(
                "Storage key version mismatch."
            )

        nonce_start = 2
        nonce_end = (
            nonce_start
            + cls.NONCE_SIZE
        )

        nonce = envelope[
            nonce_start:nonce_end
        ]
        ciphertext = envelope[
            nonce_end:
        ]

        try:
            return AESGCM(
                cls._key(
                    key_version=key_version
                )
            ).decrypt(
                nonce,
                ciphertext,
                cls._aad(storage_key),
            )
        except Exception as exc:
            raise PrivateStorageError(
                "Encrypted storage object "
                "failed authentication."
            ) from exc

    @classmethod
    def write_encrypted(
        cls,
        *,
        storage_key: str,
        plaintext: bytes,
        key_version: int,
    ) -> None:
        path = cls._path(
            storage_key
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if path.exists():
            raise PrivateStorageError(
                "Storage object already exists."
            )

        envelope = cls.encrypt_bytes(
            storage_key=storage_key,
            plaintext=plaintext,
            key_version=key_version,
        )

        temporary = path.with_name(
            f".{path.name}.tmp"
        )

        try:
            with open(
                temporary,
                "xb",
            ) as handle:
                handle.write(envelope)

            os.replace(
                temporary,
                path,
            )
        finally:
            if temporary.exists():
                temporary.unlink(
                    missing_ok=True
                )

    @classmethod
    def read_encrypted(
        cls,
        *,
        storage_key: str,
        key_version: int,
    ) -> bytes:
        path = cls._path(
            storage_key
        )

        if not path.is_file():
            raise StorageObjectNotFoundError(
                "Storage object not found."
            )

        envelope = path.read_bytes()

        return cls.decrypt_bytes(
            storage_key=storage_key,
            envelope=envelope,
            expected_key_version=(
                key_version
            ),
        )

    @classmethod
    def delete(
        cls,
        *,
        storage_key: str,
    ) -> None:
        path = cls._path(
            storage_key
        )

        path.unlink(
            missing_ok=True
        )

    @classmethod
    def exists(
        cls,
        *,
        storage_key: str,
    ) -> bool:
        return cls._path(
            storage_key
        ).is_file()
