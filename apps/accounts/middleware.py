from apps.accounts.services.authentication import (
    SessionSecurityService,
)


class SessionSecurityMiddleware:
    """Apply absolute and idle timeouts to authenticated sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            SessionSecurityService.enforce(
                request
            )

        return self.get_response(request)
