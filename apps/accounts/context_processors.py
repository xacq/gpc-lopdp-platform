from apps.accounts.policies import can_manage_users
from apps.cases.policies import can_access_case_panel
from apps.organization.policies import can_manage_system_settings


def navigation_permissions(request):
    user = getattr(request, "user", None)
    return {
        "nav_can_access_cases": can_access_case_panel(user),
        "nav_can_manage_users": can_manage_users(user),
        "nav_can_manage_settings": can_manage_system_settings(user),
    }
