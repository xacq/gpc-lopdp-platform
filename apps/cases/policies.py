from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import Role
from apps.cases.models import RightsRequest


FULL_READ_ROLE_CODES = {
    Role.Code.ADMIN,
    Role.Code.DPD,
    Role.Code.RESPONSABLE,
    Role.Code.AUDITOR,
}

SENSITIVE_READ_ROLE_CODES = {
    Role.Code.ADMIN,
    Role.Code.DPD,
    Role.Code.RESPONSABLE,
}

MANAGER_ROLE_CODES = {
    Role.Code.ADMIN,
    Role.Code.DPD,
    Role.Code.RESPONSABLE,
}

PANEL_ROLE_CODES = {
    Role.Code.ADMIN,
    Role.Code.DPD,
    Role.Code.RESPONSABLE,
    Role.Code.OPERADOR,
    Role.Code.AUDITOR,
}


def active_role_codes(user) -> set[str]:
    if (
        user is None
        or not getattr(
            user,
            "is_authenticated",
            False,
        )
        or not getattr(
            user,
            "is_active",
            False,
        )
    ):
        return set()

    return set(
        user.role_assignments
        .filter(
            revoked_at__isnull=True,
            role__is_active=True,
        )
        .values_list(
            "role__code",
            flat=True,
        )
    )


def _is_active_superuser(user) -> bool:
    return bool(
        getattr(
            user,
            "is_active",
            False,
        )
        and getattr(
            user,
            "is_superuser",
            False,
        )
    )


def can_access_case_panel(user) -> bool:
    if _is_active_superuser(user):
        return True

    return bool(
        active_role_codes(user)
        & PANEL_ROLE_CODES
    )


def visible_requests_for(
    user,
    queryset: QuerySet | None = None,
) -> QuerySet:
    if queryset is None:
        queryset = (
            RightsRequest.objects.all()
        )

    if _is_active_superuser(user):
        return queryset

    role_codes = active_role_codes(
        user
    )

    if role_codes & FULL_READ_ROLE_CODES:
        return queryset

    if (
        Role.Code.OPERADOR
        in role_codes
    ):
        return queryset.filter(
            assigned_to_id=user.pk
        )

    return queryset.none()


def can_view_sensitive_case_data(
    user,
    request: RightsRequest,
) -> bool:
    if _is_active_superuser(user):
        return True

    role_codes = active_role_codes(
        user
    )

    if (
        role_codes
        & SENSITIVE_READ_ROLE_CODES
    ):
        return True

    return (
        Role.Code.OPERADOR
        in role_codes
        and request.assigned_to_id
        == user.pk
    )


def can_create_case(user) -> bool:
    if _is_active_superuser(user):
        return True

    return bool(
        active_role_codes(user)
        & MANAGER_ROLE_CODES
    )


def can_assign_case(user) -> bool:
    return can_create_case(user)


def can_start_review(
    user,
    request: RightsRequest,
) -> bool:
    if _is_active_superuser(user):
        return True

    role_codes = active_role_codes(
        user
    )

    if role_codes & MANAGER_ROLE_CODES:
        return True

    return (
        Role.Code.OPERADOR
        in role_codes
        and request.assigned_to_id
        == user.pk
    )
