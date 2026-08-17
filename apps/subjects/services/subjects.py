import uuid
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services.crypto import CryptoService
from apps.subjects.models import (
    DataSubject,
    SubjectRepresentative,
)
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


class RepresentativeAlreadyExistsError(
    SubjectServiceError
):
    def __init__(self, representative_id):
        self.representative_id = representative_id

        super().__init__(
            f"Representative already exists: "
            f"{representative_id}"
        )


class RepresentativeVerificationStateError(
    SubjectServiceError
):
    def __init__(
        self,
        representative_id,
        current_status,
        target_status,
    ):
        self.representative_id = representative_id
        self.current_status = current_status
        self.target_status = target_status

        super().__init__(
            f"Invalid representative verification transition "
            f"for {representative_id}: "
            f"{current_status} -> {target_status}"
        )


class RepresentativeVerificationActorError(
    SubjectServiceError
):
    def __init__(self, actor_id=None):
        self.actor_id = actor_id

        super().__init__(
            "Representative verification requires "
            "an active persisted user."
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


@dataclass(frozen=True)
class RepresentativePII:
    id: uuid.UUID
    data_subject_id: uuid.UUID
    representative_name: str
    representative_document_type: str
    representative_document_number: str
    representative_email: str | None
    verification_status: str


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


def _representative_lookup_material(
    *,
    data_subject_id: uuid.UUID,
    document_type: str,
    document_number: str,
) -> str:
    return (
        f"representative:"
        f"{data_subject_id}:"
        f"{document_type}:"
        f"{document_number}"
    )


def _representative_aad(
    representative_id: uuid.UUID,
    field_name: str,
) -> str:
    return (
        f"subject_representatives:"
        f"{representative_id}:"
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


class RepresentativeService:

    @classmethod
    def _document_hashes_for_all_keys(
        cls,
        *,
        data_subject_id: uuid.UUID,
        document_type: str,
        document_number: str,
    ) -> list[str]:
        material = _representative_lookup_material(
            data_subject_id=data_subject_id,
            document_type=document_type,
            document_number=document_number,
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
        data_subject: DataSubject,
        document_type: str,
        document_number: str,
    ) -> SubjectRepresentative | None:
        document_type = _validate_choice(
            SubjectRepresentative,
            "representative_document_type",
            document_type,
        )

        document_number = normalize_document_number(
            document_type,
            document_number,
        )

        hashes = cls._document_hashes_for_all_keys(
            data_subject_id=data_subject.id,
            document_type=document_type,
            document_number=document_number,
        )

        return (
            SubjectRepresentative.objects
            .filter(
                data_subject=data_subject,
                representative_document_lookup_hash__in=hashes,
            )
            .first()
        )

    @classmethod
    def create(
        cls,
        *,
        data_subject: DataSubject,
        representative_name: str,
        representative_document_type: str,
        representative_document_number: str,
        representative_email: str | None = None,
    ) -> SubjectRepresentative:
        document_type = _validate_choice(
            SubjectRepresentative,
            "representative_document_type",
            representative_document_type,
        )

        document_number = normalize_document_number(
            document_type,
            representative_document_number,
        )

        representative_name = normalize_full_name(
            representative_name
        )

        if (
            representative_email is not None
            and representative_email.strip()
        ):
            representative_email = normalize_email(
                representative_email
            )
        else:
            representative_email = None

        existing = cls.find_by_document(
            data_subject=data_subject,
            document_type=document_type,
            document_number=document_number,
        )

        if existing is not None:
            raise RepresentativeAlreadyExistsError(
                existing.id
            )

        representative_id = uuid.uuid4()

        encryption_version = (
            settings.PII_ENCRYPTION_ACTIVE_VERSION
        )

        lookup_version = (
            settings.LOOKUP_HMAC_ACTIVE_VERSION
        )

        document_hash = CryptoService.lookup_hash(
            _representative_lookup_material(
                data_subject_id=data_subject.id,
                document_type=document_type,
                document_number=document_number,
            ),
            key_version=lookup_version,
        )

        encrypted_name = CryptoService.encrypt_text(
            representative_name,
            aad=_representative_aad(
                representative_id,
                "representative_name",
            ),
            key_version=encryption_version,
        )

        encrypted_document = CryptoService.encrypt_text(
            document_number,
            aad=_representative_aad(
                representative_id,
                "representative_document",
            ),
            key_version=encryption_version,
        )

        encrypted_email = None

        if representative_email is not None:
            encrypted_email = CryptoService.encrypt_text(
                representative_email,
                aad=_representative_aad(
                    representative_id,
                    "representative_email",
                ),
                key_version=encryption_version,
            )

        try:
            with transaction.atomic():
                return SubjectRepresentative.objects.create(
                    id=representative_id,
                    data_subject=data_subject,

                    representative_name_encrypted=(
                        encrypted_name.data
                    ),

                    representative_document_type=(
                        document_type
                    ),

                    representative_document_encrypted=(
                        encrypted_document.data
                    ),

                    representative_document_lookup_hash=(
                        document_hash.value
                    ),

                    representative_email_encrypted=(
                        encrypted_email.data
                        if encrypted_email
                        else None
                    ),

                    encryption_key_version=(
                        encryption_version
                    ),

                    lookup_key_version=(
                        lookup_version
                    ),

                    verification_status="PENDING",
                )

        except IntegrityError as exc:
            existing = cls.find_by_document(
                data_subject=data_subject,
                document_type=document_type,
                document_number=document_number,
            )

            if existing is not None:
                raise RepresentativeAlreadyExistsError(
                    existing.id
                ) from exc

            raise

    @classmethod
    def decrypt(
        cls,
        representative: SubjectRepresentative,
    ) -> RepresentativePII:
        name = CryptoService.decrypt_text(
            representative.representative_name_encrypted,
            aad=_representative_aad(
                representative.id,
                "representative_name",
            ),
            key_version=(
                representative.encryption_key_version
            ),
        )

        document = CryptoService.decrypt_text(
            representative.representative_document_encrypted,
            aad=_representative_aad(
                representative.id,
                "representative_document",
            ),
            key_version=(
                representative.encryption_key_version
            ),
        )

        email = None

        if representative.representative_email_encrypted:
            email = CryptoService.decrypt_text(
                representative.representative_email_encrypted,
                aad=_representative_aad(
                    representative.id,
                    "representative_email",
                ),
                key_version=(
                    representative.encryption_key_version
                ),
            )

        return RepresentativePII(
            id=representative.id,
            data_subject_id=(
                representative.data_subject_id
            ),
            representative_name=name,
            representative_document_type=(
                representative
                .representative_document_type
            ),
            representative_document_number=document,
            representative_email=email,
            verification_status=(
                representative.verification_status
            ),
        )

    @classmethod
    def _validate_verification_actor(
        cls,
        actor,
    ) -> None:
        actor_id = getattr(
            actor,
            "pk",
            None,
        )

        if actor_id is None:
            raise RepresentativeVerificationActorError()

        user_model = get_user_model()

        actor_is_active = (
            user_model.objects
            .filter(
                pk=actor_id,
                is_active=True,
            )
            .exists()
        )

        if not actor_is_active:
            raise RepresentativeVerificationActorError(
                actor_id
            )

    @classmethod
    def _set_verification_status(
        cls,
        *,
        representative: SubjectRepresentative,
        actor,
        target_status: str,
    ) -> SubjectRepresentative:
        cls._validate_verification_actor(
            actor
        )

        allowed_targets = {
            SubjectRepresentative
            .VerificationStatus
            .VERIFIED,

            SubjectRepresentative
            .VerificationStatus
            .REJECTED,
        }

        if target_status not in allowed_targets:
            raise ValueError(
                f"Invalid representative "
                f"verification target: "
                f"{target_status}"
            )

        with transaction.atomic():
            locked_representative = (
                SubjectRepresentative.objects
                .select_for_update()
                .get(
                    pk=representative.pk
                )
            )

            current_status = (
                locked_representative
                .verification_status
            )

            if (
                current_status
                != SubjectRepresentative
                .VerificationStatus
                .PENDING
            ):
                raise (
                    RepresentativeVerificationStateError(
                        locked_representative.id,
                        current_status,
                        target_status,
                    )
                )

            locked_representative.verification_status = (
                target_status
            )

            locked_representative.verified_by = (
                actor
            )

            locked_representative.verified_at = (
                timezone.now()
            )

            locked_representative.save(
                update_fields=[
                    "verification_status",
                    "verified_by",
                    "verified_at",
                ]
            )

            return locked_representative

    @classmethod
    def verify(
        cls,
        *,
        representative: SubjectRepresentative,
        actor,
    ) -> SubjectRepresentative:
        return cls._set_verification_status(
            representative=representative,
            actor=actor,
            target_status=(
                SubjectRepresentative
                .VerificationStatus
                .VERIFIED
            ),
        )

    @classmethod
    def reject(
        cls,
        *,
        representative: SubjectRepresentative,
        actor,
    ) -> SubjectRepresentative:
        return cls._set_verification_status(
            representative=representative,
            actor=actor,
            target_status=(
                SubjectRepresentative
                .VerificationStatus
                .REJECTED
            ),
        )    