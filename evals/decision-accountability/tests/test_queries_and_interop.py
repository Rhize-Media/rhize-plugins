from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from _support import (
    ACTOR,
    NONCE,
    NOW,
    PRINCIPAL,
    SCOPES,
    canonical_json,
    decision_bindings,
    proposal,
    record_one,
    sha256_value,
)
from graph_memory.decisions import (
    DecisionError,
    DecisionPreviewStore,
    DecisionQueryBudget,
    InMemoryDecisionLedger,
)
from graph_memory.prov_export import export_prov_o, validate_prov_o


class DecisionQueryAndInteropTests(unittest.TestCase):
    def _record_in(
        self,
        ledger: InMemoryDecisionLedger,
        item: dict,
        *,
        key: str,
        nonce: str,
    ) -> str:
        preview = ledger.preview(
            item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
            idempotency_key=key, nonce=nonce, now=NOW,
        )
        result = ledger.record(
            preview["previewId"], tenant_ref=item["tenantRef"], project_ref=item["projectRef"],
            actor_hash=ACTOR, workflow=item["workflow"], principal_hash=PRINCIPAL,
            principal_scopes=SCOPES, nonce=nonce, current_bindings=decision_bindings(item),
            role=ledger.RECORD_ROLE, now=NOW,
        )
        return result["record"]["decisionId"]

    def test_explain_denies_existence_inference_and_reports_revalidation_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger, item, decision_id, _ = record_one(Path(directory))
            denied = ledger.explain(
                decision_id, tenant_ref=item["tenantRef"], principal_hash=PRINCIPAL,
                principal_scopes=["group:other"], role=ledger.QUERY_ROLE,
            )
            empty = InMemoryDecisionLedger(DecisionPreviewStore(Path(directory) / "empty"))
            missing = empty.explain(
                decision_id, tenant_ref=item["tenantRef"], principal_hash=PRINCIPAL,
                principal_scopes=["group:other"], role=ledger.QUERY_ROLE,
            )
            self.assertEqual(denied, missing)
            visible = ledger.explain(
                decision_id, tenant_ref=item["tenantRef"], principal_hash=PRINCIPAL,
                principal_scopes=SCOPES, role=ledger.QUERY_ROLE,
                current_bindings=decision_bindings(item),
            )
            payload = canonical_json(visible)
            self.assertNotIn(item["tenantRef"], payload)
            self.assertNotIn("actor:fixture", payload)
            self.assertIn(ACTOR, payload)
            self.assertEqual(visible["receipt"]["warnings"], [])
            stale = decision_bindings(item)
            stale["policyDigest"] = sha256_value("replacement-policy")
            warning = ledger.explain(
                decision_id, tenant_ref=item["tenantRef"], principal_hash=PRINCIPAL,
                principal_scopes=SCOPES, role=ledger.QUERY_ROLE, current_bindings=stale,
            )
            self.assertIn("policy_stale", warning["receipt"]["warnings"])

    def test_impact_and_precedents_are_bounded_candidates_not_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = InMemoryDecisionLedger(DecisionPreviewStore(Path(directory)))
            first_item = proposal(source_revision="source-v1")
            second_item = proposal(source_revision="source-v2")
            second_item["source"]["idHash"] = sha256_value("RT-fixture-two")
            second_item["source"]["digest"] = sha256_value("RT-fixture-two:source-v2")
            first = self._record_in(ledger, first_item, key="first", nonce=NONCE)
            second = self._record_in(
                ledger, second_item, key="second", nonce="fixture-nonce-0002"
            )
            current = ledger.current(first)
            ledger.link_decisions(
                first, second, relationship_type="PRECEDENT_FOR",
                tenant_ref=first_item["tenantRef"], actor_hash=ACTOR,
                principal_scopes=SCOPES, expected_sequence=current["sequence"],
                expected_event_hash=current["currentEventHash"], idempotency_key="precedent-link",
                role=ledger.REVIEW_ROLE, reviewed=True, now=NOW,
            )
            impact = ledger.impact(
                first, tenant_ref=first_item["tenantRef"], principal_hash=PRINCIPAL,
                principal_scopes=SCOPES, role=ledger.QUERY_ROLE,
                budget=DecisionQueryBudget(depth=2, results=10, runtime_ms=250, max_bytes=8192),
            )
            self.assertEqual(impact["results"][0]["targetDecisionId"], second)
            self.assertTrue(impact["results"][0]["candidateOnly"])
            self.assertIn("candidate_not_authority", impact["receipt"]["warnings"])
            precedents = ledger.precedents(
                tenant_ref=first_item["tenantRef"], principal_hash=PRINCIPAL,
                principal_scopes=SCOPES, role=ledger.QUERY_ROLE,
                decision_class="promotion", domain="release-governance",
                current_policy_digest=sha256_value("different-policy"),
                budget=DecisionQueryBudget(results=1, max_bytes=4096),
            )
            self.assertEqual(len(precedents["results"]), 1)
            self.assertTrue(precedents["receipt"]["truncated"])
            self.assertTrue(precedents["results"][0]["policyMismatch"])
            with self.assertRaisesRegex(DecisionError, "depth exceeds"):
                ledger.impact(
                    first, tenant_ref=first_item["tenantRef"], principal_hash=PRINCIPAL,
                    principal_scopes=SCOPES, role=ledger.QUERY_ROLE,
                    budget=DecisionQueryBudget(depth=4),
                )

    def test_causality_is_disabled_by_default_and_requires_reviewed_deterministic_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = InMemoryDecisionLedger(DecisionPreviewStore(root / "disabled"))
            first_item = proposal(source_revision="source-v1")
            second_item = proposal(source_revision="source-v2")
            second_item["source"]["idHash"] = sha256_value("RT-causal-two")
            second_item["source"]["digest"] = sha256_value("RT-causal-two:v2")
            first = self._record_in(ledger, first_item, key="first", nonce=NONCE)
            second = self._record_in(ledger, second_item, key="second", nonce="fixture-nonce-0002")
            current = ledger.current(first)
            arguments = dict(
                source_decision_id=first, target_decision_id=second,
                relationship_type="CAUSED", tenant_ref=first_item["tenantRef"],
                actor_hash=ACTOR, principal_scopes=SCOPES, expected_sequence=current["sequence"],
                expected_event_hash=current["currentEventHash"], idempotency_key="cause",
                role=ledger.REVIEW_ROLE, evidence_digest=sha256_value("mechanism"),
                mechanism="deterministic", reviewed=True, now=NOW,
            )
            with self.assertRaisesRegex(DecisionError, "causality_disabled"):
                ledger.link_decisions(**arguments)

            enabled = InMemoryDecisionLedger(DecisionPreviewStore(root / "enabled"), causality_enabled=True)
            first = self._record_in(enabled, first_item, key="first", nonce=NONCE)
            second = self._record_in(enabled, second_item, key="second", nonce="fixture-nonce-0002")
            current = enabled.current(first)
            arguments.update(
                source_decision_id=first, target_decision_id=second,
                expected_sequence=current["sequence"], expected_event_hash=current["currentEventHash"],
            )
            unsafe = copy.deepcopy(arguments)
            unsafe["reviewed"] = False
            with self.assertRaisesRegex(DecisionError, "deterministic_reviewed"):
                enabled.link_decisions(**unsafe)
            enabled.link_decisions(**arguments)
            self.assertTrue(enabled.verify(first))

    def test_retention_purge_leaves_tombstone_and_prov_export_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger, item, decision_id, _ = record_one(Path(directory))
            record = ledger.current(decision_id)
            export = export_prov_o(record)
            validate_prov_o(export)
            self.assertEqual(export["rhize:authority"], "interoperability_view_only")
            self.assertNotIn(item["tenantRef"], canonical_json(export))
            with self.assertRaisesRegex(DecisionError, "retention_not_expired"):
                ledger.purge(
                    decision_id, tenant_ref=item["tenantRef"], actor_hash=ACTOR,
                    principal_scopes=SCOPES, expected_sequence=record["sequence"],
                    expected_event_hash=record["currentEventHash"], idempotency_key="early-purge",
                    role=ledger.REVIEW_ROLE, now=NOW,
                )
            purged = ledger.purge(
                decision_id, tenant_ref=item["tenantRef"], actor_hash=ACTOR,
                principal_scopes=SCOPES, expected_sequence=record["sequence"],
                expected_event_hash=record["currentEventHash"], idempotency_key="late-purge",
                role=ledger.REVIEW_ROLE, now=NOW + timedelta(days=2),
            )
            self.assertEqual(purged["record"]["status"], "purged")
            self.assertEqual(purged["record"]["evidenceSet"]["items"], [])
            with self.assertRaisesRegex(DecisionError, "purged decisions"):
                export_prov_o(ledger.current(decision_id))

    def test_fixed_preview_is_byte_equivalent_for_claude_and_codex_callers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item = proposal()
            first = InMemoryDecisionLedger(DecisionPreviewStore(Path(directory) / "claude"))
            second = InMemoryDecisionLedger(DecisionPreviewStore(Path(directory) / "codex"))
            arguments = dict(
                principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="host-parity", nonce=NONCE, now=NOW,
            )
            self.assertEqual(
                canonical_json(first.preview(item, **arguments)),
                canonical_json(second.preview(item, **arguments)),
            )


if __name__ == "__main__":
    unittest.main()
