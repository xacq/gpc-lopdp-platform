from apps.accounts.models import Role
from apps.cases.policies import active_role_codes


def can_manage_legal(user) -> bool:
    return bool(
        getattr(user, "is_active", False)
        and (
            getattr(user, "is_superuser", False)
            or active_role_codes(user) & {Role.Code.ADMIN, Role.Code.DPD}
        )
    )
