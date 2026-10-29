from .models import AuditLog


def log(user, action, project=None, target=None, **detail):
    """Write one audit entry. `detail` must never contain secrets."""
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        project=project,
        action=action,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=getattr(target, "pk", None),
        detail=detail,
    )
