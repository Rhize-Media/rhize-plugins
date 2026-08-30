from __future__ import annotations

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from decision_support import (
    ACTOR,
    NONCE,
    NOW,
    PRINCIPAL,
    SCOPES,
    correction_approval,
    decision_bindings,
    proposal,
    record_one,
    sha256_value,
)
from graph_memory.decisions import DecisionError, DecisionPreviewStore, InMemoryDecisionLedger


class DecisionLifecycleTests(unittest.TestCase):
    def test_concurrent_record_claim_has_one_winner_and_no_split_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item = proposal()
            ledger = InMemoryDecisionLedger(DecisionPreviewStore(Path(directory)))
            preview = ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="race-record", nonce=NONCE, now=NOW,
            )
            arguments = dict(
                preview_id=preview["previewId"], tenant_ref=item["tenantRef"],
                project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                principal_hash=PRINCIPAL, principal_scopes=SCOPES, nonce=NONCE,
                current_bindings=decision_bindings(item), role=ledger.RECORD_ROLE, now=NOW,
            )

            def attempt():
                try:
                    return ledger.record(**arguments)
                except DecisionError as exc:
                    return str(exc)

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: attempt(), range(2)))
            winners = [result for result in results if isinstance(result, dict)]
            self.assertEqual(len(winners), 1)
            self.assertIn("preview_replayed", results)
            decision_id = winners[0]["record"]["decisionId"]
            self.assertEqual(len(ledger.events(decision_id)), 1)
            self.assertTrue(ledger.verify(decision_id))

    def test_preview_is_private_bound_short_lived_and_single_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "previews"
            item = proposal()
            ledger = InMemoryDecisionLedger(DecisionPreviewStore(root))
            preview = ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="one", nonce=NONCE, now=NOW, ttl_seconds=60,
            )
            path = root / f"{preview['previewId']}.json"
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(DecisionError, "binding_mismatch"):
                ledger.record(
                    preview["previewId"], tenant_ref=item["tenantRef"],
                    project_ref=item["projectRef"], actor_hash=ACTOR,
                    workflow={"id": "other", "revision": "workflow-v1"},
                    principal_hash=PRINCIPAL, principal_scopes=SCOPES, nonce=NONCE,
                    current_bindings=decision_bindings(item), role=ledger.RECORD_ROLE, now=NOW,
                )
            result = ledger.record(
                preview["previewId"], tenant_ref=item["tenantRef"],
                project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                principal_hash=PRINCIPAL, principal_scopes=SCOPES, nonce=NONCE,
                current_bindings=decision_bindings(item), role=ledger.RECORD_ROLE, now=NOW,
            )
            self.assertFalse(result["replayed"])
            with self.assertRaisesRegex(DecisionError, "preview_replayed"):
                ledger.record(
                    preview["previewId"], tenant_ref=item["tenantRef"],
                    project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                    principal_hash=PRINCIPAL, principal_scopes=SCOPES, nonce=NONCE,
                    current_bindings=decision_bindings(item), role=ledger.RECORD_ROLE, now=NOW,
                )

    def test_expired_stale_and_wrong_authority_previews_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DecisionPreviewStore(Path(directory))
            ledger = InMemoryDecisionLedger(store)
            item = proposal()
            preview = ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="expired", nonce=NONCE, now=NOW, ttl_seconds=1,
            )
            common = dict(
                preview_id=preview["previewId"], tenant_ref=item["tenantRef"],
                project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                principal_hash=PRINCIPAL, principal_scopes=SCOPES, nonce=NONCE,
                current_bindings=decision_bindings(item), role=ledger.RECORD_ROLE,
            )
            with self.assertRaisesRegex(DecisionError, "preview_expired"):
                ledger.record(**common, now=NOW + timedelta(seconds=2))

            preview = ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="stale", nonce="fixture-nonce-0002", now=NOW,
            )
            stale = decision_bindings(item)
            stale["policyDigest"] = sha256_value("new-policy")
            with self.assertRaisesRegex(DecisionError, "preview_stale"):
                ledger.record(
                    preview["previewId"], tenant_ref=item["tenantRef"], project_ref=item["projectRef"],
                    actor_hash=ACTOR, workflow=item["workflow"], principal_hash=PRINCIPAL,
                    principal_scopes=SCOPES, nonce="fixture-nonce-0002", current_bindings=stale,
                    role=ledger.RECORD_ROLE, now=NOW,
                )
            with self.assertRaisesRegex(DecisionError, "role_not_authorized"):
                ledger.record(
                    preview["previewId"], tenant_ref=item["tenantRef"], project_ref=item["projectRef"],
                    actor_hash=ACTOR, workflow=item["workflow"], principal_hash=PRINCIPAL,
                    principal_scopes=SCOPES, nonce="fixture-nonce-0002",
                    current_bindings=decision_bindings(item), role=ledger.QUERY_ROLE, now=NOW,
                )

    def test_record_idempotency_cas_and_failure_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, item, decision_id, result = record_one(root)
            self.assertTrue(ledger.verify(decision_id))
            self.assertEqual(ledger.current(decision_id)["sequence"], 1)

            second_preview = ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="decision-one", nonce="fixture-nonce-0002", now=NOW,
            )
            replay = ledger.record(
                second_preview["previewId"], tenant_ref=item["tenantRef"],
                project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                principal_hash=PRINCIPAL, principal_scopes=SCOPES, nonce="fixture-nonce-0002",
                current_bindings=decision_bindings(item), role=ledger.RECORD_ROLE, now=NOW,
            )
            self.assertTrue(replay["replayed"])
            self.assertEqual(len(ledger.events(decision_id)), 1)

            failed_ledger = InMemoryDecisionLedger(DecisionPreviewStore(root / "failed"))
            failed_preview = failed_ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="failure", nonce="fixture-nonce-fail", now=NOW,
            )
            with self.assertRaisesRegex(DecisionError, "injected_failure"):
                failed_ledger.record(
                    failed_preview["previewId"], tenant_ref=item["tenantRef"],
                    project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                    principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                    nonce="fixture-nonce-fail", current_bindings=decision_bindings(item),
                    role=failed_ledger.RECORD_ROLE, failure_at="before_commit", now=NOW,
                )
            failed_id = sha256_value([item["tenantRef"], item["source"]["idHash"], sha256_value("failure")])
            self.assertIsNone(failed_ledger.current(failed_id))
            self.assertEqual(failed_ledger.events(failed_id), [])

    def test_competing_transition_writers_have_one_cas_owner_and_failure_keeps_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger, item, decision_id, _ = record_one(Path(directory))
            original = ledger.current(decision_id)
            with self.assertRaisesRegex(DecisionError, "injected_failure"):
                ledger.record_effect(
                    decision_id, system="github", action="merge",
                    effect_idempotency_key="failed-effect", tenant_ref=item["tenantRef"],
                    actor_hash=ACTOR, principal_scopes=SCOPES,
                    expected_sequence=original["sequence"],
                    expected_event_hash=original["currentEventHash"],
                    transition_idempotency_key="failed-transition", role=ledger.RECORD_ROLE,
                    failure_at="before_commit", now=NOW,
                )
            self.assertEqual(ledger.current(decision_id), original)
            self.assertTrue(ledger.verify(decision_id))

            evidence_id = item["evidenceSet"]["items"][0]["evidenceId"]

            def effect():
                return ledger.record_effect(
                    decision_id, system="github", action="merge", effect_idempotency_key="race-effect",
                    tenant_ref=item["tenantRef"], actor_hash=ACTOR, principal_scopes=SCOPES,
                    expected_sequence=original["sequence"],
                    expected_event_hash=original["currentEventHash"],
                    transition_idempotency_key="race-effect-transition", role=ledger.RECORD_ROLE, now=NOW,
                )

            def invalidate():
                return ledger.invalidate_evidence(
                    decision_id, evidence_id=evidence_id, tenant_ref=item["tenantRef"],
                    actor_hash=ACTOR, principal_scopes=SCOPES,
                    expected_sequence=original["sequence"],
                    expected_event_hash=original["currentEventHash"],
                    idempotency_key="race-invalidate", role=ledger.REVIEW_ROLE, now=NOW,
                )

            def run(operation):
                try:
                    return operation()
                except DecisionError as exc:
                    return str(exc)

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, [effect, invalidate]))
            self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
            self.assertIn("stale_writer", results)
            self.assertEqual(ledger.current(decision_id)["sequence"], 2)
            self.assertTrue(ledger.verify(decision_id))

    def test_effect_outcome_correction_and_evidence_invalidation_remain_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger, item, decision_id, _ = record_one(Path(directory))
            first = ledger.current(decision_id)
            effect_result = ledger.record_effect(
                decision_id, system="github", action="merge", effect_idempotency_key="merge-one",
                tenant_ref=item["tenantRef"], actor_hash=ACTOR, principal_scopes=SCOPES,
                expected_sequence=1, expected_event_hash=first["currentEventHash"],
                transition_idempotency_key="transition-effect", role=ledger.RECORD_ROLE, now=NOW,
            )
            after_effect = ledger.current(decision_id)
            self.assertEqual(after_effect["effects"][0]["status"], "attempted")
            self.assertEqual(after_effect["outcomes"], [])
            exact_retry = ledger.record_effect(
                decision_id, system="github", action="merge", effect_idempotency_key="merge-one",
                tenant_ref=item["tenantRef"], actor_hash=ACTOR, principal_scopes=SCOPES,
                expected_sequence=1, expected_event_hash=first["currentEventHash"],
                transition_idempotency_key="transition-effect", role=ledger.RECORD_ROLE, now=NOW,
            )
            self.assertTrue(exact_retry["replayed"])
            with self.assertRaisesRegex(DecisionError, "stale_writer"):
                ledger.correct(
                    decision_id, kind="corrected", reason_code="policy_clarified",
                    correction_approval=correction_approval(), tenant_ref=item["tenantRef"],
                    actor_hash=ACTOR, principal_scopes=SCOPES, expected_sequence=1,
                    expected_event_hash=first["currentEventHash"], idempotency_key="stale-correction",
                    role=ledger.REVIEW_ROLE, now=NOW,
                )
            effect_id = after_effect["effects"][0]["effectId"]
            ledger.observe_outcome(
                decision_id, effect_id=effect_id, source_receipt_hash=sha256_value("github-receipt"),
                source_revision="merge-sha", status="succeeded", tenant_ref=item["tenantRef"],
                actor_hash=ACTOR, principal_scopes=SCOPES,
                expected_sequence=effect_result["record"]["sequence"],
                expected_event_hash=effect_result["record"]["currentEventHash"],
                idempotency_key="outcome-one", role=ledger.RECORD_ROLE, now=NOW,
            )
            after_outcome = ledger.current(decision_id)
            self.assertEqual(after_outcome["effects"][0]["status"], "attempted")
            self.assertEqual(after_outcome["outcomes"][0]["status"], "succeeded")

            evidence_id = item["evidenceSet"]["items"][0]["evidenceId"]
            ledger.invalidate_evidence(
                decision_id, evidence_id=evidence_id, tenant_ref=item["tenantRef"],
                actor_hash=ACTOR, principal_scopes=SCOPES,
                expected_sequence=after_outcome["sequence"],
                expected_event_hash=after_outcome["currentEventHash"],
                idempotency_key="invalidate-one", role=ledger.REVIEW_ROLE, now=NOW,
            )
            invalidated = ledger.current(decision_id)
            self.assertEqual(invalidated["evidenceSet"], item["evidenceSet"])
            self.assertIn("evidence_invalidated", invalidated["staleReasons"])
            corrected = ledger.correct(
                decision_id, kind="corrected", reason_code="policy_clarified",
                correction_approval=correction_approval(), tenant_ref=item["tenantRef"],
                actor_hash=ACTOR, principal_scopes=SCOPES,
                expected_sequence=invalidated["sequence"],
                expected_event_hash=invalidated["currentEventHash"],
                idempotency_key="correction-one", role=ledger.REVIEW_ROLE, now=NOW,
            )
            self.assertEqual(corrected["record"]["status"], "corrected")
            self.assertEqual(len(corrected["record"]["corrections"]), 1)
            self.assertTrue(ledger.verify(decision_id))

            replay_preview = ledger.preview(
                item, principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                idempotency_key="decision-one", nonce="fixture-nonce-replay", now=NOW,
            )
            original_result = ledger.record(
                replay_preview["previewId"], tenant_ref=item["tenantRef"],
                project_ref=item["projectRef"], actor_hash=ACTOR, workflow=item["workflow"],
                principal_hash=PRINCIPAL, principal_scopes=SCOPES,
                nonce="fixture-nonce-replay", current_bindings=decision_bindings(item),
                role=ledger.RECORD_ROLE, now=NOW,
            )
            self.assertTrue(original_result["replayed"])
            self.assertEqual(original_result["record"]["status"], "accepted")
            self.assertEqual(ledger.current(decision_id)["status"], "corrected")


if __name__ == "__main__":
    unittest.main()
