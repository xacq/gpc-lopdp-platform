from __future__ import annotations

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from apps.accounts.forms import LoginForm
from apps.accounts.services.authentication import (
    AuthenticationRejected,
    AuthenticationService,
    AuthenticationSessionService,
)


_GENERIC_LOGIN_ERROR = (
    "No fue posible iniciar sesión con las "
    "credenciales proporcionadas."
)


def _safe_next_url(request, candidate: str | None) -> str | None:
    if not candidate:
        return None

    if url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate

    return None


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(
            settings.LOGIN_REDIRECT_URL
        )

    if request.method == "POST":
        form = LoginForm(request.POST)

        if form.is_valid():
            try:
                user = (
                    AuthenticationService
                    .verify_primary_factor(
                        email=(
                            form.cleaned_data[
                                "email"
                            ]
                        ),
                        password=(
                            form.cleaned_data[
                                "password"
                            ]
                        ),
                    )
                )
            except AuthenticationRejected:
                form.add_error(
                    None,
                    _GENERIC_LOGIN_ERROR,
                )
            else:
                safe_next = _safe_next_url(
                    request,
                    form.cleaned_data.get(
                        "next"
                    ),
                )

                (
                    AuthenticationSessionService
                    .begin_pending_mfa(
                        request=request,
                        user=user,
                        next_url=safe_next,
                    )
                )

                return redirect(
                    "accounts:mfa_pending"
                )
    else:
        form = LoginForm(
            initial={
                "next": _safe_next_url(
                    request,
                    request.GET.get("next"),
                )
                or "",
            }
        )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
        },
    )


@require_GET
def mfa_pending(request):
    pending = (
        AuthenticationSessionService
        .get_pending_mfa(request)
    )

    if pending is None:
        return redirect(
            reverse("accounts:login")
        )

    return render(
        request,
        "accounts/mfa_pending.html",
        {},
    )


@require_POST
def logout_view(request):
    django_logout(request)
    return redirect(
        settings.LOGOUT_REDIRECT_URL
    )
