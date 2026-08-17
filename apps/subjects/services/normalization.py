import re
import unicodedata


class NormalizationError(ValueError):
    pass


def normalize_document_number(
    document_type: str,
    value: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError("document number must be str.")

    document_type = document_type.strip().upper()
    value = unicodedata.normalize("NFKC", value).strip()

    if document_type in {"CEDULA", "RUC"}:
        normalized = re.sub(r"\D", "", value)
    else:
        normalized = " ".join(value.split()).upper()

    if not normalized:
        raise NormalizationError(
            "document number cannot be empty."
        )

    return normalized


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("email must be str.")

    normalized = unicodedata.normalize(
        "NFKC",
        value,
    ).strip().casefold()

    if not normalized or "@" not in normalized:
        raise NormalizationError(
            "invalid email."
        )

    return normalized


def normalize_full_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("full name must be str.")

    normalized = unicodedata.normalize(
        "NFKC",
        value,
    )

    normalized = " ".join(
        normalized.strip().split()
    )

    if not normalized:
        raise NormalizationError(
            "full name cannot be empty."
        )

    return normalized


def normalize_phone(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError("phone must be str or None.")

    value = unicodedata.normalize(
        "NFKC",
        value,
    ).strip()

    if not value:
        return None

    has_plus = value.startswith("+")
    digits = re.sub(r"\D", "", value)

    if not digits:
        raise NormalizationError(
            "invalid phone."
        )

    return (
        f"+{digits}"
        if has_plus
        else digits
    )