from __future__ import annotations

from apps.accounts.policies import can_manage_users


def can_manage_system_settings(user) -> bool:
    return can_manage_users(user)
