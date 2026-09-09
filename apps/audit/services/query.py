from __future__ import annotations

from math import ceil

from apps.audit.models import AuditLog
from apps.audit.presentation import (
    action_label,
    chain_scope_label,
    entity_label,
    source_label,
)
from apps.audit.policies import can_read_audit
from apps.audit.services.audit import LogSanitizer


class AuditQueryPermissionError(Exception):
    pass


class AuditQueryService:
    EXPORT_LIMIT = 5000

    @classmethod
    def _filtered_queryset(cls, *, user, filters):
        if not can_read_audit(user):
            raise AuditQueryPermissionError
        queryset = AuditLog.objects.select_related("actor_user")
        if filters.get("date_from"):
            queryset = queryset.filter(
                created_at__date__gte=filters["date_from"]
            )
        if filters.get("date_to"):
            queryset = queryset.filter(
                created_at__date__lte=filters["date_to"]
            )
        if filters.get("actor"):
            queryset = queryset.filter(actor_user_id=filters["actor"])
        if filters.get("action"):
            queryset = queryset.filter(action=filters["action"])
        if filters.get("entity_type"):
            queryset = queryset.filter(entity_type=filters["entity_type"])
        if filters.get("source"):
            queryset = queryset.filter(source=filters["source"])
        if filters.get("correlation_id"):
            queryset = queryset.filter(
                correlation_id=filters["correlation_id"]
            )
        if filters.get("chain_scope"):
            queryset = queryset.filter(chain_scope=filters["chain_scope"])
        return queryset.order_by("-created_at", "-id")

    @staticmethod
    def _actor(entry):
        if entry.actor_user_id is None:
            return {"type": entry.actor_type, "user_id": None, "name": "Sistema"}
        return {
            "type": entry.actor_type,
            "user_id": str(entry.actor_user_id),
            "name": entry.actor_user.full_name or entry.actor_user.email,
        }

    @classmethod
    def _serialize(cls, entry, *, detail=False):
        payload = {
            "id": entry.id,
            "created_at": entry.created_at,
            "actor": cls._actor(entry),
            "action": entry.action,
            "action_label": action_label(entry.action),
            "entity_type": entry.entity_type,
            "entity_type_label": entity_label(entry.entity_type),
            "entity_pk": entry.entity_pk,
            "source": entry.source,
            "source_label": source_label(entry.source),
            "correlation_id": str(entry.correlation_id),
            "chain_scope": entry.chain_scope,
            "chain_scope_label": chain_scope_label(entry.chain_scope),
            "chain_position": entry.chain_position,
        }
        if detail:
            payload.update(
                {
                    "description": LogSanitizer.sanitize(entry.description),
                    "previous_values": LogSanitizer.sanitize(
                        entry.previous_values
                    ),
                    "new_values": LogSanitizer.sanitize(entry.new_values),
                    "metadata": LogSanitizer.sanitize(entry.metadata),
                    "ip_address": entry.ip_address,
                    "user_agent": entry.user_agent,
                    "entry_hash": entry.entry_hash,
                }
            )
        return payload

    @classmethod
    def search(cls, *, user, filters):
        queryset = cls._filtered_queryset(user=user, filters=filters)
        page = filters.get("page") or 1
        page_size = filters.get("page_size") or 25
        total = queryset.count()
        start = (page - 1) * page_size
        entries = queryset[start : start + page_size]
        return {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": ceil(total / page_size) if total else 0,
            },
            "events": [cls._serialize(entry) for entry in entries],
        }

    @classmethod
    def detail(cls, *, user, event_id):
        queryset = cls._filtered_queryset(user=user, filters={})
        entry = queryset.filter(pk=event_id).first()
        if entry is None:
            return None
        return cls._serialize(entry, detail=True)

    @classmethod
    def export(cls, *, user, filters):
        queryset = cls._filtered_queryset(user=user, filters=filters)
        return (
            [
                cls._serialize(entry)
                for entry in queryset[: cls.EXPORT_LIMIT]
            ],
            cls.EXPORT_LIMIT,
        )
