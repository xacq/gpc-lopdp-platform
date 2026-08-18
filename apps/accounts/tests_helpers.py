from django.utils import timezone


def force_mfa_login(client, user, *, sensitive=True):
    """Create a fully MFA-gated session for HTTP tests."""
    client.force_login(user)
    now_epoch = int(timezone.now().timestamp())
    session = client.session
    session["_gpc_auth_started_at"] = now_epoch
    session["_gpc_auth_last_activity_at"] = now_epoch
    session["_gpc_mfa_verified_at"] = now_epoch
    session["_gpc_mfa_user_id"] = str(user.pk)
    if sensitive:
        session["_gpc_sensitive_verified_at"] = now_epoch
    session.save()
