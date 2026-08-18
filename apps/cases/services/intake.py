from __future__ import annotations

from django.db import transaction

from apps.cases.models import RightsRequest
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.legal_content.models import RightCatalog
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
from apps.subjects.services.subjects import (
    RepresentativeAlreadyExistsError,
    RepresentativeService,
    SubjectAlreadyExistsError,
    SubjectService,
)


class CaseIntakeError(Exception):
    pass


class ExistingSubjectDataMismatchError(
    CaseIntakeError
):
    def __init__(self, fields):
        self.fields = tuple(fields)
        super().__init__(
            "Existing subject data does not "
            "match the submitted intake."
        )


class ExistingRepresentativeDataMismatchError(
    CaseIntakeError
):
    def __init__(self, fields):
        self.fields = tuple(fields)
        super().__init__(
            "Existing representative data does "
            "not match the submitted intake."
        )


class CaseIntakeService:
    @classmethod
    def _normalize_subject_input(
        cls,
        *,
        subject_type: str,
        document_type: str,
        document_number: str,
        full_name: str,
        email: str,
        phone: str | None,
    ) -> dict:
        subject_type = (
            str(subject_type)
            .strip()
            .upper()
        )

        document_type = (
            str(document_type)
            .strip()
            .upper()
        )

        if (
            subject_type
            not in DataSubject
            .SubjectType
            .values
        ):
            raise ValueError(
                "Invalid subject_type."
            )

        if (
            document_type
            not in DataSubject
            .DocumentType
            .values
        ):
            raise ValueError(
                "Invalid document_type."
            )

        return {
            "subject_type": subject_type,
            "document_type": document_type,
            "document_number": (
                normalize_document_number(
                    document_type,
                    document_number,
                )
            ),
            "full_name": (
                normalize_full_name(
                    full_name
                )
            ),
            "email": normalize_email(
                email
            ),
            "phone": normalize_phone(
                phone
            ),
        }

    @classmethod
    def _subject_mismatches(
        cls,
        *,
        existing: DataSubject,
        normalized: dict,
    ) -> list[str]:
        pii = SubjectService.decrypt(
            existing
        )

        mismatches = []

        if (
            pii.subject_type
            != normalized[
                "subject_type"
            ]
        ):
            mismatches.append(
                "subject_type"
            )

        if (
            pii.full_name
            != normalized[
                "full_name"
            ]
        ):
            mismatches.append(
                "full_name"
            )

        if (
            pii.email
            != normalized["email"]
        ):
            mismatches.append(
                "email"
            )

        submitted_phone = (
            normalized["phone"]
        )

        if (
            submitted_phone is not None
            and pii.phone
            != submitted_phone
        ):
            mismatches.append(
                "phone"
            )

        return mismatches

    @classmethod
    def _get_or_create_subject(
        cls,
        *,
        normalized: dict,
    ) -> DataSubject:
        existing = (
            SubjectService
            .find_by_document(
                document_type=(
                    normalized[
                        "document_type"
                    ]
                ),
                document_number=(
                    normalized[
                        "document_number"
                    ]
                ),
            )
        )

        if existing is None:
            try:
                return SubjectService.create(
                    subject_type=(
                        normalized[
                            "subject_type"
                        ]
                    ),
                    document_type=(
                        normalized[
                            "document_type"
                        ]
                    ),
                    document_number=(
                        normalized[
                            "document_number"
                        ]
                    ),
                    full_name=(
                        normalized[
                            "full_name"
                        ]
                    ),
                    email=(
                        normalized[
                            "email"
                        ]
                    ),
                    phone=(
                        normalized[
                            "phone"
                        ]
                    ),
                )
            except SubjectAlreadyExistsError:
                existing = (
                    SubjectService
                    .find_by_document(
                        document_type=(
                            normalized[
                                "document_type"
                            ]
                        ),
                        document_number=(
                            normalized[
                                "document_number"
                            ]
                        ),
                    )
                )

                if existing is None:
                    raise

        mismatches = (
            cls._subject_mismatches(
                existing=existing,
                normalized=normalized,
            )
        )

        if mismatches:
            raise (
                ExistingSubjectDataMismatchError(
                    mismatches
                )
            )

        return existing

    @classmethod
    def _normalize_representative_input(
        cls,
        *,
        representative_name: str,
        representative_document_type: str,
        representative_document_number: str,
        representative_email: (
            str | None
        ),
    ) -> dict:
        document_type = (
            str(
                representative_document_type
            )
            .strip()
            .upper()
        )

        if (
            document_type
            not in SubjectRepresentative
            .DocumentType
            .values
        ):
            raise ValueError(
                "Invalid representative "
                "document type."
            )

        if (
            representative_email
            is not None
            and representative_email
            .strip()
        ):
            normalized_email = (
                normalize_email(
                    representative_email
                )
            )
        else:
            normalized_email = None

        return {
            "representative_name": (
                normalize_full_name(
                    representative_name
                )
            ),
            "document_type": (
                document_type
            ),
            "document_number": (
                normalize_document_number(
                    document_type,
                    representative_document_number,
                )
            ),
            "email": normalized_email,
        }

    @classmethod
    def _representative_mismatches(
        cls,
        *,
        existing: SubjectRepresentative,
        normalized: dict,
    ) -> list[str]:
        pii = (
            RepresentativeService
            .decrypt(
                existing
            )
        )

        mismatches = []

        if (
            pii.representative_name
            != normalized[
                "representative_name"
            ]
        ):
            mismatches.append(
                "representative_name"
            )

        submitted_email = (
            normalized["email"]
        )

        if (
            submitted_email is not None
            and pii.representative_email
            != submitted_email
        ):
            mismatches.append(
                "representative_email"
            )

        return mismatches

    @classmethod
    def _get_or_create_representative(
        cls,
        *,
        data_subject: DataSubject,
        normalized: dict,
    ) -> SubjectRepresentative:
        existing = (
            RepresentativeService
            .find_by_document(
                data_subject=(
                    data_subject
                ),
                document_type=(
                    normalized[
                        "document_type"
                    ]
                ),
                document_number=(
                    normalized[
                        "document_number"
                    ]
                ),
            )
        )

        if existing is None:
            try:
                return (
                    RepresentativeService
                    .create(
                        data_subject=(
                            data_subject
                        ),
                        representative_name=(
                            normalized[
                                "representative_name"
                            ]
                        ),
                        representative_document_type=(
                            normalized[
                                "document_type"
                            ]
                        ),
                        representative_document_number=(
                            normalized[
                                "document_number"
                            ]
                        ),
                        representative_email=(
                            normalized[
                                "email"
                            ]
                        ),
                    )
                )
            except (
                RepresentativeAlreadyExistsError
            ):
                existing = (
                    RepresentativeService
                    .find_by_document(
                        data_subject=(
                            data_subject
                        ),
                        document_type=(
                            normalized[
                                "document_type"
                            ]
                        ),
                        document_number=(
                            normalized[
                                "document_number"
                            ]
                        ),
                    )
                )

                if existing is None:
                    raise

        mismatches = (
            cls._representative_mismatches(
                existing=existing,
                normalized=normalized,
            )
        )

        if mismatches:
            raise (
                ExistingRepresentativeDataMismatchError(
                    mismatches
                )
            )

        return existing

    @classmethod
    def create_administrative_request(
        cls,
        *,
        subject_type: str,
        document_type: str,
        document_number: str,
        full_name: str,
        email: str,
        phone: str | None,
        right: RightCatalog,
        request_details: str,
        source_channel: str,
        actor,
        representative_name: (
            str | None
        ) = None,
        representative_document_type: (
            str | None
        ) = None,
        representative_document_number: (
            str | None
        ) = None,
        representative_email: (
            str | None
        ) = None,
    ) -> RightsRequest:
        normalized_subject = (
            cls._normalize_subject_input(
                subject_type=subject_type,
                document_type=(
                    document_type
                ),
                document_number=(
                    document_number
                ),
                full_name=full_name,
                email=email,
                phone=phone,
            )
        )

        representative_values = [
            representative_name,
            representative_document_type,
            representative_document_number,
            representative_email,
        ]

        wants_representative = any(
            value is not None
            and str(value).strip()
            for value in (
                representative_values
            )
        )

        normalized_representative = None

        if wants_representative:
            required_values = [
                representative_name,
                representative_document_type,
                representative_document_number,
            ]

            if not all(
                value is not None
                and str(value).strip()
                for value in required_values
            ):
                raise ValueError(
                    "Representative name, "
                    "document type and document "
                    "number are required together."
                )

            normalized_representative = (
                cls
                ._normalize_representative_input(
                    representative_name=(
                        representative_name
                    ),
                    representative_document_type=(
                        representative_document_type
                    ),
                    representative_document_number=(
                        representative_document_number
                    ),
                    representative_email=(
                        representative_email
                    ),
                )
            )

        with transaction.atomic():
            data_subject = (
                cls._get_or_create_subject(
                    normalized=(
                        normalized_subject
                    )
                )
            )

            representative = None

            if (
                normalized_representative
                is not None
            ):
                representative = (
                    cls
                    ._get_or_create_representative(
                        data_subject=(
                            data_subject
                        ),
                        normalized=(
                            normalized_representative
                        ),
                    )
                )

            return (
                CaseWorkflowService
                .create_request(
                    data_subject=(
                        data_subject
                    ),
                    right=right,
                    request_details=(
                        request_details
                    ),
                    representative=(
                        representative
                    ),
                    source_channel=(
                        source_channel
                    ),
                    actor=actor,
                )
            )
