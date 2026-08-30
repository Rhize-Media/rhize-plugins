from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import compilation, load_fixture, ontology
from graph_memory.contract import canonical_json, sha256_value
from graph_memory.translate import (
    GraphifyTranslationError,
    GraphifyTranslator,
    validate_codegraph_reference,
)


class GraphifyTranslationTests(unittest.TestCase):
    def test_translation_is_deterministic_and_tenant_ids_are_isolated(self) -> None:
        first = compilation(tenant="tenant-a")
        repeated = compilation(tenant="tenant-a")
        other = compilation(tenant="tenant-b")
        self.assertEqual(canonical_json(first), canonical_json(repeated))
        self.assertNotEqual(first["tenantKey"], other["tenantKey"])
        self.assertTrue(
            {record["governedId"] for record in first["records"]}.isdisjoint(
                record["governedId"] for record in other["records"]
            )
        )

    def test_parallel_evidence_and_hyperedge_are_preserved_as_claims(self) -> None:
        translated = compilation()
        claims = [record for record in translated["records"] if record["recordType"] == "Claim"]
        self.assertEqual(len(claims), 5)
        predicates = [claim["properties"]["predicate"] for claim in claims]
        self.assertIn("implements", predicates)
        self.assertIn("conceptually_related_to", predicates)
        hyperedge = next(claim for claim in claims if claim["properties"]["predicate"] == "participate_in")
        self.assertEqual(len(hyperedge["properties"]["participants"]), 3)

    def test_known_graphify_export_metadata_is_validated_and_hash_bound(self) -> None:
        translated = compilation()
        compiler = next(
            record for record in translated["records"]
            if record["properties"].get("label") == "Ontology Compiler"
        )
        implements = next(
            record for record in translated["records"]
            if record["recordType"] == "Claim"
            and record["properties"]["predicate"] == "implements"
        )
        self.assertRegex(compiler["properties"]["graphifyMetadataHash"], r"^[a-f0-9]{64}$")
        self.assertRegex(implements["properties"]["graphifyMetadataHash"], r"^[a-f0-9]{64}$")

    def test_graphify_export_envelope_mismatches_fail_closed(self) -> None:
        graph = load_fixture("graph.json")
        manifest = load_fixture("manifest.json")
        manifest["graphifyBuildCommit"] = "b" * 40
        manifest["artifactSha256"] = sha256_value(graph)
        with self.assertRaisesRegex(GraphifyTranslationError, "build commit"):
            GraphifyTranslator(ontology()).translate(
                graph, manifest, tenant="tenant-a", namespace="rhize-tools"
            )

        graph = load_fixture("graph.json")
        graph["graph"]["hyperedges"] = []
        manifest = load_fixture("manifest.json")
        manifest["artifactSha256"] = sha256_value(graph)
        with self.assertRaisesRegex(GraphifyTranslationError, "hyperedge metadata"):
            GraphifyTranslator(ontology()).translate(
                graph, manifest, tenant="tenant-a", namespace="rhize-tools"
            )

    def test_prompt_like_graph_text_is_quarantined_not_executed(self) -> None:
        translated = compilation()
        poisoned = [
            record for record in translated["records"]
            if "Ignore all previous" in str(record["properties"].get("label"))
        ]
        self.assertEqual(len(poisoned), 1)
        self.assertTrue(poisoned[0]["quarantined"])
        self.assertEqual(poisoned[0]["trust"], "unverified")
        touching = [
            edge for edge in translated["relationships"]
            if poisoned[0]["governedId"] in {edge["sourceId"], edge["targetId"]}
        ]
        self.assertTrue(touching)
        self.assertTrue(all(edge["quarantined"] for edge in touching))

    def test_source_specific_acl_and_trust_cannot_be_weakened_by_cross_source_edges(self) -> None:
        graph = load_fixture("graph.json")
        manifest = load_fixture("manifest.json")
        manifest["defaultAcl"] = ["group:docs"]
        code_source_hash = sha256_value("source:/redacted/repo/src/compiler.py")
        manifest["sourcePolicies"] = {
            code_source_hash: {
                "acl": ["group:code"], "sensitivity": "confidential", "trust": "low"
            }
        }
        manifest["artifactSha256"] = sha256_value(graph)
        translated = GraphifyTranslator(ontology()).translate(
            graph, manifest, tenant="tenant-a", namespace="rhize-tools"
        )
        code_record = next(
            record for record in translated["records"]
            if record["properties"].get("label") == "Ontology Compiler"
        )
        self.assertEqual(code_record["acl"], ["group:code"])
        self.assertEqual(code_record["trust"], "low")
        self.assertEqual(code_record["sensitivity"], "confidential")
        self.assertTrue(
            any(
                rejection["kind"] == "edge" and rejection["code"] == "invalid_record"
                for rejection in translated["rejections"]
            )
        )
        self.assertFalse(
            any(
                code_record["governedId"] in {edge["sourceId"], edge["targetId"]}
                and edge["relationshipType"] == "ABOUT"
                for edge in translated["relationships"]
            )
        )

    def test_unsupported_node_fields_are_reported_and_not_silently_dropped(self) -> None:
        graph = load_fixture("graph.json")
        graph["nodes"][0]["system_prompt"] = "unsafe"
        manifest = load_fixture("manifest.json")
        manifest["artifactSha256"] = sha256_value(graph)
        translated = GraphifyTranslator(ontology()).translate(
            graph, manifest, tenant="tenant-a", namespace="rhize-tools"
        )
        self.assertIn(
            {"kind": "node", "index": 0, "code": "unsupported_field_or_value"},
            translated["rejections"],
        )
        self.assertFalse(
            any(record["properties"].get("label") == "Ontology Compiler" for record in translated["records"])
        )

    def test_artifact_hash_mismatch_fails_closed(self) -> None:
        graph = load_fixture("graph.json")
        manifest = load_fixture("manifest.json")
        manifest["artifactSha256"] = "0" * 64
        with self.assertRaisesRegex(GraphifyTranslationError, "hash mismatch"):
            GraphifyTranslator(ontology()).translate(
                graph, manifest, tenant="tenant-a", namespace="rhize-tools"
            )

    def test_artifact_backlog_is_bounded_before_item_processing(self) -> None:
        graph = load_fixture("graph.json")
        manifest = load_fixture("manifest.json")
        with patch("graph_memory.translate.MAX_NODES", 3):
            with self.assertRaisesRegex(GraphifyTranslationError, "node count"):
                GraphifyTranslator(ontology()).translate(
                    graph, manifest, tenant="tenant-a", namespace="rhize-tools"
                )

        with patch("graph_memory.translate.MAX_PROJECTED_RELATIONSHIPS", 1):
            with self.assertRaisesRegex(GraphifyTranslationError, "relationship budget"):
                GraphifyTranslator(ontology()).translate(
                    graph, manifest, tenant="tenant-a", namespace="rhize-tools"
                )

    def test_codegraph_reference_never_initializes_an_index(self) -> None:
        reference = {
            "repositoryId": "repo-a", "commitSha": "a" * 40,
            "relativePath": "src/app.py", "qualifiedSymbol": "app.main", "toolVersion": "1.2.3",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(GraphifyTranslationError, "existing index"):
                validate_codegraph_reference(
                    reference, repo_root=root, repository_id="repo-a", current_commit="a" * 40,
                    tool_version="1.2.3",
                )
            self.assertFalse((root / ".codegraph").exists())
            (root / ".codegraph").mkdir()
            resolved = validate_codegraph_reference(
                reference, repo_root=root, repository_id="repo-a", current_commit="a" * 40,
                tool_version="1.2.3",
            )
            self.assertEqual(resolved["validation"], "same_revision_metadata")
            stale = copy.deepcopy(reference)
            stale["commitSha"] = "b" * 40
            with self.assertRaisesRegex(GraphifyTranslationError, "revision mismatch"):
                validate_codegraph_reference(
                    stale, repo_root=root, repository_id="repo-a", current_commit="a" * 40,
                    tool_version="1.2.3",
                )


if __name__ == "__main__":
    unittest.main()
