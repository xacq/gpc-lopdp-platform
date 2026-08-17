import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.core.services.crypto import CryptoService
from apps.subjects.models import DataSubject
from apps.subjects.services.normalization import (
    normalize_document_number,
    normalize_email,
    normalize_full_name,
    normalize_phone,
)


class SubjectServiceError(Exception):
    pass


class SubjectAlreadyExistsError(
    SubjectServiceError
):
    def __init__(self, subject_id):
        self.subject_id = subject_id
        super().__init__(
            f"Data subject already exists: "
            f"{subject_id}"
        )


@dataclass(frozen=True)
class SubjectPII:
    id: uuid.UUID
    subject_type: str
    document_type: str
    document_number: str
    full_name: str
    email: str
    phone: str | None


def _validate_choice(
    model,
    field_name: str,
    value: str,
) -> str:
    value = value.strip().upper()

    field = model._meta.get_field(
        field_name
    )

    valid_values = {
        choice[0]
        for choice in field.choices
    }

    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name}: {value}"
        )

    return value


def _document_lookup_material(
    document_type: str,
    document_number: str,
) -> str:
    return (
        f"document:"
        f"{document_type}:"
        f"{document_number}"
    )


def _email_lookup_material(
    email: str,
) -> str:
    return f"email:{email}"


def _subject_aad(
    subject_id: uuid.UUID,
    field_name: str,
) -> str:
    return (
        f"data_subjects:"
        f"{subject_id}:"
        f"{field_name}"
    )


class SubjectService:

    @classmethod
    def _document_hashes_for_all_keys(
        cls,
        *,
        document_type: str,
        document_number: str,
    ) -> list[str]:
        material = _document_lookup_material(
            document_type,
            document_number,
        )

        hashes = []

        for version, encoded_key in (
            settings.LOOKUP_HMAC_KEYS.items()
        ):
            if not encoded_key:
                continue

            digest = CryptoService.lookup_hash(
                material,
                key_version=version,
            )

            hashes.append(digest.value)

        if not hashes:
            raise SubjectServiceError(
                "No lookup HMAC keys configured."
            )

        return hashes

    @classmethod
    def find_by_document(
        cls,
        *,
        document_type: str,
        document_number: str,
    ) -> DataSubject | None:
        document_type = _validate_choice(
            DataSubject,
            "document_type",
            document_type,
        )

        document_number = (
            normalize_document_number(
                document_type,
                document_number,
            )
        )

        hashes = (
            cls._document_hashes_for_all_keys(
                document_type=document_type,
                document_number=document_number,
            )
        )

        return (
            DataSubject.objects
            .filter(
                document_number_lookup_hash__in=hashes
            )
            .first()
        )

    @classmethod
    def create(
        cls,
        *,
        subject_type: str,
        document_type: str,
        document_number: str,
        full_name: str,
        email: str,
        phone: str | None = None,
    ) -> DataSubject:
        subject_type = _validate_choice(
            DataSubject,
            "subject_type",
            subject_type,
        )

        document_type = _validate_choice(
            DataSubject,
            "document_type",
            document_type,
        )

        document_number = (
            normalize_document_number(
                document_type,
                document_number,
            )
        )

        full_name = normalize_full_name(
            full_name
        )

        email = normalize_email(
            email
        )

        phone = normalize_phone(
            phone
        )

        existing = cls.find_by_document(
            document_type=document_type,
            document_number=document_number,
        )

        if existing is not None:
            raise SubjectAlreadyExistsError(
                existing.id
            )

        subject_id = uuid.uuid4()

        encryption_version = (
            settings
            .PII_ENCRYPTION_ACTIVE_VERSION
        )

        lookup_version = (
            settings
            .LOOKUP_HMAC_ACTIVE_VERSION
        )

        document_hash = (
            CryptoService.lookup_hash(
                _document_lookup_material(
                    document_type,
                    document_number,
                ),
                key_version=lookup_version,
            )
        )

        email_hash = CryptoService.lookup_hash(
            _email_lookup_material(
                email
            ),
            key_version=lookup_version,
        )

        encrypted_document = (
            CryptoService.encrypt_text(
                document_number,
                aad=_subject_aad(
                    subject_id,
                    "document_number",
                ),
                key_version=encryption_version,
            )
        )

        encrypted_name = (
            CryptoService.encrypt_text(
                full_name,
                aad=_subject_aad(
                    subject_id,
                    "full_name",
                ),
                key_version=encryption_version,
            )
        )

        encrypted_email = (
            CryptoService.encrypt_text(
                email,
                aad=_subject_aad(
                    subject_id,
                    "email",
                ),
                key_version=encryption_version,
            )
        )

        encrypted_phone = None

        if phone is not None:
            encrypted_phone = (
                CryptoService.encrypt_text(
                    phone,
                    aad=_subject_aad(
                        subject_id,
                        "phone",
                    ),
                    key_version=(
                        encryption_version
                    ),
                )
            )

        try:
            with transaction.atomic():
                return DataSubject.objects.create(
                    id=subject_id,
                    subject_type=subject_type,
                    document_type=document_type,

                    document_number_encrypted=(
                        encrypted_document.data
                    ),
                    document_number_lookup_hash=(
                        document_hash.value
                    ),

                    full_name_encrypted=(
                        encrypted_name.data
                    ),

                    email_encrypted=(
                        encrypted_email.data
                    ),
                    email_lookup_hash=(
                        email_hash.value
                    ),

                    phone_encrypted=(
                        encrypted_phone.data
                        if encrypted_phone
                        else None
                    ),

                    encryption_key_version=(
                        encryption_version
                    ),
                    lookup_key_version=(
                        lookup_version
                    ),
                )

        except IntegrityError as exc:
            existing = cls.find_by_document(
                document_type=document_type,
                document_number=document_number,
            )

            if existing is not None:
                raise SubjectAlreadyExistsError(
                    existing.id
                ) from exc

            raise

    @classmethod
    def decrypt(
        cls,
        subject: DataSubject,
    ) -> SubjectPII:
        document_number = (
            CryptoService.decrypt_text(
                subject.document_number_encrypted,
                aad=_subject_aad(
                    subject.id,
                    "document_number",
                ),
                key_version=(
                    subject.encryption_key_version
                ),
            )
        )

        full_name = CryptoService.decrypt_text(
            subject.full_name_encrypted,
            aad=_subject_aad(
                subject.id,
                "full_name",
            ),
            key_version=(
                subject.encryption_key_version
            ),
        )

        email = CryptoService.decrypt_text(
            subject.email_encrypted,
            aad=_subject_aad(
                subject.id,
                "email",
            ),
            key_version=(
                subject.encryption_key_version
            ),
        )

        phone = None

        if subject.phone_encrypted:
            phone = CryptoService.decrypt_text(
                subject.phone_encrypted,
                aad=_subject_aad(
                    subject.id,
                    "phone",
                ),
                key_version=(
                    subject.encryption_key_version
                ),
            )

        return SubjectPII(
            id=subject.id,
            subject_type=subject.subject_type,
            document_type=(
                subject.document_type
            ),
            document_number=(
                document_number
            ),
            full_name=full_name,
            email=email,
            phone=phone,
        )