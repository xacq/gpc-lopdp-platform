from django.urls import path

from apps.accounts.views import (
    login_view,
    logout_view,
    mfa_pending,
    sensitive_reauthentication,
)
from apps.accounts.views_users import (
    user_activate,
    user_change_role,
    user_create,
    user_deactivate,
    user_list,
    user_reset_password,
    user_unlock,
)

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        login_view,
        name="login",
    ),
    path(
        "logout/",
        logout_view,
        name="logout",
    ),
    path(
        "mfa/",
        mfa_pending,
        name="mfa_pending",
    ),
    path(
        "reauthenticate/",
        sensitive_reauthentication,
        name="reauth",
    ),
    path(
        "users/",
        user_list,
        name="user_list",
    ),
    path(
        "users/new/",
        user_create,
        name="user_create",
    ),
    path(
        "users/<uuid:user_id>/role/",
        user_change_role,
        name="user_change_role",
    ),
    path(
        "users/<uuid:user_id>/activate/",
        user_activate,
        name="user_activate",
    ),
    path(
        "users/<uuid:user_id>/deactivate/",
        user_deactivate,
        name="user_deactivate",
    ),
    path(
        "users/<uuid:user_id>/unlock/",
        user_unlock,
        name="user_unlock",
    ),
    path(
        "users/<uuid:user_id>/password/",
        user_reset_password,
        name="user_reset_password",
    ),
]
