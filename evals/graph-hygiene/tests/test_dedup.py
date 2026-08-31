from __future__ import annotations

import unittest
from unittest.mock import patch

from hygiene_support import NAMESPACE, NOW, TENANT, deterministic, entity, h, policy
from graph_memory.dedup import generate_candidates
from graph_memory.resolution import HygieneError


class DedupTests(unittest.TestCase):
    def generate(self, entities, **kwargs):
        return generate_candidates(
            entities,
            policy=kwargs.pop("candidate_policy", policy()),
            tenant_hash=TENANT,
            namespace_hash=NAMESPACE,
            created_at=NOW,
            **kwargs,
        )

    def test_fuzzy_match_is_pending_only_and_reproducible(self) -> None:
        rows = [entity("a", "Rhize Context"), entity("b", "Rhize Context")]
        first = self.generate(rows)
        second = self.generate(rows)
        self.assertEqual(first, second)
        self.assertEqual(first["candidates"][0]["state"], "pending")
        self.assertIsNone(first["candidates"][0]["decisionId"])
        self.assertNotIn("accepted", first)
        self.assertLessEqual(first["counts"]["noCandidate"], first["counts"]["input"])

    def test_partition_acl_type_and_trust_gates(self) -> None:
        with self.assertRaises(HygieneError):
            self.generate([entity("a", "Name"), entity("b", "Name", tenant_hash=h("other"))])
        acl = self.generate(
            [entity("a", "Name", acl=["scope:a"]), entity("b", "Name", acl=["scope:b"])]
        )
        self.assertEqual(acl["candidates"], [])
        typed = self.generate(
            [entity("a", "Name", entity_type="Topic"), entity("b", "Name", entity_type="Organization")]
        )
        self.assertEqual(typed["candidates"], [])
        low = self.generate([entity("a", "Name", trust="low"), entity("b", "Name")])
        self.assertEqual(low["candidates"], [])

    def test_deterministic_identity_bypasses_fuzzy_and_protected_types_never_fuzzy(self) -> None:
        match = self.generate(
            [
                entity("a", "One", entity_type="Repository", deterministic_identity=deterministic("repo")),
                entity("b", "Two", entity_type="Repository", deterministic_identity=deterministic("repo")),
            ]
        )
        self.assertEqual(len(match["deterministicMatches"]), 1)
        self.assertEqual(match["candidates"], [])
        mismatch = self.generate(
            [
                entity("a", "Same", entity_type="Repository", deterministic_identity=deterministic("one")),
                entity("b", "Same", entity_type="Repository", deterministic_identity=deterministic("two")),
            ]
        )
        self.assertEqual(mismatch["deterministicMatches"], [])
        self.assertEqual(mismatch["candidates"], [])

    def test_source_type_and_pair_budgets_isolate_floods(self) -> None:
        flooded = [entity(str(i), "Same", source_ref="one-source") for i in range(3)]
        result = self.generate(
            flooded,
            candidate_policy=policy(max_entities_per_source=2, max_pair_comparisons=2),
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["counts"]["eligible"], 0)
        self.assertEqual(len(result["pausedSourceTypeHashes"]), 1)
        pair_limited = self.generate(
            [entity(str(i), "Same", source_ref=str(i)) for i in range(4)],
            candidate_policy=policy(max_pair_comparisons=1),
        )
        self.assertTrue(pair_limited["pairBudgetExceeded"])

    def test_rejected_revision_is_suppressed(self) -> None:
        rows = [entity("a", "Same"), entity("b", "Same")]
        first = self.generate(rows)
        revision = first["candidates"][0]["candidateRevision"]
        replay = self.generate(rows, suppressed_candidate_revisions=[revision])
        self.assertEqual(replay["candidates"], [])
        self.assertEqual(replay["counts"]["suppressed"], 1)

    def test_candidate_revision_binds_acl_trust_and_evidence_versions(self) -> None:
        high = self.generate([entity("a", "Same"), entity("b", "Same")])
        medium = self.generate(
            [entity("a", "Same", trust="medium"), entity("b", "Same")]
        )
        self.assertNotEqual(
            high["candidates"][0]["candidateRevision"],
            medium["candidates"][0]["candidateRevision"],
        )

    def test_pair_keys_bind_acl_lanes_for_fuzzy_and_deterministic_matches(self) -> None:
        internal = self.generate(
            [entity("a", "Same"), entity("b", "Same")]
        )["candidates"][0]
        restricted = self.generate(
            [
                entity("a", "Same", acl=["rhize:restricted"]),
                entity("b", "Same", acl=["rhize:restricted"]),
            ]
        )["candidates"][0]
        self.assertEqual(internal["candidateIds"], restricted["candidateIds"])
        self.assertNotEqual(internal["pairKey"], restricted["pairKey"])

        deterministic_internal = self.generate(
            [
                entity(
                    "a",
                    "One",
                    entity_type="Repository",
                    deterministic_identity=deterministic("repo"),
                ),
                entity(
                    "b",
                    "Two",
                    entity_type="Repository",
                    deterministic_identity=deterministic("repo"),
                ),
            ]
        )["deterministicMatches"][0]
        deterministic_restricted = self.generate(
            [
                entity(
                    "a",
                    "One",
                    entity_type="Repository",
                    acl=["rhize:restricted"],
                    deterministic_identity=deterministic("repo"),
                ),
                entity(
                    "b",
                    "Two",
                    entity_type="Repository",
                    acl=["rhize:restricted"],
                    deterministic_identity=deterministic("repo"),
                ),
            ]
        )["deterministicMatches"][0]
        self.assertEqual(
            deterministic_internal["candidateIds"],
            deterministic_restricted["candidateIds"],
        )
        self.assertNotEqual(
            deterministic_internal["pairKey"],
            deterministic_restricted["pairKey"],
        )

    def test_global_input_budget_is_enforced_before_unbounded_materialization(self) -> None:
        rows = [entity(str(index), "Same") for index in range(3)]
        with patch("graph_memory.dedup.MAX_INPUT_ENTITIES", 2):
            with self.assertRaisesRegex(HygieneError, "governed entity budget"):
                self.generate(rows)


if __name__ == "__main__":
    unittest.main()
