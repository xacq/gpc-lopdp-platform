import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.audit.services.audit import (
    AuditActorError,
    AuditChainIntegrityError,
    AuditService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"A" * 32
).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={
        1: ENCRYPTION_KEY,
    },
)
class AuditServiceTests(TestCase):

    def create_actor(
        self,
        *,
        email="auditor@example.com",
        is_active=True,
    ):
        user_model = get_user_model()

        return user_model.objects.create_user(
            email=email,
            password="TestPassword123!",
            full_name="Usuario Auditor",
            is_active=is_active,
        )

    def test_first_entry_starts_global_chain(self):
        entry = AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="SYSTEM_BOOTSTRAP",
            entity_type="SYSTEM",
        )

        self.assertEqual(
            entry.chain_scope,
            "GLOBAL",
        )
        self.assertEqual(
            entry.chain_position,
            1,
        )
        self.assertIsNone(
            entry.previous_hash
        )
        self.assertEqual(
            len(entry.entry_hash),
            64,
        )

    def test_second_entry_links_previous_hash(self):
        first = AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="FIRST",
            entity_type="SYSTEM",
        )

        actor = self.create_actor()

        second = AuditService.write(
            actor_type="USER",
            actor=actor,
            source="WEB",
            action="SECOND",
            entity_type="RIGHTS_REQUEST",
            entity_pk="request-1",
        )

        self.assertEqual(
            second.chain_position,
            2,
        )
        self.assertEqual(
            second.previous_hash,
            first.entry_hash,
        )

    def test_user_entry_requires_active_persisted_actor(self):
        inactive_actor = self.create_actor(
            email="inactive@example.com",
            is_active=False,
        )

        with self.assertRaises(
            AuditActorError
        ):
            AuditService.write(
                actor_type="USER",
                actor=inactive_actor,
                source="WEB",
                action="INVALID_ACTOR",
                entity_type="TEST",
            )

        self.assertEqual(
            AuditLog.objects.count(),
            0,
        )

    def test_system_entry_rejects_user_actor(self):
        actor = self.create_actor()

        with self.assertRaises(
            AuditActorError
        ):
            AuditService.write(
                actor_type="SYSTEM",
                actor=actor,
                source="SYSTEM",
                action="INVALID_SYSTEM_ACTOR",
                entity_type="TEST",
            )

        self.assertEqual(
            AuditLog.objects.count(),
            0,
        )

    def test_structured_values_are_sanitized(self):
        entry = AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="SANITIZE",
            entity_type="TEST",
            previous_values={
                "status": "PENDING",
                "email": "person@example.com",
                "document_number": "1712345678",
            },
            new_values={
                "status": "VERIFIED",
                "nested": {
                    "token": "super-secret-token",
                    "safe": "ok",
                },
            },
            metadata={
                "correlation_note": (
                    "Contact user@example.com"
                ),
                "password": "secret",
            },
        )

        self.assertEqual(
            entry.previous_values["status"],
            "PENDING",
        )
        self.assertEqual(
            entry.previous_values["email"],
            "[REDACTED]",
        )
        self.assertEqual(
            entry.previous_values[
                "document_number"
            ],
            "[REDACTED]",
        )
        self.assertEqual(
            entry.new_values[
                "nested"
            ]["token"],
            "[REDACTED]",
        )
        self.assertEqual(
            entry.new_values[
                "nested"
            ]["safe"],
            "ok",
        )
        self.assertEqual(
            entry.metadata["password"],
            "[REDACTED]",
        )
        self.assertNotIn(
            "user@example.com",
            entry.metadata[
                "correlation_note"
            ],
        )

    def test_reason_is_encrypted(self):
        plaintext_reason = (
            "Justificación interna reservada"
        )

        entry = AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="REASON_TEST",
            entity_type="TEST",
            reason=plaintext_reason,
        )

        self.assertIsNotNone(
            entry.reason_encrypted
        )

        self.assertNotIn(
            plaintext_reason.encode("utf-8"),
            bytes(
                entry.reason_encrypted
            ),
        )

    def test_verify_chain_accepts_valid_chain(self):
        AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="FIRST",
            entity_type="TEST",
        )

        AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="SECOND",
            entity_type="TEST",
        )

        result = AuditService.verify_chain()

        self.assertEqual(
            result.chain_scope,
            "GLOBAL",
        )
        self.assertEqual(
            result.checked_entries,
            2,
        )

    def test_verify_chain_detects_tampering(self):
        entry = AuditService.write(
            actor_type="SYSTEM",
            actor=None,
            source="SYSTEM",
            action="ORIGINAL",
            entity_type="TEST",
            metadata={
                "safe": "original",
            },
        )

        AuditLog.objects.filter(
            pk=entry.pk
        ).update(
            metadata={
                "safe": "tampered",
            }
        )

        with self.assertRaises(
            AuditChainIntegrityError
        ):
            AuditService.verify_chain()
