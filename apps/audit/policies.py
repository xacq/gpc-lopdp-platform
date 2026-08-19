from apps.accounts.models import Role


AUDIT_READER_ROLE_CODES = {
    Role.Code.ADMIN,
    Role.Code.DPD,
    Role.Code.AUDITOR,
}


def can_read_audit(user) -> bool:
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.role_assignments.filter(
        role__code__in=AUDIT_READER_ROLE_CODES,
        role__is_active=True,
        revoked_at__isnull=True,
    ).exists()
