from __future__ import annotations

import unittest
from dataclasses import replace

from hygiene_support import NAMESPACE, TENANT, actor, entity, policy
from graph_memory.consolidate import (
    INITIAL_WATERMARK_REVISION,
    ConsolidationError,
    ProposalConsolidator,
)
from graph_memory.review import IdentityReviewStore


class ConsolidationTests(unittest.TestCase):
    def test_same_timestamp_watermark_has_stable_tie_break_and_no_duplicate_reviews(self) -> None:
        rows = [
            entity("a", "Same", recorded_at="2026-08-30T13:00:00+00:00"),
            entity("b", "Same", recorded_at="2026-08-30T13:00:00+00:00"),
        ]
        store = IdentityReviewStore()
        consolidator = ProposalConsolidator()
        ingester = actor("identity_ingest")
        first = consolidator.run(
            rows, policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
            expected_watermark_revision=INITIAL_WATERMARK_REVISION, actor=ingester,
            review_store=store, run_at="2026-08-30T14:00:00+00:00",
            idempotency_key="first", batch_size=1,
        )
        second = consolidator.run(
            rows, policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
            expected_watermark_revision=first["watermarkRevision"], actor=ingester,
            review_store=store, run_at="2026-08-30T14:01:00+00:00",
            idempotency_key="second", batch_size=1,
        )
        self.assertNotEqual(first["watermarkRevision"], second["watermarkRevision"])
        self.assertEqual(store.counts()["pending"], 1)
        self.assertEqual(second["enqueueCounts"]["replayed"], 1)
        final = consolidator.run(
            rows, policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
            expected_watermark_revision=second["watermarkRevision"], actor=ingester,
            review_store=store, run_at="2026-08-30T14:02:00+00:00",
            idempotency_key="third", batch_size=1,
        )
        self.assertEqual(final["status"], "no_change")

    def test_interruption_after_enqueue_replays_without_skipping_or_duplication(self) -> None:
        rows = [entity("a", "Same"), entity("b", "Same")]
        store = IdentityReviewStore()
        consolidator = ProposalConsolidator()
        arguments = dict(
            policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
            expected_watermark_revision=INITIAL_WATERMARK_REVISION,
            actor=actor("identity_ingest"), review_store=store,
            run_at="2026-08-30T14:00:00+00:00", idempotency_key="retry", batch_size=2,
        )
        with self.assertRaisesRegex(ConsolidationError, "after consolidation enqueue"):
            consolidator.run(rows, failure_at="after_enqueue", **arguments)
        self.assertEqual(store.counts()["pending"], 1)
        self.assertEqual(
            consolidator.status(
                tenant_hash=TENANT, namespace_hash=NAMESPACE, actor=arguments["actor"]
            )["watermarkRevision"],
            INITIAL_WATERMARK_REVISION,
        )
        receipt = consolidator.run(rows, **arguments)
        self.assertEqual(receipt["enqueueCounts"]["replayed"], 1)
        self.assertEqual(store.counts()["pending"], 1)

    def test_backlog_pause_does_not_advance_watermark(self) -> None:
        rows = [entity("a", "Same"), entity("b", "Same")]
        store = IdentityReviewStore()
        consolidator = ProposalConsolidator()
        first = consolidator.run(
            rows, policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
            expected_watermark_revision=INITIAL_WATERMARK_REVISION,
            actor=actor("identity_ingest"), review_store=store,
            run_at="2026-08-30T14:00:00+00:00", idempotency_key="seed", batch_size=2,
        )
        later = [entity("c", "Later", recorded_at="2026-08-30T15:00:00+00:00")]
        paused = consolidator.run(
            later, policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
            expected_watermark_revision=first["watermarkRevision"],
            actor=actor("identity_ingest"), review_store=store,
            run_at="2026-08-30T15:30:00+00:00", idempotency_key="paused",
            backlog_limit=1,
        )
        self.assertEqual(paused["status"], "paused_backlog")
        self.assertEqual(paused["watermarkRevision"], first["watermarkRevision"])

    def test_status_and_runs_are_partition_bound(self) -> None:
        consolidator = ProposalConsolidator()
        ingester = actor("identity_ingest")
        outsider = replace(
            ingester,
            authorized_partitions=frozenset({("0" * 64, NAMESPACE)}),
        )
        with self.assertRaisesRegex(ConsolidationError, "not authorized for this partition"):
            consolidator.status(
                tenant_hash=TENANT, namespace_hash=NAMESPACE, actor=outsider
            )
        with self.assertRaisesRegex(ConsolidationError, "not authorized for this partition"):
            consolidator.run(
                [], policy=policy(), tenant_hash=TENANT, namespace_hash=NAMESPACE,
                expected_watermark_revision=INITIAL_WATERMARK_REVISION, actor=outsider,
                review_store=IdentityReviewStore(), run_at="2026-08-30T14:00:00+00:00",
                idempotency_key="forbidden",
            )


if __name__ == "__main__":
    unittest.main()
