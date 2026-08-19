from __future__ import annotations

import hashlib
import html
import uuid
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.policies import active_role_codes
from apps.evidence.models import NoticeDelivery
from apps.legal_content.models import LegalDocument


class LegalDocumentError(Exception):
    pass


class LegalDocumentPermissionError(LegalDocumentError):
    pass


class LegalDocumentStateError(LegalDocumentError):
    pass


class _LegalHTMLSanitizer(HTMLParser):
    ALLOWED_TAGS = {
        "p", "br", "h2", "h3", "h4", "ul", "ol", "li",
        "strong", "em", "blockquote", "a",
    }
    VOID_TAGS = {"br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in self.ALLOWED_TAGS:
            return
        safe_attrs = ""
        if tag == "a":
            href = next((value for key, value in attrs if key.lower() == "href"), None)
            if href:
                parsed = urlparse(href.strip())
                if parsed.scheme in {"", "http", "https", "mailto"}:
                    safe_attrs = f' href="{html.escape(href.strip(), quote=True)}"'
        self.parts.append(f"<{tag}{safe_attrs}>")
        if tag not in self.VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.open_tags and self.open_tags[-1] == tag:
            self.open_tags.pop()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag not in self.open_tags:
            return
        while self.open_tags:
            current = self.open_tags.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def close(self):
        super().close()
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")

    def sanitized(self) -> str:
        return "".join(self.parts).strip()


class LegalDocumentService:
    MANAGER_ROLES = {Role.Code.ADMIN, Role.Code.DPD}

    @classmethod
    def _validate_actor(cls, actor):
        if (
            actor is None
            or not getattr(actor, "is_authenticated", False)
            or not getattr(actor, "is_active", False)
            or not actor.__class__.objects.filter(pk=actor.pk, is_active=True).exists()
        ):
            raise LegalDocumentPermissionError(
                "Legal document management requires an active user."
            )
        if not getattr(actor, "is_superuser", False) and not (
            active_role_codes(actor) & cls.MANAGER_ROLES
        ):
            raise LegalDocumentPermissionError(
                "Legal document management is not permitted for this actor."
            )
        return actor

    @classmethod
    def _normalize_type(cls, document_type: str) -> str:
        value = str(document_type).strip().upper()
        if value not in {choice[0] for choice in LegalDocument.DocumentType.choices}:
            raise ValueError(f"Invalid document_type: {value}")
        return value

    @classmethod
    def sanitize_content(cls, content_html: str) -> str:
        if not isinstance(content_html, str) or not content_html.strip():
            raise ValueError("content_html is required.")
        parser = _LegalHTMLSanitizer()
        parser.feed(content_html)
        parser.close()
        sanitized = parser.sanitized()
        if not sanitized:
            raise ValueError("content_html has no publishable content.")
        return sanitized

    @classmethod
    def create_draft(
        cls,
        *,
        document_type: str,
        title: str,
        version: str,
        content_html: str,
        effective_from,
        actor,
        slug: str | None = None,
        correlation_id: uuid.UUID | None = None,
        source: str = AuditLog.Source.WEB,
    ) -> LegalDocument:
        actor = cls._validate_actor(actor)
        document_type = cls._normalize_type(document_type)
        title = str(title).strip()
        version = str(version).strip()
        if not title or not version:
            raise ValueError("title and version are required.")
        normalized_slug = slugify(slug or title)
        if not normalized_slug:
            raise ValueError("A valid slug is required.")
        sanitized = cls.sanitize_content(content_html)
        digest = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
        correlation_id = correlation_id or uuid.uuid4()

        with transaction.atomic():
            document = LegalDocument.objects.create(
                document_type=document_type,
                title=title,
                slug=normalized_slug,
                version=version,
                content_html=sanitized,
                content_sha256=digest,
                effective_from=effective_from,
                is_published=False,
                created_by=actor,
            )
            AuditService.write(
                action="LEGAL_DOCUMENT_DRAFT_CREATED",
                entity_type="LegalDocument",
                actor=actor,
                source=source,
                correlation_id=correlation_id,
                entity_pk=document.id,
                description="Legal document draft created.",
                new_values={
                    "document_type": document_type,
                    "version": version,
                    "content_sha256": digest,
                    "is_published": False,
                },
            )
        return document

    @classmethod
    def publish(
        cls,
        *,
        document: LegalDocument,
        actor,
        correlation_id: uuid.UUID | None = None,
        source: str = AuditLog.Source.WEB,
    ) -> LegalDocument:
        actor = cls._validate_actor(actor)
        correlation_id = correlation_id or uuid.uuid4()
        with transaction.atomic():
            documents = list(
                LegalDocument.objects.select_for_update()
                .filter(document_type=document.document_type)
                .order_by("effective_from", "created_at")
            )
            locked = next((item for item in documents if item.pk == document.pk), None)
            if locked is None:
                raise LegalDocumentStateError("Legal document does not exist.")
            if locked.is_published:
                raise LegalDocumentStateError("Legal document is already published.")

            current_open = next(
                (
                    item for item in documents
                    if item.is_published and item.effective_to is None
                ),
                None,
            )
            if current_open is not None:
                if locked.effective_from <= current_open.effective_from:
                    raise LegalDocumentStateError(
                        "A new version must become effective after the open version."
                    )
                current_open.effective_to = locked.effective_from
                current_open.save(update_fields=["effective_to"])

            locked.is_published = True
            locked.save(update_fields=["is_published"])
            AuditService.write(
                action="LEGAL_DOCUMENT_PUBLISHED",
                entity_type="LegalDocument",
                actor=actor,
                source=source,
                correlation_id=correlation_id,
                entity_pk=locked.id,
                description="Legal document version published.",
                new_values={
                    "document_type": locked.document_type,
                    "version": locked.version,
                    "content_sha256": locked.content_sha256,
                    "is_published": True,
                },
                metadata={
                    "superseded_document_id": (
                        str(current_open.id) if current_open is not None else None
                    )
                },
            )
        return locked

    @classmethod
    def current(cls, *, document_type: str, at=None) -> LegalDocument | None:
        document_type = cls._normalize_type(document_type)
        at = at or timezone.now()
        return (
            LegalDocument.objects.filter(
                document_type=document_type,
                is_published=True,
                effective_from__lte=at,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at))
            .order_by("-effective_from")
            .first()
        )


class NoticeDeliveryService:
    @classmethod
    def record(
        cls,
        *,
        request,
        legal_document: LegalDocument,
        rendered_content: str,
        delivery_channel: str = NoticeDelivery.DeliveryChannel.WEB,
        acknowledged: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> NoticeDelivery:
        channel = str(delivery_channel).strip().upper()
        if channel not in {choice[0] for choice in NoticeDelivery.DeliveryChannel.choices}:
            raise ValueError(f"Invalid delivery_channel: {channel}")
        persisted_document = LegalDocument.objects.filter(
            pk=legal_document.pk,
            is_published=True,
        ).first()
        if persisted_document is None:
            raise LegalDocumentStateError(
                "Notice evidence requires a published legal document."
            )
        rendered_hash = hashlib.sha256(
            str(rendered_content).encode("utf-8")
        ).hexdigest()
        acknowledged_at = timezone.now() if acknowledged else None
        correlation_id = correlation_id or uuid.uuid4()

        with transaction.atomic():
            delivery = NoticeDelivery.objects.create(
                request=request,
                legal_document=persisted_document,
                delivery_channel=channel,
                acknowledged=acknowledged,
                acknowledged_at=acknowledged_at,
                ip_address=ip_address,
                user_agent=(str(user_agent)[:500] if user_agent else None),
                rendered_content_sha256=rendered_hash,
            )
            AuditService.write(
                action="NOTICE_DELIVERY_RECORDED",
                entity_type="NoticeDelivery",
                actor_type=AuditLog.ActorType.SYSTEM,
                source=(
                    AuditLog.Source.WEB
                    if channel == NoticeDelivery.DeliveryChannel.WEB
                    else AuditLog.Source.SYSTEM
                ),
                correlation_id=correlation_id,
                entity_pk=delivery.id,
                description="Legal notice delivery evidence recorded.",
                new_values={
                    "delivery_channel": channel,
                    "acknowledged": acknowledged,
                    "rendered_content_sha256": rendered_hash,
                },
                metadata={
                    "request_id": str(request.id),
                    "legal_document_id": str(persisted_document.id),
                },
            )
        return delivery
