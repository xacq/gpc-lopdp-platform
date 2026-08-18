from __future__ import annotations

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import LoginForm, MFAChallengeForm, TOTPForm
from apps.accounts.services.authentication import (
    AuthenticationRejected,
    AuthenticationService,
    AuthenticationSessionService,
)
from apps.accounts.services.mfa import (
    MFAEnrollmentRequired,
    MFARejected,
    MFAService,
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


@require_http_methods(["GET", "POST"])
def mfa_pending(request):
    pending = (
        AuthenticationSessionService
        .get_pending_mfa(request)
    )

    if pending is None:
        return redirect(
            reverse("accounts:login")
        )

    user = (
        AuthenticationSessionService
        .get_pending_user(request)
    )
    if user is None:
        return redirect(
            reverse("accounts:login")
        )

    if MFAService.has_confirmed_totp(user=user):
        form = MFAChallengeForm(
            request.POST or None
        )
        if (
            request.method == "POST"
            and form.is_valid()
        ):
            code = form.cleaned_data["code"]
            try:
                if (
                    len(code.strip()) == 6
                    and code.strip().isascii()
                    and code.strip().isdigit()
                ):
                    MFAService.verify_totp(
                        user=user,
                        code=code,
                    )
                else:
                    MFAService.consume_recovery_code(
                        user=user,
                        code=code,
                    )
            except (
                MFARejected,
                MFAEnrollmentRequired,
            ):
                (
                    AuthenticationSessionService
                    .record_pending_mfa_failure(request)
                )
                form.add_error(
                    None,
                    "No fue posible verificar "
                    "el segundo factor.",
                )
            else:
                next_url = (
                    AuthenticationSessionService
                    .complete_mfa(
                        request=request,
                        user=user,
                    )
                )
                return redirect(next_url)

        return render(
            request,
            "accounts/mfa_challenge.html",
            {"form": form},
        )

    enrollment = MFAService.begin_totp_enrollment(
        user=user
    )
    form = TOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            confirmation = MFAService.confirm_totp(
                user=user,
                device_id=enrollment.device.pk,
                code=form.cleaned_data["code"],
            )
        except MFARejected:
            (
                AuthenticationSessionService
                .record_pending_mfa_failure(request)
            )
            form.add_error(
                None,
                "No fue posible verificar "
                "el segundo factor.",
            )
        else:
            next_url = (
                AuthenticationSessionService
                .complete_mfa(
                    request=request,
                    user=user,
                )
            )
            return render(
                request,
                "accounts/recovery_codes.html",
                {
                    "recovery_codes": (
                        confirmation
                        .recovery_codes
                    ),
                    "next_url": next_url,
                },
            )

    return render(
        request,
        "accounts/mfa_enroll.html",
        {
            "form": form,
            "secret": enrollment.secret,
            "provisioning_uri": (
                enrollment.provisioning_uri
            ),
            "qr_data_uri": enrollment.qr_data_uri,
        },
    )


@require_POST
def logout_view(request):
    django_logout(request)
    return redirect(
        settings.LOGOUT_REDIRECT_URL
    )
