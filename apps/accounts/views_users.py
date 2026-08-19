from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.decorators import sensitive_reauthentication_required
from apps.accounts.forms import (
    UserCreateForm,
    UserPasswordResetForm,
    UserListFilterForm,
    UserRoleForm,
)
from apps.accounts.models import MFADevice, UserRole
from apps.accounts.policies import can_manage_users
from apps.accounts.services.users import (
    UserAdministrationError,
    UserAdministrationPermissionError,
    UserAdministrationService,
)


def _require_user_administrator(request) -> None:
    if not can_manage_users(request.user):
        raise PermissionDenied


def _target_or_404(user_id):
    return get_object_or_404(
        get_user_model().objects.all(),
        pk=user_id,
    )


@login_required
@sensitive_reauthentication_required
@require_GET
def user_list(request):
    _require_user_administrator(request)
    active_assignments = UserRole.objects.filter(
        revoked_at__isnull=True,
        role__is_active=True,
    ).select_related("role")
    user_model = get_user_model()
    base_users = user_model.objects.all()
    metrics = base_users.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        inactive=Count("id", filter=Q(is_active=False)),
    )
    metrics["locked"] = base_users.filter(
        locked_until__gt=timezone.now()
    ).count()
    metrics["mfa_enabled"] = base_users.filter(
        mfa_devices__is_active=True,
        mfa_devices__is_confirmed=True,
        mfa_devices__revoked_at__isnull=True,
    ).distinct().count()
    form = UserListFilterForm(request.GET)
    users = base_users
    if form.is_valid():
        filters = form.cleaned_data
        if filters["search"]:
            users = users.filter(
                Q(email__icontains=filters["search"])
                | Q(full_name__icontains=filters["search"])
            )
        if filters["role"]:
            users = users.filter(
                role_assignments__role=filters["role"],
                role_assignments__revoked_at__isnull=True,
            )
        if filters["status"] == "ACTIVE":
            users = users.filter(is_active=True)
        elif filters["status"] == "INACTIVE":
            users = users.filter(is_active=False)
        elif filters["status"] == "LOCKED":
            users = users.filter(locked_until__gt=timezone.now())
        page_number = filters["page"] or 1
    else:
        page_number = 1
    active_mfa = MFADevice.objects.filter(
        user_id=OuterRef("pk"),
        is_active=True,
        is_confirmed=True,
        revoked_at__isnull=True,
    )
    users = (
        users
        .distinct()
        .annotate(mfa_enabled=Exists(active_mfa))
        .prefetch_related(
            Prefetch(
                "role_assignments",
                queryset=active_assignments,
                to_attr="active_role_assignments",
            )
        )
        .order_by("email")
    )
    page = Paginator(users, 20).get_page(page_number)
    return render(
        request,
        "accounts/user_list.html",
        {
            "users": page.object_list,
            "page": page,
            "filter_form": form,
            "metrics": metrics,
        },
    )


@login_required
@sensitive_reauthentication_required
@require_http_methods(["GET", "POST"])
def user_create(request):
    _require_user_administrator(request)
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            UserAdministrationService.create_user(
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                password=form.cleaned_data["password1"],
                role=form.cleaned_data["role"],
                actor=request.user,
            )
        except UserAdministrationError:
            form.add_error(
                None,
                "No fue posible crear el usuario. "
                "Verifique los datos y la política de contraseña.",
            )
        else:
            return redirect("accounts:user_list")
    return render(
        request,
        "accounts/user_create.html",
        {"form": form},
    )


@login_required
@sensitive_reauthentication_required
@require_http_methods(["GET", "POST"])
def user_change_role(request, user_id):
    _require_user_administrator(request)
    target = _target_or_404(user_id)
    current = (
        target.role_assignments
        .filter(
            revoked_at__isnull=True,
            is_primary=True,
            role__is_active=True,
        )
        .select_related("role")
        .first()
    )
    form = UserRoleForm(
        request.POST or None,
        initial={
            "role": current.role_id if current else None,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            UserAdministrationService.change_primary_role(
                user=target,
                role=form.cleaned_data["role"],
                actor=request.user,
            )
        except UserAdministrationError:
            form.add_error(
                None,
                "No fue posible cambiar el rol del usuario.",
            )
        else:
            return redirect("accounts:user_list")
    return render(
        request,
        "accounts/user_change_role.html",
        {"form": form, "target": target},
    )


def _change_active_state(request, *, user_id, is_active):
    _require_user_administrator(request)
    target = _target_or_404(user_id)
    try:
        UserAdministrationService.set_active(
            user=target,
            is_active=is_active,
            actor=request.user,
        )
    except UserAdministrationPermissionError:
        raise PermissionDenied
    except UserAdministrationError:
        return HttpResponseBadRequest(
            "No fue posible cambiar el estado del usuario."
        )
    return redirect("accounts:user_list")


@login_required
@sensitive_reauthentication_required
@require_POST
def user_activate(request, user_id):
    return _change_active_state(
        request,
        user_id=user_id,
        is_active=True,
    )


@login_required
@sensitive_reauthentication_required
@require_POST
def user_deactivate(request, user_id):
    return _change_active_state(
        request,
        user_id=user_id,
        is_active=False,
    )


@login_required
@sensitive_reauthentication_required
@require_POST
def user_unlock(request, user_id):
    _require_user_administrator(request)
    target = _target_or_404(user_id)
    try:
        UserAdministrationService.unlock(
            user=target,
            actor=request.user,
        )
    except UserAdministrationPermissionError:
        raise PermissionDenied
    except UserAdministrationError:
        return HttpResponseBadRequest(
            "No fue posible desbloquear el usuario."
        )
    return redirect("accounts:user_list")


@login_required
@sensitive_reauthentication_required
@require_http_methods(["GET", "POST"])
def user_reset_password(request, user_id):
    _require_user_administrator(request)
    target = _target_or_404(user_id)
    form = UserPasswordResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            UserAdministrationService.reset_password(
                user=target,
                password=form.cleaned_data["password1"],
                actor=request.user,
            )
        except UserAdministrationError:
            form.add_error(
                None,
                "No fue posible restablecer la contraseña. "
                "Verifique la política de seguridad.",
            )
        else:
            return redirect("accounts:user_list")
    return render(
        request,
        "accounts/user_reset_password.html",
        {"form": form, "target": target},
    )
