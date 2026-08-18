import threading
import uuid

from django.db import (
    close_old_connections,
)
from django.test import TransactionTestCase

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService


class AuditConcurrencyTests(
    TransactionTestCase
):
    reset_sequences = True

    def _write_entry(
        self,
        *,
        index: int,
        errors: list,
    ):
        close_old_connections()

        try:
            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.SYSTEM
                ),
                actor=None,
                source=(
                    AuditLog.Source.SYSTEM
                ),
                correlation_id=uuid.uuid4(),
                action=(
                    "CONCURRENCY_TEST_EVENT"
                ),
                entity_type=(
                    "CONCURRENCY_TEST"
                ),
                entity_pk=str(index),
                description=(
                    "Concurrent audit test event."
                ),
                metadata={
                    "index": index,
                },
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    def test_concurrent_writes_preserve_global_chain(self):
        thread_count = 8
        errors = []

        threads = [
            threading.Thread(
                target=self._write_entry,
                kwargs={
                    "index": index,
                    "errors": errors,
                },
            )
            for index in range(
                thread_count
            )
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(
                timeout=20
            )

        self.assertFalse(
            any(
                thread.is_alive()
                for thread in threads
            )
        )

        self.assertEqual(
            errors,
            [],
        )

        entries = list(
            AuditLog.objects
            .filter(
                action=(
                    "CONCURRENCY_TEST_EVENT"
                )
            )
            .order_by(
                "chain_position"
            )
        )

        self.assertEqual(
            len(entries),
            thread_count,
        )

        positions = [
            entry.chain_position
            for entry in entries
        ]

        self.assertEqual(
            positions,
            list(
                range(
                    positions[0],
                    positions[0]
                    + thread_count,
                )
            ),
        )

        self.assertEqual(
            len({
                entry.entry_hash
                for entry in entries
            }),
            thread_count,
        )

    def test_concurrent_entries_link_previous_hash(self):
        thread_count = 6
        errors = []

        threads = [
            threading.Thread(
                target=self._write_entry,
                kwargs={
                    "index": index,
                    "errors": errors,
                },
            )
            for index in range(
                thread_count
            )
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(
                timeout=20
            )

        self.assertEqual(
            errors,
            [],
        )

        entries = list(
            AuditLog.objects
            .filter(
                action=(
                    "CONCURRENCY_TEST_EVENT"
                )
            )
            .order_by(
                "chain_position"
            )
        )

        self.assertEqual(
            len(entries),
            thread_count,
        )

        for previous, current in zip(
            entries,
            entries[1:],
        ):
            self.assertEqual(
                current.previous_hash,
                previous.entry_hash,
            )
