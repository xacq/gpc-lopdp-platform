from .base import *  # noqa: F403,F401


DEBUG = False

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = env.bool(  # noqa: F405
    "DJANGO_SECURE_SSL_REDIRECT",
    default=True,
)
SECURE_HSTS_SECONDS = env.int(  # noqa: F405
    "DJANGO_SECURE_HSTS_SECONDS",
    default=31536000,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(  # noqa: F405
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)
SECURE_HSTS_PRELOAD = env.bool(  # noqa: F405
    "DJANGO_SECURE_HSTS_PRELOAD",
    default=False,
)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

X_FRAME_OPTIONS = "DENY"
