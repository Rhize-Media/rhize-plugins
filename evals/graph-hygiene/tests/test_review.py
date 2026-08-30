from __future__ import annotations

import copy
import json
import threading
import unittest
from dataclasses import replace

from hygiene_support import (
    NOW,
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
        with self.assertRaisesRegex(ReviewError, "ACL scope"):
            store.enqueue_candidates(
                [other_scope_review], actor=denied, occurred_at=NOW
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
