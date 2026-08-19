from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)

ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    environ.Env.read_env(ENV_FILE)


# ============================================================
# APPLICATION CRYPTOGRAPHY
# ============================================================

PII_ENCRYPTION_ACTIVE_VERSION = env.int(
    "PII_ENCRYPTION_ACTIVE_VERSION",
    default=1,
)

LOOKUP_HMAC_ACTIVE_VERSION = env.int(
    "LOOKUP_HMAC_ACTIVE_VERSION",
    default=1,
)

PII_ENCRYPTION_KEYS = {
    1: env(
        "PII_ENCRYPTION_KEY_V1",
        default="",
    ),
}

LOOKUP_HMAC_KEYS = {
    1: env(
        "LOOKUP_HMAC_KEY_V1",
        default="",
    ),
}


# ---------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=[],
)


# ---------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]


LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.organization.apps.OrganizationConfig",
    "apps.legal_content.apps.LegalContentConfig",
    "apps.subjects.apps.SubjectsConfig",
    "apps.cases.apps.CasesConfig",
    "apps.evidence.apps.EvidenceConfig",
    "apps.communications.apps.CommunicationsConfig",
    "apps.retention.apps.RetentionConfig",
    "apps.audit.apps.AuditConfig",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS


# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.SessionSecurityMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ---------------------------------------------------------------------
# URLs / WSGI
# ---------------------------------------------------------------------

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.navigation_permissions",
            ],
        },
    },
]


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

DATABASES = {
    "default": env.db("DATABASE_URL")
}


# ---------------------------------------------------------------------
# Email / encrypted communication outbox
# ---------------------------------------------------------------------

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default="noreply@localhost",
)

COMMUNICATION_MAX_ATTEMPTS = env.int(
    "COMMUNICATION_MAX_ATTEMPTS",
    default=5,
)
COMMUNICATION_RETRY_MINUTES = env.int(
    "COMMUNICATION_RETRY_MINUTES",
    default=5,
)


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/cases/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Five failures is the frozen architecture requirement. The lock period
# remains configuration-driven so it can be adjusted without a schema
# change. Current default: 15 minutes.
ACCOUNT_LOGIN_MAX_FAILURES = env.int(
    "ACCOUNT_LOGIN_MAX_FAILURES",
    default=5,
)
ACCOUNT_LOGIN_LOCK_SECONDS = env.int(
    "ACCOUNT_LOGIN_LOCK_SECONDS",
    default=15 * 60,
)

# Password -> MFA transitional state. No email, password, OTP, secret or
# other PII is stored in this session state.
AUTH_PENDING_MFA_TTL_SECONDS = env.int(
    "AUTH_PENDING_MFA_TTL_SECONDS",
    default=5 * 60,
)
AUTH_PENDING_MFA_MAX_FAILURES = env.int(
    "AUTH_PENDING_MFA_MAX_FAILURES",
    default=5,
)

MFA_TOTP_ISSUER = env(
    "MFA_TOTP_ISSUER",
    default="VINESA",
)
MFA_RECOVERY_CODE_COUNT = env.int(
    "MFA_RECOVERY_CODE_COUNT",
    default=10,
)

# Frozen session requirements: maximum 8 hours, 30 minutes inactivity.
AUTH_SESSION_ABSOLUTE_SECONDS = env.int(
    "AUTH_SESSION_ABSOLUTE_SECONDS",
    default=8 * 60 * 60,
)
AUTH_SESSION_IDLE_SECONDS = env.int(
    "AUTH_SESSION_IDLE_SECONDS",
    default=30 * 60,
)
AUTH_SENSITIVE_REAUTH_SECONDS = env.int(
    "AUTH_SENSITIVE_REAUTH_SECONDS",
    default=15 * 60,
)
AUTH_SENSITIVE_REAUTH_MAX_FAILURES = env.int(
    "AUTH_SENSITIVE_REAUTH_MAX_FAILURES",
    default=5,
)

# Public portal access codes. Codes are HMAC-protected at rest and delivered
# only through encrypted communication records.
PUBLIC_EMAIL_VERIFICATION_TTL_SECONDS = env.int(
    "PUBLIC_EMAIL_VERIFICATION_TTL_SECONDS",
    default=24 * 60 * 60,
)
PUBLIC_TRACKING_TTL_SECONDS = env.int(
    "PUBLIC_TRACKING_TTL_SECONDS",
    default=90 * 24 * 60 * 60,
)

SESSION_COOKIE_AGE = AUTH_SESSION_ABSOLUTE_SECONDS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"


# ---------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------

LANGUAGE_CODE = "es-ec"

TIME_ZONE = "America/Guayaquil"

USE_I18N = True

USE_TZ = True


# ---------------------------------------------------------------------
# Static / Media
# ---------------------------------------------------------------------

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

PRIVATE_STORAGE_ROOT = env(
    "PRIVATE_STORAGE_ROOT",
    default=str(BASE_DIR / "private_storage"),
)
PUBLIC_TEMPORARY_UPLOAD_TTL_SECONDS = env.int(
    "PUBLIC_TEMPORARY_UPLOAD_TTL_SECONDS",
    default=60 * 60,
)
PUBLIC_UPLOAD_MALWARE_SCANNER = env(
    "PUBLIC_UPLOAD_MALWARE_SCANNER",
    default="apps.evidence.services.scanners.ClamAVCommandScanner",
)
CLAMAV_EXECUTABLE = env("CLAMAV_EXECUTABLE", default="clamscan")
MALWARE_SCAN_TIMEOUT_SECONDS = env.int(
    "MALWARE_SCAN_TIMEOUT_SECONDS",
    default=30,
)
DATA_UPLOAD_MAX_NUMBER_FILES = env.int(
    "DATA_UPLOAD_MAX_NUMBER_FILES",
    default=3,
)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "FILE_UPLOAD_MAX_MEMORY_SIZE",
    default=1024 * 1024,
)


# ---------------------------------------------------------------------
# Django defaults
# ---------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
