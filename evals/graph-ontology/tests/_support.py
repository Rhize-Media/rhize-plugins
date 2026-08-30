from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "rhize-context-manager" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from graph_memory.contract import compile_ontology, sha256_value  # noqa: E402
from graph_memory.translate import GraphifyTranslator  # noqa: E402


FIXTURES = ROOT / "evals" / "graph-ontology" / "fixtures"
CORE = ROOT / "rhize-context-manager" / "catalog" / "graph-ontology" / "core-v1.json"
PACK = ROOT / "rhize-context-manager" / "catalog" / "graph-ontology" / "packs" / "knowledge-management-v1.json"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def ontology(with_pack: bool = True):
    return compile_ontology(CORE, [PACK] if with_pack else [])


def compilation(
    *,
    tenant: str = "tenant-a",
    namespace: str = "rhize-tools",
    source_revision: str | None = None,
) -> dict[str, Any]:
    graph = load_fixture("graph.json")
    manifest = load_fixture("manifest.json")
    if source_revision is not None:
        manifest["sourceRevision"] = source_revision
    manifest["artifactSha256"] = sha256_value(graph)
    return GraphifyTranslator(ontology()).translate(
        graph, manifest, tenant=tenant, namespace=namespace
    )
