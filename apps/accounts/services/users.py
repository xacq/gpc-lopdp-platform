from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import MFADevice, Role, UserRole
from apps.accounts.policies import can_manage_users
from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService


class UserAdministrationError(Exception):
    """Base exception for administrative user management."""


class UserAdministrationPermissionError(UserAdministrationError):
    pass


class UserAdministrationConflict(UserAdministrationError):
    pass


class UserAdministrationValidationError(UserAdministrationError):
    pass


class UserAdministrationService:
    """Secure lifecycle management for administrative users and roles."""

    @classmethod
    def _require_actor(cls, actor):
        user_model = get_user_model()
        persisted = (
            user_model.objects
            .filter(pk=getattr(actor, "pk", None), is_active=True)
            .first()
        )
        if persisted is None or not can_manage_users(persisted):
            raise UserAdministrationPermissionError(
                "User administration is not permitted."
            )
        return persisted

    @classmethod
    def _locked_target(cls, user):
        return (
            get_user_model().objects
            .select_for_update()
            .filter(pk=getattr(user, "pk", user))
            .first()
        )

    @classmethod
    def _active_role(cls, role):
        persisted = (
            Role.objects.select_for_update()
            .filter(pk=getattr(role, "pk", role), is_active=True)
            .first()
        )
        if persisted is None:
            raise UserAdministrationValidationError(
                "The selected role is unavailable."
            )
        return persisted

    @classmethod
    def _ensure_target_allowed(cls, *, actor, target):
        if target is None:
            raise UserAdministrationValidationError(
                "The selected user is unavailable."
            )
        if target.is_superuser and not actor.is_superuser:
            raise UserAdministrationPermissionError(
                "Only a superuser may manage another superuser."
            )

    @classmethod
    def _manager_count(cls) -> int:
        return (
            get_user_model().objects
            .filter(is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(
                    role_assignments__role__code=Role.Code.ADMIN,
                    role_assignments__role__is_active=True,
                    role_assignments__revoked_at__isnull=True,
                )
            )
            .distinct()
            .count()
        )

    @classmethod
    def _is_manager(cls, user) -> bool:
        return bool(
            user.is_active
            and (
                user.is_superuser
                or UserRole.objects.filter(
                    user=user,
                    role__code=Role.Code.ADMIN,
                    role__is_active=True,
                    revoked_at__isnull=True,
                ).exists()
            )
        )

    @classmethod
    def _revoke_mfa(cls, *, user, now) -> int:
        return MFADevice.objects.filter(
            user=user,
            is_active=True,
            revoked_at__isnull=True,
        ).update(
            is_active=False,
            revoked_at=now,
        )

    @classmethod
    def _audit(cls, *, action, actor, target, metadata=None):
        return AuditService.write(
            action=action,
            entity_type="USER",
            entity_pk=target.pk,
            actor_type=AuditLog.ActorType.USER,
            actor=actor,
            metadata=metadata or {},
        )

    @classmethod
    @transaction.atomic
    def create_user(
        cls,
        *,
        email: str,
        full_name: str,
        password: str,
        role,
        actor,
    ):
        actor = cls._require_actor(actor)
        role = cls._active_role(role)
        email = get_user_model().objects.normalize_email(email).strip()
        full_name = full_name.strip()
        if not email or not full_name:
            raise UserAdministrationValidationError(
                "Email and full name are required."
            )

        candidate = get_user_model()(
            email=email,
            full_name=full_name,
            is_active=True,
        )
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise UserAdministrationValidationError(
                "The password does not meet the security policy."
            ) from exc

        candidate.set_password(password)
        try:
            candidate.save()
        except IntegrityError as exc:
            raise UserAdministrationConflict(
                "The user could not be created."
            ) from exc

        UserRole.objects.create(
            user=candidate,
            role=role,
            is_primary=True,
            assigned_by=actor,
        )
        cls._audit(
            action="USER_CREATED",
            actor=actor,
            target=candidate,
            metadata={"role_code": role.code},
        )
        return candidate

    @classmethod
    @transaction.atomic
    def change_primary_role(cls, *, user, role, actor):
        actor = cls._require_actor(actor)
        target = cls._locked_target(user)
        cls._ensure_target_allowed(actor=actor, target=target)
        role = cls._active_role(role)

        current_assignments = list(
            UserRole.objects.select_for_update()
            .filter(user=target, revoked_at__isnull=True)
            .select_related("role")
        )
        has_admin = any(
            assignment.role.code == Role.Code.ADMIN
            and assignment.role.is_active
            for assignment in current_assignments
        )
        if (
            has_admin
            and role.code != Role.Code.ADMIN
            and cls._manager_count() <= 1
        ):
            raise UserAdministrationConflict(
                "The last administrator cannot be demoted."
            )

        if (
            len(current_assignments) == 1
            and current_assignments[0].role_id == role.pk
            and current_assignments[0].is_primary
        ):
            return target

        now = timezone.now()
        UserRole.objects.filter(
            pk__in=[item.pk for item in current_assignments]
        ).update(
            revoked_at=now,
            is_primary=False,
        )
        UserRole.objects.create(
            user=target,
            role=role,
            is_primary=True,
            assigned_by=actor,
        )
        cls._audit(
            action="USER_PRIMARY_ROLE_CHANGED",
            actor=actor,
            target=target,
            metadata={"role_code": role.code},
        )
        return target

    @classmethod
    @transaction.atomic
    def set_active(cls, *, user, is_active: bool, actor):
        actor = cls._require_actor(actor)
        target = cls._locked_target(user)
        cls._ensure_target_allowed(actor=actor, target=target)
        if not isinstance(is_active, bool):
            raise TypeError("is_active must be a boolean.")
        if not is_active and target.pk == actor.pk:
            raise UserAdministrationConflict(
                "An administrator cannot deactivate their own account."
            )
        if (
            not is_active
            and cls._is_manager(target)
            and cls._manager_count() <= 1
        ):
            raise UserAdministrationConflict(
                "The last administrator cannot be deactivated."
            )
        if target.is_active == is_active:
            return target

        now = timezone.now()
        target.is_active = is_active
        target.updated_at = now
        update_fields = ["is_active", "updated_at"]
        if is_active:
            target.failed_login_attempts = 0
            target.locked_until = None
            update_fields.extend(
                ["failed_login_attempts", "locked_until"]
            )
        else:
            cls._revoke_mfa(user=target, now=now)
        target.save(update_fields=update_fields)
        cls._audit(
            action=("USER_ACTIVATED" if is_active else "USER_DEACTIVATED"),
            actor=actor,
            target=target,
            metadata={"active": is_active},
        )
        return target

    @classmethod
    @transaction.atomic
    def unlock(cls, *, user, actor):
        actor = cls._require_actor(actor)
        target = cls._locked_target(user)
        cls._ensure_target_allowed(actor=actor, target=target)
        target.failed_login_attempts = 0
        target.locked_until = None
        target.updated_at = timezone.now()
        target.save(
            update_fields=[
                "failed_login_attempts",
                "locked_until",
                "updated_at",
            ]
        )
        cls._audit(
            action="USER_ACCOUNT_UNLOCKED",
            actor=actor,
            target=target,
        )
        return target

    @classmethod
    @transaction.atomic
    def reset_password(cls, *, user, password: str, actor):
        actor = cls._require_actor(actor)
        target = cls._locked_target(user)
        cls._ensure_target_allowed(actor=actor, target=target)
        try:
            validate_password(password, user=target)
        except ValidationError as exc:
            raise UserAdministrationValidationError(
                "The password does not meet the security policy."
            ) from exc
        now = timezone.now()
        target.set_password(password)
        target.failed_login_attempts = 0
        target.locked_until = None
        target.updated_at = now
        target.save(
            update_fields=[
                "password",
                "failed_login_attempts",
                "locked_until",
                "updated_at",
            ]
        )
        revoked_count = cls._revoke_mfa(user=target, now=now)
        cls._audit(
            action="USER_PASSWORD_RESET",
            actor=actor,
            target=target,
            metadata={"mfa_devices_revoked": revoked_count},
        )
        return target
