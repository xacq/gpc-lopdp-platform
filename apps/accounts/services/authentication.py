from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService


_DUMMY_PASSWORD_HASH = make_password(
    "gpc-lopdp-dummy-authentication-password"
)

_PENDING_USER_KEY = "_gpc_pending_auth_user_id"
_PENDING_STARTED_KEY = "_gpc_pending_auth_started_at"
_PENDING_NEXT_KEY = "_gpc_pending_auth_next"
_PENDING_FAILURES_KEY = "_gpc_pending_mfa_failures"

_AUTH_STARTED_KEY = "_gpc_auth_started_at"
_AUTH_LAST_ACTIVITY_KEY = "_gpc_auth_last_activity_at"


class AuthenticationError(Exception):
    """Base exception for administrative authentication."""


class AuthenticationRejected(AuthenticationError):
    """Primary factor was not accepted.

    Deliberately generic so callers do not reveal whether an account
    exists, is inactive, is locked, or has an incorrect password.
    """


@dataclass(frozen=True)
class PendingAuthentication:
    user_id: str
    started_at: int
    next_url: str | None


class AuthenticationService:
    """Password-stage authentication for administrative users.

    A successful password check does NOT create a Django authenticated
    session. It only authorizes creation of a short-lived pending MFA
    session. Full login is completed by the MFA phase.
    """

    FAILURE_ACTION = "AUTH_PRIMARY_FACTOR_REJECTED"
    SUCCESS_ACTION = "AUTH_PRIMARY_FACTOR_ACCEPTED"

    @classmethod
    def _max_failures(cls) -> int:
        value = int(
            getattr(
                settings,
                "ACCOUNT_LOGIN_MAX_FAILURES",
                5,
            )
        )
        if value <= 0:
            raise ValueError(
                "ACCOUNT_LOGIN_MAX_FAILURES must be positive."
            )
        return value

    @classmethod
    def _lock_seconds(cls) -> int:
        value = int(
            getattr(
                settings,
                "ACCOUNT_LOGIN_LOCK_SECONDS",
                900,
            )
        )
        if value <= 0:
            raise ValueError(
                "ACCOUNT_LOGIN_LOCK_SECONDS must be positive."
            )
        return value

    @classmethod
    def _normalize_email(cls, email: str) -> str:
        if not isinstance(email, str):
            raise TypeError("email must be a string.")
        return email.strip().lower()

    @classmethod
    def _audit_rejection(
        cls,
        *,
        user,
        reason_code: str,
        failed_attempts: int | None = None,
        locked: bool = False,
    ):
        metadata = {
            "reason_code": reason_code,
            "locked": locked,
        }
        if failed_attempts is not None:
            metadata["failed_attempts"] = failed_attempts

        return AuditService.write(
            action=cls.FAILURE_ACTION,
            entity_type="USER",
            entity_pk=(
                user.pk
                if user is not None
                else None
            ),
            actor_type=AuditLog.ActorType.SYSTEM,
            actor=None,
            metadata=metadata,
        )

    @classmethod
    def _audit_success(cls, *, user):
        return AuditService.write(
            action=cls.SUCCESS_ACTION,
            entity_type="USER",
            entity_pk=user.pk,
            actor_type=AuditLog.ActorType.USER,
            actor=user,
            metadata={
                "authentication_stage": "PASSWORD",
            },
        )

    @classmethod
    def verify_primary_factor(
        cls,
        *,
        email: str,
        password: str,
    ):
        if not isinstance(password, str):
            raise TypeError("password must be a string.")

        normalized_email = cls._normalize_email(email)
        now = timezone.now()
        user_model = get_user_model()
        rejected = False

        with transaction.atomic():
            user = (
                user_model.objects
                .select_for_update()
                .filter(email__iexact=normalized_email)
                .first()
            )

            if user is None:
                # Keep an expensive password-hash operation for unknown
                # accounts to reduce obvious account-enumeration timing.
                check_password(
                    password,
                    _DUMMY_PASSWORD_HASH,
                )
                cls._audit_rejection(
                    user=None,
                    reason_code="INVALID_CREDENTIALS",
                )
                rejected = True
            else:
                if (
                    user.locked_until is not None
                    and user.locked_until <= now
                ):
                    user.failed_login_attempts = 0
                    user.locked_until = None
                    user.updated_at = now
                    user.save(
                        update_fields=[
                            "failed_login_attempts",
                            "locked_until",
                            "updated_at",
                        ]
                    )

                is_currently_locked = (
                    user.locked_until is not None
                    and user.locked_until > now
                )

                if is_currently_locked:
                    # Perform the password check without changing the
                    # externally visible result.
                    user.check_password(password)
                    cls._audit_rejection(
                        user=user,
                        reason_code="ACCOUNT_LOCKED",
                        failed_attempts=(
                            user.failed_login_attempts
                        ),
                        locked=True,
                    )
                    rejected = True

                elif not user.is_active:
                    user.check_password(password)
                    cls._audit_rejection(
                        user=user,
                        reason_code="ACCOUNT_INACTIVE",
                        failed_attempts=(
                            user.failed_login_attempts
                        ),
                    )
                    rejected = True

                elif not user.check_password(password):
                    failures = (
                        user.failed_login_attempts + 1
                    )
                    user.failed_login_attempts = failures
                    user.updated_at = now

                    locked = (
                        failures >= cls._max_failures()
                    )

                    if locked:
                        user.locked_until = (
                            now
                            + timedelta(
                                seconds=cls._lock_seconds()
                            )
                        )

                    user.save(
                        update_fields=[
                            "failed_login_attempts",
                            "locked_until",
                            "updated_at",
                        ]
                    )

                    cls._audit_rejection(
                        user=user,
                        reason_code="INVALID_CREDENTIALS",
                        failed_attempts=failures,
                        locked=locked,
                    )
                    rejected = True

                else:
                    changed_fields = []

                    if user.failed_login_attempts != 0:
                        user.failed_login_attempts = 0
                        changed_fields.append(
                            "failed_login_attempts"
                        )

                    if user.locked_until is not None:
                        user.locked_until = None
                        changed_fields.append(
                            "locked_until"
                        )

                    if changed_fields:
                        user.updated_at = now
                        changed_fields.append("updated_at")
                        user.save(
                            update_fields=changed_fields
                        )

                    cls._audit_success(user=user)

        if rejected:
            raise AuthenticationRejected(
                "Primary factor was rejected."
            )

        return user


class AuthenticationSessionService:
    """Manage the short-lived state between password and MFA."""

    @classmethod
    def _pending_ttl_seconds(cls) -> int:
        value = int(
            getattr(
                settings,
                "AUTH_PENDING_MFA_TTL_SECONDS",
                300,
            )
        )
        if value <= 0:
            raise ValueError(
                "AUTH_PENDING_MFA_TTL_SECONDS must be positive."
            )
        return value

    @classmethod
    def begin_pending_mfa(
        cls,
        *,
        request,
        user,
        next_url: str | None = None,
    ) -> PendingAuthentication:
        request.session.flush()

        now_epoch = int(
            timezone.now().timestamp()
        )

        request.session[_PENDING_USER_KEY] = str(
            user.pk
        )
        request.session[_PENDING_STARTED_KEY] = (
            now_epoch
        )

        if next_url:
            request.session[_PENDING_NEXT_KEY] = next_url

        request.session.set_expiry(
            cls._pending_ttl_seconds()
        )

        return PendingAuthentication(
            user_id=str(user.pk),
            started_at=now_epoch,
            next_url=next_url,
        )

    @classmethod
    def clear_pending_mfa(cls, request) -> None:
        for key in (
            _PENDING_USER_KEY,
            _PENDING_STARTED_KEY,
            _PENDING_NEXT_KEY,
            _PENDING_FAILURES_KEY,
        ):
            request.session.pop(key, None)

    @classmethod
    def record_pending_mfa_failure(cls, request) -> bool:
        """Record an MFA failure and expire pending state at the limit."""
        failures = request.session.get(
            _PENDING_FAILURES_KEY,
            0,
        )
        if not isinstance(failures, int) or failures < 0:
            failures = 0
        failures += 1
        maximum = int(
            getattr(
                settings,
                "AUTH_PENDING_MFA_MAX_FAILURES",
                5,
            )
        )
        if maximum <= 0:
            raise ValueError(
                "AUTH_PENDING_MFA_MAX_FAILURES must be positive."
            )
        if failures >= maximum:
            cls.clear_pending_mfa(request)
            return False
        request.session[_PENDING_FAILURES_KEY] = failures
        return True

    @classmethod
    def complete_mfa(cls, *, request, user) -> str:
        pending = cls.get_pending_mfa(request)
        if pending is None or pending.user_id != str(user.pk):
            raise AuthenticationRejected(
                "Pending authentication is invalid."
            )

        next_url = (
            pending.next_url
            or settings.LOGIN_REDIRECT_URL
        )
        cls.clear_pending_mfa(request)
        django_login(
            request,
            user,
            backend=(
                "django.contrib.auth.backends."
                "ModelBackend"
            ),
        )
        SessionSecurityService.initialize_authenticated_session(
            request
        )
        return next_url

    @classmethod
    def get_pending_mfa(
        cls,
        request,
    ) -> PendingAuthentication | None:
        user_id = request.session.get(
            _PENDING_USER_KEY
        )
        started_at = request.session.get(
            _PENDING_STARTED_KEY
        )

        if not user_id or not isinstance(
            started_at,
            int,
        ):
            cls.clear_pending_mfa(request)
            return None

        now_epoch = int(
            timezone.now().timestamp()
        )

        if (
            now_epoch - started_at
            > cls._pending_ttl_seconds()
        ):
            cls.clear_pending_mfa(request)
            return None

        user_model = get_user_model()
        exists = user_model.objects.filter(
            pk=user_id,
            is_active=True,
        ).exists()

        if not exists:
            cls.clear_pending_mfa(request)
            return None

        return PendingAuthentication(
            user_id=str(user_id),
            started_at=started_at,
            next_url=request.session.get(
                _PENDING_NEXT_KEY
            ),
        )

    @classmethod
    def get_pending_user(cls, request):
        pending = cls.get_pending_mfa(request)
        if pending is None:
            return None
        return (
            get_user_model()
            .objects
            .filter(
                pk=pending.user_id,
                is_active=True,
            )
            .first()
        )


class SessionSecurityService:
    """Enforce absolute and inactivity limits for authenticated sessions."""

    @classmethod
    def _absolute_seconds(cls) -> int:
        value = int(
            getattr(
                settings,
                "AUTH_SESSION_ABSOLUTE_SECONDS",
                8 * 60 * 60,
            )
        )
        if value <= 0:
            raise ValueError(
                "AUTH_SESSION_ABSOLUTE_SECONDS must be positive."
            )
        return value

    @classmethod
    def _idle_seconds(cls) -> int:
        value = int(
            getattr(
                settings,
                "AUTH_SESSION_IDLE_SECONDS",
                30 * 60,
            )
        )
        if value <= 0:
            raise ValueError(
                "AUTH_SESSION_IDLE_SECONDS must be positive."
            )
        return value

    @classmethod
    def initialize_authenticated_session(
        cls,
        request,
    ) -> None:
        now_epoch = int(
            timezone.now().timestamp()
        )
        request.session[_AUTH_STARTED_KEY] = (
            now_epoch
        )
        request.session[_AUTH_LAST_ACTIVITY_KEY] = (
            now_epoch
        )
        request.session.set_expiry(
            min(
                cls._absolute_seconds(),
                cls._idle_seconds(),
            )
        )

    @classmethod
    def enforce(cls, request) -> bool:
        if not request.user.is_authenticated:
            return True

        now_epoch = int(
            timezone.now().timestamp()
        )
        started_at = request.session.get(
            _AUTH_STARTED_KEY
        )
        last_activity = request.session.get(
            _AUTH_LAST_ACTIVITY_KEY
        )

        # Existing development/test sessions created before this layer
        # are initialized on their first authenticated request. A
        # production rollout should invalidate legacy sessions once MFA
        # gating is enabled in Phase 2A.3.
        if not isinstance(started_at, int) or not isinstance(
            last_activity,
            int,
        ):
            cls.initialize_authenticated_session(
                request
            )
            return True

        absolute_age = now_epoch - started_at
        idle_age = now_epoch - last_activity

        if (
            absolute_age
            >= cls._absolute_seconds()
            or idle_age >= cls._idle_seconds()
        ):
            django_logout(request)
            return False

        request.session[
            _AUTH_LAST_ACTIVITY_KEY
        ] = now_epoch

        remaining_absolute = max(
            1,
            cls._absolute_seconds()
            - absolute_age,
        )

        request.session.set_expiry(
            min(
                cls._idle_seconds(),
                remaining_absolute,
            )
        )

        return True
