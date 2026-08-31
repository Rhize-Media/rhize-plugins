from __future__ import annotations

import copy
import json
import threading
import unittest
from dataclasses import replace

from hygiene_support import (
    NAMESPACE,
    NOW,
    TENANT,
    actor,
    candidate,
    entity,
    h,
    leased_review,
    policy,
    preview,
)
from graph_memory.dedup import generate_candidates
from graph_memory.review import (
    IdentityReviewStore,
    ReviewError,
    current_candidate_state,
)


class ForcedIdempotencyRaceStore(IdentityReviewStore):
    """Force the old lookup-before-mutation ordering into a deterministic race."""

    def __init__(self) -> None:
        super().__init__()
        self._race_lookup = False
        self._lookup_barrier = threading.Barrier(2)

    def arm_idempotency_race(self) -> None:
        self._race_lookup = True
        self._lookup_barrier = threading.Barrier(2)

    def _idempotency_lookup(self, idempotency_key, fingerprint, **scope):
        result = super()._idempotency_lookup(
            idempotency_key, fingerprint, **scope
        )
        if self._race_lookup and not self._lock._is_owned():
            self._lookup_barrier.wait(timeout=2)
        return result


def decide(
    store: IdentityReviewStore,
    review: dict,
    reviewer,
    lease: dict,
    impact: dict,
    *,
    action: str = "accept_same_as",
    rationale: str = "verified_alias",
    when: str = "2026-08-30T14:03:00+00:00",
    key: str = "decision-one",
    failure_at: str | None = None,
):
    return store.decide(
        review["reviewId"],
        action=action,
        rationale_code=rationale,
        expected_revision=review["reviewRevision"],
        lease_token_hash=lease["leaseTokenHash"],
        preview_hash=impact["previewHash"],
        actor=reviewer,
        occurred_at=when,
        idempotency_key=key,
        current_state=current_candidate_state(review),
        failure_at=failure_at,
    )


class ReviewTests(unittest.TestCase):
    def run_concurrently(self, operation):
        start = threading.Barrier(2)
        receipts = []
        errors = []

        def invoke() -> None:
            start.wait(timeout=2)
            try:
                receipts.append(operation())
            except Exception as error:  # captured so both threads always join
                errors.append(error)

        threads = [threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[0], receipts[1])
        return receipts[0]

    def test_authorized_accept_is_logged_logical_and_source_preserving(self) -> None:
        source = [entity("a", "Same"), entity("b", "Same")]
        source_bytes = json.dumps(source, sort_keys=True).encode()
        review = candidate(*source)
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        receipt = decide(store, leased, reviewer, lease, impact)

        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(len(store.ledger(tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"], actor=reviewer)), 1)
        self.assertEqual(list(store.projection(tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"], actor=reviewer).values()), [review["candidateIds"]])
        self.assertEqual(json.dumps(source, sort_keys=True).encode(), source_bytes)
        self.assertNotIn("label", json.dumps(receipt))

    def test_changed_accepted_evidence_removes_stale_projection_and_queues_review(self) -> None:
        source = [entity("a", "Same"), entity("b", "Same")]
        review = candidate(*source)
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        accepted = decide(store, leased, reviewer, lease, impact)

        changed_source = copy.deepcopy(source)
        changed_source[0]["sourceRevisionHash"] = h("revision:a:v2")
        successor = generate_candidates(
            changed_source,
            policy=policy(),
            tenant_hash=review["tenantHash"],
            namespace_hash=review["namespaceHash"],
            created_at="2026-08-30T15:00:00+00:00",
            origin="ingest",
        )["candidates"][0]
        result = store.enqueue_candidates(
            [successor],
            actor=actor("identity_ingest"),
            occurred_at="2026-08-30T15:00:00+00:00",
        )

        self.assertEqual(result, {"queued": 1, "replayed": 0, "suppressed": 0, "superseded": 1})
        self.assertEqual(store.show_review(review["reviewId"], actor=reviewer)["state"], "superseded")
        self.assertEqual(store.show_review(successor["reviewId"], actor=reviewer)["state"], "pending")
        self.assertEqual(
            store.projection(
                tenant_hash=review["tenantHash"],
                namespace_hash=review["namespaceHash"],
                actor=reviewer,
            ),
            {},
        )
        events = store.ledger(
            tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"], actor=reviewer
        )
        self.assertEqual([event["eventType"] for event in events], ["ACCEPT_SAME_AS", "SUPERSEDE"])
        self.assertEqual(events[-1]["reversalOfDecisionId"], accepted["decisionId"])

    def test_same_partition_actor_without_candidate_acl_cannot_read_or_transition(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        denied = actor(
            "identity_reviewer",
            "denied",
            acl_scope_hashes=frozenset({h("rhize:other")}),
        )
        store = IdentityReviewStore()
        store.enqueue_candidates([review], actor=reviewer, occurred_at=NOW)

        self.assertEqual(
            store.list_reviews(
                tenant_hash=review["tenantHash"],
                namespace_hash=review["namespaceHash"],
                actor=denied,
            )["results"],
            [],
        )
        with self.assertRaisesRegex(ReviewError, "ACL scope"):
            store.show_review(review["reviewId"], actor=denied)
        with self.assertRaisesRegex(ReviewError, "ACL scope"):
            store.lease(
                review["reviewId"],
                expected_revision=review["reviewRevision"],
                actor=denied,
                now=NOW,
                lease_expires_at="2026-08-30T14:30:00+00:00",
                idempotency_key="denied-lease",
            )
        other_scope_review = candidate(
            entity("a", "Context Compiler", acl=["rhize:other"]),
            entity("b", "Context Compiler", acl=["rhize:other"]),
        )
        self.assertEqual(
            store.enqueue_candidates(
                [other_scope_review], actor=denied, occurred_at=NOW
            ),
            {"queued": 1, "replayed": 0, "suppressed": 0, "superseded": 0},
        )
        with self.assertRaisesRegex(ReviewError, "ACL scope"):
            store.show_review(other_scope_review["reviewId"], actor=reviewer)

    def test_same_entity_pair_in_disjoint_acl_lanes_has_isolated_review_state(self) -> None:
        internal = candidate()
        restricted = candidate(
            entity("a", "Context Compiler", acl=["rhize:restricted"]),
            entity("b", "Context Compiler", acl=["rhize:restricted"]),
        )
        internal_reviewer = actor("identity_reviewer")
        restricted_reviewer = actor(
            "identity_reviewer",
            "restricted",
            acl_scope_hashes=frozenset({h("rhize:restricted")}),
        )
        store = IdentityReviewStore()

        self.assertEqual(internal["candidateIds"], restricted["candidateIds"])
        self.assertNotEqual(internal["pairKey"], restricted["pairKey"])
        self.assertNotEqual(internal["reviewId"], restricted["reviewId"])
        store.enqueue_candidates([internal], actor=internal_reviewer, occurred_at=NOW)
        store.enqueue_candidates([restricted], actor=restricted_reviewer, occurred_at=NOW)

        internal_results = store.list_reviews(
            tenant_hash=internal["tenantHash"],
            namespace_hash=internal["namespaceHash"],
            actor=internal_reviewer,
        )["results"]
        restricted_results = store.list_reviews(
            tenant_hash=restricted["tenantHash"],
            namespace_hash=restricted["namespaceHash"],
            actor=restricted_reviewer,
        )["results"]
        self.assertEqual(
            [result["reviewId"] for result in internal_results],
            [internal["reviewId"]],
        )
        self.assertEqual(
            [result["reviewId"] for result in restricted_results],
            [restricted["reviewId"]],
        )

        lease = store.lease(
            internal["reviewId"],
            expected_revision=internal["reviewRevision"],
            actor=internal_reviewer,
            now="2026-08-30T14:01:00+00:00",
            lease_expires_at="2026-08-30T14:31:00+00:00",
            idempotency_key="internal-lease",
        )
        leased = store.show_review(internal["reviewId"], actor=internal_reviewer)
        impact = preview(
            store, leased, internal_reviewer, lease, "accept_same_as"
        )
        decide(store, leased, internal_reviewer, lease, impact, key="internal-accept")

        self.assertEqual(
            store.show_review(restricted["reviewId"], actor=restricted_reviewer)["state"],
            "pending",
        )
        self.assertEqual(
            store.projection(
                tenant_hash=restricted["tenantHash"],
                namespace_hash=restricted["namespaceHash"],
                actor=restricted_reviewer,
            ),
            {},
        )
        with self.assertRaisesRegex(ReviewError, "ACL scope"):
            store.show_review(internal["reviewId"], actor=restricted_reviewer)

    def test_preview_and_reversal_hide_dependencies_outside_actor_acl(self) -> None:
        shared_acl = ["rhize:internal", "rhize:restricted"]
        shared = candidate(
            entity("a", "Context Compiler", acl=shared_acl),
            entity("b", "Context Compiler", acl=shared_acl),
        )
        restricted = candidate(
            entity("b", "Context Compiler", acl=["rhize:restricted"]),
            entity("c", "Context Compiler", acl=["rhize:restricted"]),
        )
        internal_reviewer = actor("identity_reviewer")
        restricted_reviewer = actor(
            "identity_reviewer",
            "restricted",
            acl_scope_hashes=frozenset({h("rhize:restricted")}),
        )
        store = IdentityReviewStore()

        shared_lease, shared_leased = leased_review(
            store, shared, internal_reviewer, key="shared-lease"
        )
        shared_impact = preview(
            store, shared_leased, internal_reviewer, shared_lease, "accept_same_as"
        )
        shared_receipt = decide(
            store,
            shared_leased,
            internal_reviewer,
            shared_lease,
            shared_impact,
            key="shared-accept",
        )

        restricted_lease, restricted_leased = leased_review(
            store,
            restricted,
            restricted_reviewer,
            now="2026-08-30T14:04:00+00:00",
            expires="2026-08-30T14:34:00+00:00",
            key="restricted-lease",
        )
        restricted_impact = preview(
            store,
            restricted_leased,
            restricted_reviewer,
            restricted_lease,
            "accept_same_as",
            now="2026-08-30T14:05:00+00:00",
        )
        restricted_receipt = decide(
            store,
            restricted_leased,
            restricted_reviewer,
            restricted_lease,
            restricted_impact,
            when="2026-08-30T14:06:00+00:00",
            key="restricted-accept",
        )
        restricted_event = next(
            event
            for event in store.ledger(
                tenant_hash=restricted["tenantHash"],
                namespace_hash=restricted["namespaceHash"],
                actor=restricted_reviewer,
            )
            if event["decisionId"] == restricted_receipt["decisionId"]
        )
        self.assertIn(
            shared_receipt["decisionId"], restricted_event["dependsOnDecisionIds"]
        )

        accepted_shared = store.show_review(shared["reviewId"], actor=internal_reviewer)
        reverse_lease = store.lease(
            shared["reviewId"],
            expected_revision=accepted_shared["reviewRevision"],
            actor=internal_reviewer,
            now="2026-08-30T14:10:00+00:00",
            lease_expires_at="2026-08-30T14:30:00+00:00",
            idempotency_key="shared-reverse-lease",
        )
        accepted_shared = store.show_review(shared["reviewId"], actor=internal_reviewer)
        impact = preview(
            store,
            accepted_shared,
            internal_reviewer,
            reverse_lease,
            "reverse_same_as",
            now="2026-08-30T14:11:00+00:00",
        )

        self.assertEqual(set(impact["currentClusterMemberIds"]), set(shared["candidateIds"]))
        self.assertEqual(impact["blockedByDecisionIds"], [])
        self.assertTrue(impact["canApply"])
        internal_view = json.dumps(impact, sort_keys=True)
        self.assertNotIn(h("entity:c"), internal_view)
        self.assertNotIn(restricted_receipt["decisionId"], internal_view)

        store.reverse(
            shared["reviewId"],
            rationale_code="distinct_entities",
            expected_revision=accepted_shared["reviewRevision"],
            lease_token_hash=reverse_lease["leaseTokenHash"],
            preview_hash=impact["previewHash"],
            actor=internal_reviewer,
            occurred_at="2026-08-30T14:12:00+00:00",
            idempotency_key="shared-reverse",
            current_state=current_candidate_state(accepted_shared),
        )
        self.assertEqual(
            store.projection(
                tenant_hash=shared["tenantHash"],
                namespace_hash=shared["namespaceHash"],
                actor=internal_reviewer,
            ),
            {},
        )
        restricted_projection = store.projection(
            tenant_hash=restricted["tenantHash"],
            namespace_hash=restricted["namespaceHash"],
            actor=restricted_reviewer,
        )
        self.assertEqual(
            {tuple(members) for members in restricted_projection.values()},
            {tuple(restricted["candidateIds"])},
        )

    def test_multi_authorized_actor_is_limited_to_current_review_acl_lane(self) -> None:
        internal = candidate(
            entity("a", "Context Compiler", acl=["rhize:internal"]),
            entity("b", "Context Compiler", acl=["rhize:internal"]),
        )
        restricted = candidate(
            entity("b", "Context Compiler", acl=["rhize:restricted"]),
            entity("c", "Context Compiler", acl=["rhize:restricted"]),
        )
        restricted_reviewer = actor(
            "identity_reviewer",
            "restricted-lane",
            acl_scope_hashes=frozenset({h("rhize:restricted")}),
        )
        multi_reviewer = actor(
            "identity_reviewer",
            "multi-lane",
            acl_scope_hashes=frozenset(
                {h("rhize:internal"), h("rhize:restricted")}
            ),
        )
        internal_auditor = actor("identity_auditor", "internal-auditor")
        store = IdentityReviewStore()

        restricted_lease, restricted_leased = leased_review(
            store,
            restricted,
            restricted_reviewer,
            now="2026-08-30T15:00:00+00:00",
            expires="2026-08-30T15:30:00+00:00",
            key="restricted-lane-lease",
        )
        restricted_impact = preview(
            store,
            restricted_leased,
            restricted_reviewer,
            restricted_lease,
            "accept_same_as",
            now="2026-08-30T15:01:00+00:00",
        )
        restricted_receipt = decide(
            store,
            restricted_leased,
            restricted_reviewer,
            restricted_lease,
            restricted_impact,
            when="2026-08-30T15:02:00+00:00",
            key="restricted-lane-accept",
        )

        internal_lease, internal_leased = leased_review(
            store,
            internal,
            multi_reviewer,
            now="2026-08-30T15:03:00+00:00",
            expires="2026-08-30T15:33:00+00:00",
            key="internal-lane-lease",
        )
        internal_impact = preview(
            store,
            internal_leased,
            multi_reviewer,
            internal_lease,
            "accept_same_as",
            now="2026-08-30T15:04:00+00:00",
        )
        serialized_preview = json.dumps(internal_impact, sort_keys=True)
        self.assertEqual(
            set(internal_impact["currentClusterMemberIds"]),
            set(internal["candidateIds"]),
        )
        self.assertNotIn(h("entity:c"), serialized_preview)
        self.assertNotIn(restricted_receipt["decisionId"], serialized_preview)

        decide(
            store,
            internal_leased,
            multi_reviewer,
            internal_lease,
            internal_impact,
            when="2026-08-30T15:05:00+00:00",
            key="internal-lane-accept",
        )
        internal_ledger = json.dumps(
            store.ledger(
                tenant_hash=internal["tenantHash"],
                namespace_hash=internal["namespaceHash"],
                actor=internal_auditor,
            ),
            sort_keys=True,
        )
        self.assertNotIn(h("entity:c"), internal_ledger)
        self.assertNotIn(restricted_receipt["decisionId"], internal_ledger)

    def test_multi_authorized_ingester_supersedes_only_current_review_acl_lane(self) -> None:
        internal = candidate(
            entity("a", "Context Compiler", acl=["rhize:internal"]),
            entity("b", "Context Compiler", acl=["rhize:internal"]),
        )
        restricted = candidate(
            entity("b", "Context Compiler", acl=["rhize:restricted"]),
            entity("c", "Context Compiler", acl=["rhize:restricted"]),
        )
        internal_reviewer = actor("identity_reviewer", "internal-lane")
        restricted_reviewer = actor(
            "identity_reviewer",
            "restricted-lane",
            acl_scope_hashes=frozenset({h("rhize:restricted")}),
        )
        multi_ingester = replace(
            actor(
                "identity_reviewer",
                "multi-lane-ingester",
                acl_scope_hashes=frozenset(
                    {h("rhize:internal"), h("rhize:restricted")}
                ),
            ),
            roles=frozenset({"identity_reviewer", "identity_ingest"}),
        )
        store = IdentityReviewStore()

        internal_lease, internal_leased = leased_review(
            store,
            internal,
            internal_reviewer,
            now="2026-08-30T16:00:00+00:00",
            expires="2026-08-30T16:30:00+00:00",
            key="internal-first-lease",
        )
        internal_impact = preview(
            store,
            internal_leased,
            internal_reviewer,
            internal_lease,
            "accept_same_as",
            now="2026-08-30T16:01:00+00:00",
        )
        internal_receipt = decide(
            store,
            internal_leased,
            internal_reviewer,
            internal_lease,
            internal_impact,
            when="2026-08-30T16:02:00+00:00",
            key="internal-first-accept",
        )

        restricted_lease, restricted_leased = leased_review(
            store,
            restricted,
            restricted_reviewer,
            now="2026-08-30T16:03:00+00:00",
            expires="2026-08-30T16:33:00+00:00",
            key="restricted-second-lease",
        )
        restricted_impact = preview(
            store,
            restricted_leased,
            restricted_reviewer,
            restricted_lease,
            "accept_same_as",
            now="2026-08-30T16:04:00+00:00",
        )
        restricted_receipt = decide(
            store,
            restricted_leased,
            restricted_reviewer,
            restricted_lease,
            restricted_impact,
            when="2026-08-30T16:05:00+00:00",
            key="restricted-second-accept",
        )

        changed_a = entity("a", "Context Compiler", acl=["rhize:internal"])
        changed_a["sourceRevisionHash"] = h("revision:a:v2")
        successor = candidate(
            changed_a,
            entity("b", "Context Compiler", acl=["rhize:internal"]),
        )
        result = store.enqueue_candidates(
            [successor],
            actor=multi_ingester,
            occurred_at="2026-08-30T16:06:00+00:00",
        )

        self.assertEqual(
            result,
            {"queued": 1, "replayed": 0, "suppressed": 0, "superseded": 1},
        )
        supersession = store.ledger(
            tenant_hash=internal["tenantHash"],
            namespace_hash=internal["namespaceHash"],
            actor=internal_reviewer,
        )[-1]
        serialized_event = json.dumps(supersession, sort_keys=True)
        self.assertEqual(supersession["reversalOfDecisionId"], internal_receipt["decisionId"])
        self.assertNotIn(h("entity:c"), serialized_event)
        self.assertNotIn(restricted_receipt["decisionId"], serialized_event)

    def test_idempotency_keys_are_isolated_across_partitions_and_acl_lanes(self) -> None:
        tenant_b = h("tenant-b")
        namespace_b = h("namespace-b")

        def partition_review(tenant_hash, namespace_hash, suffix):
            return generate_candidates(
                [
                    entity(
                        f"{suffix}-a",
                        "Context Compiler",
                        tenant_hash=tenant_hash,
                        namespace_hash=namespace_hash,
                    ),
                    entity(
                        f"{suffix}-b",
                        "Context Compiler",
                        tenant_hash=tenant_hash,
                        namespace_hash=namespace_hash,
                    ),
                ],
                policy=policy(),
                tenant_hash=tenant_hash,
                namespace_hash=namespace_hash,
                created_at=NOW,
                origin="manual",
            )["candidates"][0]

        partitioned = [
            candidate(),
            partition_review(tenant_b, NAMESPACE, "tenant-b"),
            partition_review(TENANT, namespace_b, "namespace-b"),
        ]
        reviewer = replace(
            actor("identity_reviewer", "multi-partition"),
            authorized_partitions=frozenset(
                (review["tenantHash"], review["namespaceHash"])
                for review in partitioned
            ),
        )
        store = IdentityReviewStore()
        for review in partitioned:
            store.enqueue_candidates([review], actor=reviewer, occurred_at=NOW)
        receipts = [
            store.lease(
                review["reviewId"],
                expected_revision=review["reviewRevision"],
                actor=reviewer,
                now="2026-08-30T14:01:00+00:00",
                lease_expires_at="2026-08-30T14:31:00+00:00",
                idempotency_key="caller-retry-key",
            )
            for review in partitioned
        ]
        self.assertEqual(len({receipt["idempotencyKeyHash"] for receipt in receipts}), 3)

        internal = candidate()
        restricted = candidate(
            entity("a", "Context Compiler", acl=["rhize:restricted"]),
            entity("b", "Context Compiler", acl=["rhize:restricted"]),
        )
        lane_reviewer = actor(
            "identity_reviewer",
            "all-lanes",
            acl_scope_hashes=frozenset(
                {h("rhize:internal"), h("rhize:restricted")}
            ),
        )
        acl_store = IdentityReviewStore()
        acl_store.enqueue_candidates([internal], actor=lane_reviewer, occurred_at=NOW)
        acl_store.enqueue_candidates([restricted], actor=lane_reviewer, occurred_at=NOW)
        internal_receipt = acl_store.lease(
            internal["reviewId"],
            expected_revision=internal["reviewRevision"],
            actor=lane_reviewer,
            now="2026-08-30T14:01:00+00:00",
            lease_expires_at="2026-08-30T14:31:00+00:00",
            idempotency_key="same-acl-lane-key",
        )
        restricted_receipt = acl_store.lease(
            restricted["reviewId"],
            expected_revision=restricted["reviewRevision"],
            actor=lane_reviewer,
            now="2026-08-30T14:01:00+00:00",
            lease_expires_at="2026-08-30T14:31:00+00:00",
            idempotency_key="same-acl-lane-key",
        )
        self.assertNotEqual(
            internal_receipt["idempotencyKeyHash"],
            restricted_receipt["idempotencyKeyHash"],
        )

    def test_concurrent_same_key_lease_returns_one_atomic_receipt(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = ForcedIdempotencyRaceStore()
        store.enqueue_candidates([review], actor=reviewer, occurred_at=NOW)
        store.arm_idempotency_race()

        receipt = self.run_concurrently(
            lambda: store.lease(
                review["reviewId"],
                expected_revision=review["reviewRevision"],
                actor=reviewer,
                now="2026-08-30T14:01:00+00:00",
                lease_expires_at="2026-08-30T14:31:00+00:00",
                idempotency_key="concurrent-lease",
            )
        )
        self.assertEqual(receipt["status"], "leased")

    def test_concurrent_same_key_decision_returns_one_atomic_receipt(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = ForcedIdempotencyRaceStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        store.arm_idempotency_race()

        receipt = self.run_concurrently(
            lambda: decide(
                store,
                leased,
                reviewer,
                lease,
                impact,
                key="concurrent-decision",
            )
        )
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(
            len(
                store.ledger(
                    tenant_hash=review["tenantHash"],
                    namespace_hash=review["namespaceHash"],
                    actor=reviewer,
                )
            ),
            1,
        )

    def test_concurrent_same_key_reversal_returns_one_atomic_receipt(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = ForcedIdempotencyRaceStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        decide(store, leased, reviewer, lease, impact)
        accepted = store.show_review(review["reviewId"], actor=reviewer)
        reverse_lease = store.lease(
            review["reviewId"],
            expected_revision=accepted["reviewRevision"],
            actor=reviewer,
            now="2026-08-30T14:10:00+00:00",
            lease_expires_at="2026-08-30T14:30:00+00:00",
            idempotency_key="concurrent-reverse-lease",
        )
        accepted = store.show_review(review["reviewId"], actor=reviewer)
        reverse_impact = preview(
            store,
            accepted,
            reviewer,
            reverse_lease,
            "reverse_same_as",
            now="2026-08-30T14:11:00+00:00",
        )
        store.arm_idempotency_race()

        receipt = self.run_concurrently(
            lambda: store.reverse(
                review["reviewId"],
                rationale_code="distinct_entities",
                expected_revision=accepted["reviewRevision"],
                lease_token_hash=reverse_lease["leaseTokenHash"],
                preview_hash=reverse_impact["previewHash"],
                actor=reviewer,
                occurred_at="2026-08-30T14:12:00+00:00",
                idempotency_key="concurrent-reverse",
                current_state=current_candidate_state(accepted),
            )
        )
        self.assertEqual(receipt["status"], "reversed")
        self.assertEqual(
            store.projection(
                tenant_hash=review["tenantHash"],
                namespace_hash=review["namespaceHash"],
                actor=reviewer,
            ),
            {},
        )

    def test_authority_cas_lease_expiry_and_stale_state_are_enforced(self) -> None:
        review = candidate()
        store = IdentityReviewStore()
        reviewers = [actor("identity_reviewer", "one"), actor("identity_reviewer", "two")]
        store.enqueue_candidates([review], actor=reviewers[0], occurred_at=NOW)
        with self.assertRaises(ReviewError):
            store.lease(
                review["reviewId"], expected_revision=review["reviewRevision"],
                actor=actor("identity_auditor"), now=NOW,
                lease_expires_at="2026-08-30T14:30:00+00:00", idempotency_key="bad",
            )

        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def compete(index: int) -> None:
            barrier.wait()
            try:
                store.lease(
                    review["reviewId"], expected_revision=review["reviewRevision"],
                    actor=reviewers[index], now=NOW,
                    lease_expires_at="2026-08-30T14:30:00+00:00",
                    idempotency_key=f"race-{index}",
                )
                outcomes.append("leased")
            except ReviewError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=compete, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ["leased", "rejected"])

        leased = store.show_review(review["reviewId"], actor=reviewers[0])
        owner = next(reviewer for reviewer in reviewers if reviewer.actor_hash == leased["lease"]["actorHash"])
        with self.assertRaises(ReviewError):
            store.preview(
                review["reviewId"], operation="accept_same_as",
                expected_revision=leased["reviewRevision"],
                lease_token_hash=leased["lease"]["tokenHash"], actor=owner,
                now="2026-08-30T14:31:00+00:00",
                current_state=current_candidate_state(leased),
            )

        reclaimed = store.lease(
            review["reviewId"], expected_revision=leased["reviewRevision"], actor=reviewers[0],
            now="2026-08-30T14:31:00+00:00", lease_expires_at="2026-08-30T15:00:00+00:00",
            idempotency_key="reclaim",
        )
        current = store.show_review(review["reviewId"], actor=reviewers[0])
        stale = current_candidate_state(current)
        stale["candidateRevision"] = h("stale")
        with self.assertRaises(ReviewError):
            store.preview(
                review["reviewId"], operation="accept_same_as",
                expected_revision=current["reviewRevision"],
                lease_token_hash=reclaimed["leaseTokenHash"], actor=reviewers[0],
                now="2026-08-30T14:32:00+00:00", current_state=stale,
            )

    def test_failure_injection_cannot_diverge_decision_ledger_and_projection(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        with self.assertRaisesRegex(ReviewError, "injected failure"):
            decide(store, leased, reviewer, lease, impact, failure_at="after_transition_staged")
        current = store.show_review(review["reviewId"], actor=reviewer)
        self.assertEqual(current["state"], "leased")
        self.assertEqual(store.ledger(tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"], actor=reviewer), [])
        self.assertEqual(store.projection(tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"], actor=reviewer), {})

    def test_rejection_suppresses_unchanged_candidate_and_is_idempotent(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "reject_same_as")
        first = decide(
            store, leased, reviewer, lease, impact,
            action="reject_same_as", rationale="distinct_entities", key="reject",
        )
        replay = decide(
            store, leased, reviewer, lease, impact,
            action="reject_same_as", rationale="distinct_entities", key="reject",
        )
        self.assertEqual(first, replay)
        enqueue = store.enqueue_candidates([review], actor=reviewer, occurred_at="2026-08-30T14:04:00+00:00")
        self.assertEqual(enqueue["suppressed"], 1)
        self.assertIn(review["candidateRevision"], store.suppressed_candidate_revisions(tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"]))

    def test_dependency_aware_reverse_restores_golden_projection(self) -> None:
        a, b, c = entity("a", "Same"), entity("b", "Same"), entity("c", "Same")
        first, second = candidate(a, b), candidate(b, c)
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()

        lease_one, leased_one = leased_review(store, first, reviewer, key="lease-ab")
        impact_one = preview(store, leased_one, reviewer, lease_one, "accept_same_as")
        decide(store, leased_one, reviewer, lease_one, impact_one, key="accept-ab")

        lease_two, leased_two = leased_review(store, second, reviewer, key="lease-bc")
        impact_two = preview(store, leased_two, reviewer, lease_two, "accept_same_as")
        decide(store, leased_two, reviewer, lease_two, impact_two, key="accept-bc")

        accepted_one = store.show_review(first["reviewId"], actor=reviewer)
        reverse_lease_one = store.lease(
            first["reviewId"], expected_revision=accepted_one["reviewRevision"], actor=reviewer,
            now="2026-08-30T14:10:00+00:00", lease_expires_at="2026-08-30T14:30:00+00:00",
            idempotency_key="reverse-lease-ab",
        )
        accepted_one = store.show_review(first["reviewId"], actor=reviewer)
        blocked = preview(
            store, accepted_one, reviewer, reverse_lease_one, "reverse_same_as",
            now="2026-08-30T14:11:00+00:00",
        )
        self.assertFalse(blocked["canApply"])
        self.assertEqual(len(blocked["blockedByDecisionIds"]), 1)

        self._reverse(store, second, reviewer, "bc", "2026-08-30T14:12:00+00:00")
        accepted_one = store.show_review(first["reviewId"], actor=reviewer)
        unblocked = preview(
            store, accepted_one, reviewer, reverse_lease_one, "reverse_same_as",
            now="2026-08-30T14:16:00+00:00",
        )
        store.reverse(
            first["reviewId"], rationale_code="distinct_entities",
            expected_revision=accepted_one["reviewRevision"],
            lease_token_hash=reverse_lease_one["leaseTokenHash"],
            preview_hash=unblocked["previewHash"], actor=reviewer,
            occurred_at="2026-08-30T14:16:00+00:00", idempotency_key="reverse-ab",
            current_state=current_candidate_state(accepted_one),
        )
        self.assertEqual(store.projection(tenant_hash=first["tenantHash"], namespace_hash=first["namespaceHash"], actor=reviewer), {})

    def test_non_source_bound_dependency_blocks_reversal(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        decide(store, leased, reviewer, lease, impact)
        accepted = store.show_review(review["reviewId"], actor=reviewer)
        reverse_lease = store.lease(
            review["reviewId"], expected_revision=accepted["reviewRevision"], actor=reviewer,
            now="2026-08-30T14:10:00+00:00", lease_expires_at="2026-08-30T14:30:00+00:00",
            idempotency_key="reverse-lease",
        )
        accepted = store.show_review(review["reviewId"], actor=reviewer)
        dependency = [{
            "dependencyHash": h("claim"), "kind": "claim", "immutableSourceBound": False,
            "sourceRevisionHash": h("claim-revision"),
        }]
        impact = preview(
            store, accepted, reviewer, reverse_lease, "reverse_same_as",
            now="2026-08-30T14:11:00+00:00",
            dependencies=dependency,
        )
        self.assertFalse(impact["canApply"])
        with self.assertRaisesRegex(ReviewError, "blocked by dependency"):
            store.reverse(
                review["reviewId"], rationale_code="dependency_blocked",
                expected_revision=accepted["reviewRevision"],
                lease_token_hash=reverse_lease["leaseTokenHash"], preview_hash=impact["previewHash"],
                actor=reviewer, occurred_at="2026-08-30T14:12:00+00:00",
                idempotency_key="blocked", current_state=current_candidate_state(accepted),
                dependency_snapshot=dependency,
            )

    def test_partition_authorization_and_governed_ids_prevent_side_channels(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        outsider = replace(
            reviewer,
            actor_hash=h("outsider"),
            authorized_partitions=frozenset({(h("other-tenant"), review["namespaceHash"])}),
        )
        store = IdentityReviewStore()
        store.enqueue_candidates([review], actor=reviewer, occurred_at=NOW)
        for operation in (
            lambda: store.show_review(review["reviewId"], actor=outsider),
            lambda: store.list_reviews(
                tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"],
                actor=outsider,
            ),
            lambda: store.ledger(
                tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"],
                actor=outsider,
            ),
            lambda: store.projection(
                tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"],
                actor=outsider,
            ),
        ):
            with self.assertRaisesRegex(ReviewError, "not authorized for this partition"):
                operation()

        forged = copy.deepcopy(review)
        forged["reviewId"] = h("forged")
        with self.assertRaisesRegex(ReviewError, "governed ids"):
            IdentityReviewStore().enqueue_candidates(
                [forged], actor=reviewer, occurred_at=NOW
            )
        tampered = copy.deepcopy(review)
        tampered["trustSummary"] = "medium"
        with self.assertRaisesRegex(ReviewError, "does not bind its governed evidence"):
            IdentityReviewStore().enqueue_candidates(
                [tampered], actor=reviewer, occurred_at=NOW
            )

    def test_idempotency_key_cannot_rebind_to_changed_decision_inputs(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "reject_same_as")
        decide(
            store, leased, reviewer, lease, impact, action="reject_same_as",
            rationale="distinct_entities", key="bound-decision",
        )
        with self.assertRaisesRegex(ReviewError, "bound to another operation"):
            decide(
                store, leased, reviewer, lease, impact, action="reject_same_as",
                rationale="scope_collision", key="bound-decision",
            )

    @staticmethod
    def _reverse(store, initial, reviewer, suffix, when):
        accepted = store.show_review(initial["reviewId"], actor=reviewer)
        lease = store.lease(
            initial["reviewId"], expected_revision=accepted["reviewRevision"], actor=reviewer,
            now=when, lease_expires_at="2026-08-30T14:50:00+00:00",
            idempotency_key=f"reverse-lease-{suffix}",
        )
        accepted = store.show_review(initial["reviewId"], actor=reviewer)
        impact = preview(
            store, accepted, reviewer, lease, "reverse_same_as", now=when,
        )
        return store.reverse(
            initial["reviewId"], rationale_code="distinct_entities",
            expected_revision=accepted["reviewRevision"], lease_token_hash=lease["leaseTokenHash"],
            preview_hash=impact["previewHash"], actor=reviewer, occurred_at=when,
            idempotency_key=f"reverse-{suffix}", current_state=current_candidate_state(accepted),
        )


if __name__ == "__main__":
    unittest.main()
