from django.urls import path

from apps.accounts.views import (
    login_view,
    logout_view,
    mfa_pending,
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
]