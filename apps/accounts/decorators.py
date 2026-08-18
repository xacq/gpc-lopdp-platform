from __future__ import annotations

from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.services.authentication import SessionSecurityService


def sensitive_reauthentication_required(view_func):
    """Require MFA reauthentication no more than 15 minutes ago."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if (
            SessionSecurityService
            .has_recent_sensitive_reauthentication(request)
        ):
            return view_func(request, *args, **kwargs)

        next_url = request.get_full_path()
        if request.method != "GET":
            referer = request.META.get("HTTP_REFERER")
            if referer and url_has_allowed_host_and_scheme(
                url=referer,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                next_url = referer
            else:
                next_url = reverse("cases:request_list")

        return redirect(
            f"{reverse('accounts:reauth')}?"
            f"{urlencode({'next': next_url})}"
        )

    return wrapped
