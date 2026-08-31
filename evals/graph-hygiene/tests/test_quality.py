from __future__ import annotations

import json
import unittest

from hygiene_support import actor, candidate, h, leased_review, preview
from graph_memory.quality import build_quality_report
from graph_memory.review import IdentityReviewStore, current_candidate_state


class QualityTests(unittest.TestCase):
    def test_report_uses_explicit_denominators_and_contains_no_sensitive_rows(self) -> None:
        review = candidate()
        reviewer = actor("identity_reviewer")
        store = IdentityReviewStore()
        lease, leased = leased_review(store, review, reviewer)
        impact = preview(store, leased, reviewer, lease, "accept_same_as")
        store.decide(
            review["reviewId"], action="accept_same_as", rationale_code="verified_alias",
            expected_revision=leased["reviewRevision"], lease_token_hash=lease["leaseTokenHash"],
            preview_hash=impact["previewHash"], actor=reviewer,
            occurred_at="2026-08-30T14:03:00+00:00", idempotency_key="accept",
            current_state=current_candidate_state(leased),
        )
        current = store.show_review(review["reviewId"], actor=reviewer)
        report = build_quality_report(
            [current], store.ledger(tenant_hash=review["tenantHash"], namespace_hash=review["namespaceHash"], actor=reviewer), measured_at="2026-08-30T15:00:00+00:00",
            graphify_integrity={
                "status": "ok", "reportHash": h("graphify"), "extractionVersion": "1.0.0"
            },
            consolidation_status={
                "status": "no_change", "watermarkLagSeconds": 0, "pendingBacklog": 0
            },
            labeled_outcomes=[
                {
                    "entityType": "Topic", "expectedDisposition": "different",
                    "actualDisposition": "same", "protected": True, "cohort": "held_out",
                    "reviewerDisagreement": True,
                },
                {
                    "entityType": "Topic", "expectedDisposition": "same",
                    "actualDisposition": "same", "protected": False, "cohort": "held_out",
                    "reviewerDisagreement": False,
                },
            ],
            operational_counts={"poisonEvents": 2, "incompleteTrials": 1},
        )
        evaluation = report["byEntityType"]["Topic"]["labeledEvaluation"]["heldOut"]
        self.assertEqual(evaluation["falseAcceptanceDenominator"], 1)
        self.assertEqual(evaluation["falseAcceptanceRate"], 1.0)
        self.assertEqual(evaluation["reviewPrecisionDenominator"], 2)
        self.assertEqual(evaluation["reviewerDisagreementRate"], 0.5)
        self.assertIn("protected_false_acceptance", report["automationBlockers"])
        self.assertFalse(report["automationEligible"])
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(reviewer.actor_hash, serialized)
        self.assertNotIn(review["reviewId"], serialized)
        self.assertNotIn(review["candidateIds"][0], serialized)
        self.assertNotIn(review["tenantHash"], serialized)
        self.assertNotIn("Context Compiler", serialized)

    def test_graphify_failure_is_composed_not_reimplemented(self) -> None:
        report_hash = h("failed-integrity")
        report = build_quality_report(
            [], [], measured_at="2026-08-30T15:00:00+00:00",
            graphify_integrity={
                "status": "failed", "reportHash": report_hash, "extractionVersion": "2.0.0"
            },
            consolidation_status={
                "status": "ok", "watermarkLagSeconds": 0, "pendingBacklog": 0
            },
        )
        self.assertEqual(report["graphifyIntegrity"]["reportHash"], report_hash)
        self.assertIn("graphify_integrity", report["automationBlockers"])


if __name__ == "__main__":
    unittest.main()
