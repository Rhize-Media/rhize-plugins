from __future__ import annotations

import copy
import unittest

from _support import compilation, load_fixture, ontology
from graph_memory.contract import canonical_json, sha256_value
from graph_memory.store import InMemoryNeo4jAdapter, QueryBudget, StoreError
from graph_memory.translate import GraphifyTranslator


class StagePublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryNeo4jAdapter(ontology())
        self.store.apply_migrations(role="migration_admin")
        self.first = compilation(source_revision="revision-1")

    def _partition(self, item):
        return item["tenantKey"], item["namespaceKey"], item["corpusKey"]

    def test_roles_migrations_and_idempotent_receipt(self) -> None:
        unauthorized = InMemoryNeo4jAdapter(ontology())
        with self.assertRaisesRegex(StoreError, "not authorized"):
            unauthorized.apply_migrations(role="ingest")
        first = self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        replay = self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        self.assertEqual(first, replay)
        alternate_key = self.store.ingest(
            self.first, role="ingest", idempotency_key="same-compilation", expected_current=None
        )
        self.assertEqual(alternate_key["status"], "replayed")
        self.assertEqual(alternate_key["compilationHash"], first["compilationHash"])
        snapshot = self.store.backup(role="migration_admin")
        restored = InMemoryNeo4jAdapter(ontology())
        restored.restore(snapshot, role="migration_admin")
        self.assertEqual(restored.current_compilation(*self._partition(self.first)), first["compilationHash"])
        receipt_text = canonical_json(first)
        self.assertNotIn("tenant-a", receipt_text)
        self.assertNotIn("/redacted/", receipt_text)

    def test_failures_before_publication_keep_previous_compilation_visible(self) -> None:
        accepted = self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        second = compilation(source_revision="revision-2")
        for failure in ("after_validation", "after_stage", "before_publish"):
            candidate = compilation(source_revision=f"revision-{failure}")
            with self.assertRaisesRegex(StoreError, "injected failure"):
                self.store.ingest(
                    candidate,
                    role="ingest",
                    idempotency_key=failure,
                    expected_current=accepted["compilationHash"],
                    failure_at=failure,
                )
            self.assertEqual(
                self.store.current_compilation(*self._partition(self.first)),
                accepted["compilationHash"],
            )
        second_receipt = self.store.ingest(
            second,
            role="ingest",
            idempotency_key="second",
            expected_current=accepted["compilationHash"],
        )
        self.assertEqual(second_receipt["status"], "accepted")

    def test_competing_revision_has_named_loser_state(self) -> None:
        first_receipt = self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        loser = compilation(source_revision="revision-loser")
        self.store.stage(loser, role="ingest", idempotency_key="loser")
        with self.assertRaisesRegex(StoreError, "optimistic publication rejected"):
            self.store.publish(
                loser["compilationId"], role="ingest", expected_current="0" * 64
            )
        self.assertEqual(self.store.compilation_status(loser["compilationId"]), "rejected")
        self.assertEqual(
            self.store.current_compilation(*self._partition(self.first)),
            first_receipt["compilationHash"],
        )

    def test_queries_enforce_partition_acl_trust_and_budget(self) -> None:
        self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        tenant_key, namespace_key, corpus_key = self._partition(self.first)
        visible = self.store.query(
            "query_context",
            tenant_key=tenant_key,
            namespace_key=namespace_key,
            corpus_key=corpus_key,
            principal_scopes=["group:rhize-tools"],
            role="query",
            query_text="ontology",
        )
        self.assertTrue(visible["results"])
        self.assertFalse(any("Ignore all previous" in canonical_json(row) for row in visible["results"]))
        denied = self.store.query(
            "query_context",
            tenant_key=tenant_key,
            namespace_key=namespace_key,
            corpus_key=corpus_key,
            principal_scopes=["group:other"],
            role="query",
            query_text="ontology",
        )
        wrong_tenant = self.store.query(
            "query_context",
            tenant_key="0" * 64,
            namespace_key=namespace_key,
            corpus_key=corpus_key,
            principal_scopes=["group:rhize-tools"],
            role="query",
            query_text="ontology",
        )
        self.assertEqual(denied, wrong_tenant)
        with self.assertRaisesRegex(StoreError, "depth exceeds"):
            self.store.query(
                "query_context",
                tenant_key=tenant_key,
                namespace_key=namespace_key,
                corpus_key=corpus_key,
                principal_scopes=["group:rhize-tools"],
                role="query",
                budget=QueryBudget(depth=4),
                query_text="ontology",
            )

    def test_all_agent_shaped_query_operations_are_bounded(self) -> None:
        self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        partition = self._partition(self.first)
        claim = next(
            record for record in self.first["records"]
            if record["recordType"] == "Claim"
            and record["properties"]["predicate"] == "implements"
        )
        sources = self.store.query(
            "get_claim_sources",
            tenant_key=partition[0], namespace_key=partition[1], corpus_key=partition[2],
            principal_scopes=["group:rhize-tools"], role="query", record_id=claim["governedId"],
        )
        self.assertEqual({row["recordType"] for row in sources["results"]}, {"Source"})
        entity_id = claim["properties"]["objectId"]
        artifacts = self.store.query(
            "get_related_artifacts",
            tenant_key=partition[0], namespace_key=partition[1], corpus_key=partition[2],
            principal_scopes=["group:rhize-tools"], role="query", record_id=entity_id,
            budget=QueryBudget(depth=2, results=10, runtime_ms=250),
        )
        self.assertEqual({row["recordType"] for row in artifacts["results"]}, {"Artifact"})

    def test_new_revision_reconciles_a_deleted_source_record(self) -> None:
        first_receipt = self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        graph = load_fixture("graph.json")
        graph["nodes"] = [node for node in graph["nodes"] if node["id"] != "notes_restore_rehearsal"]
        graph["links"] = [
            edge for edge in graph["links"]
            if "notes_restore_rehearsal" not in {edge["source"], edge["target"]}
        ]
        graph["hyperedges"] = []
        graph["graph"]["hyperedges"] = []
        manifest = load_fixture("manifest.json")
        manifest["sourceRevision"] = "revision-with-deletion"
        manifest["artifactSha256"] = sha256_value(graph)
        reconciled = GraphifyTranslator(ontology()).translate(
            graph, manifest, tenant="tenant-a", namespace="rhize-tools"
        )
        self.store.ingest(
            reconciled,
            role="ingest",
            idempotency_key="reconciled",
            expected_current=first_receipt["compilationHash"],
        )
        result = self.store.query(
            "query_context",
            tenant_key=reconciled["tenantKey"], namespace_key=reconciled["namespaceKey"],
            corpus_key=reconciled["corpusKey"], principal_scopes=["group:rhize-tools"],
            role="query", query_text="Restore Rehearsal",
        )
        self.assertEqual(result["results"], [])

    def test_purge_and_checksumming_restore_reconcile_visibility(self) -> None:
        self.store.ingest(
            self.first, role="ingest", idempotency_key="first", expected_current=None
        )
        partition = self._partition(self.first)
        snapshot = self.store.backup(role="migration_admin")
        receipts = self.store.purge_source_revision(
            tenant_key=partition[0], namespace_key=partition[1], corpus_key=partition[2],
            source_revision="revision-1", role="ingest",
        )
        self.assertEqual(receipts[0]["status"], "purged")
        self.assertIsNone(self.store.current_compilation(*partition))
        self.store.restore(snapshot, role="migration_admin")
        self.assertEqual(self.store.current_compilation(*partition), self.first["compilationId"])
        damaged = dict(snapshot)
        damaged["checksum"] = "0" * 64
        with self.assertRaisesRegex(StoreError, "checksum mismatch"):
            self.store.restore(damaged, role="migration_admin")
        malformed = copy.deepcopy(snapshot)
        malformed["payload"]["accepted"] = {"invalid": self.first["compilationId"]}
        malformed["checksum"] = sha256_value(malformed["payload"])
        with self.assertRaisesRegex(StoreError, "accepted-compilation index"):
            self.store.restore(malformed, role="migration_admin")
        malformed_receipt = copy.deepcopy(snapshot)
        receipt = next(iter(malformed_receipt["payload"]["receipts"].values()))
        receipt["counts"]["records"] += 1
        malformed_receipt["checksum"] = sha256_value(malformed_receipt["payload"])
        with self.assertRaisesRegex(StoreError, "receipt contract"):
            self.store.restore(malformed_receipt, role="migration_admin")
        self.assertEqual(self.store.current_compilation(*partition), self.first["compilationId"])


if __name__ == "__main__":
    unittest.main()
