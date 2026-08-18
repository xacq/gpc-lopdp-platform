from __future__ import annotations

from apps.accounts.models import Role


def can_manage_users(user) -> bool:
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False

    if getattr(user, "is_superuser", False):
        return True

    return user.role_assignments.filter(
        role__code=Role.Code.ADMIN,
        role__is_active=True,
        revoked_at__isnull=True,
    ).exists()
