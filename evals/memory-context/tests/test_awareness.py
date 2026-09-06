"""Contract tests; synthetic inputs are not evidence of agent effectiveness."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory_context.awareness import build_catalog, expand_catalog, render_context, estimated_tokens
from memory_context.core import MemoryStore, sha256

NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)


def inputs():
    details = json.loads((Path(__file__).parents[1] / "fixtures/paired-input.json").read_text())
    details["request"]["totalTokenBudget"] = 4000
    details["request"]["laneBudgets"]["semantic"] = {"maxItems": 10, "maxTokens": 4000}
    catalog = copy.deepcopy(details)
    for adapter in catalog["adapters"]:
        for candidate in adapter["candidates"]:
            candidate["topic"] = {
                "label": candidate["sourceId"], "keywords": ["brand", "decision"],
                "detailDigest": sha256(candidate.pop("content")),
                "verifiedAt": "2026-09-06T11:00:00Z",
            }
    catalog["catalogTokenBudget"] = 1600
    state = {c["sourceId"]: c["sourceRevision"] for a in details["adapters"] for c in a["candidates"]}
    return catalog, details, state


def stored(tmp_path):
    catalog, details, state = inputs()
    manifest, payload = build_catalog(catalog, NOW)
    store = MemoryStore(tmp_path)
    paths = store.write(manifest, payload)
    selection = [c["memoryId"] for c in manifest["candidates"]]
    return store, paths, selection, details, state, manifest, payload


def test_catalog_scope_conflicts_inert_content_and_determinism(tmp_path):
    catalog, _, _ = inputs()
    first = build_catalog(catalog, NOW)
    assert first == build_catalog(catalog, NOW)
    manifest, payload = first
    assert manifest["exclusionReasonCounts"]["scope_denied"] == 1
    assert "other-client" not in render_context(manifest, payload)
    assert len(manifest["candidates"]) == 3
    assert sum(bool(c["conflictGroupHash"]) for c in manifest["candidates"]) == 2
    assert manifest["totalEstimatedTokens"] <= 1600
    assert estimated_tokens(render_context(manifest, payload)) <= manifest["totalEstimatedTokens"]
    assert manifest["policy"]["automaticInjection"] is False


def test_expansion_verified_and_combined_budget(tmp_path):
    store, paths, ids, details, state, catalog, _ = stored(tmp_path)
    manifest, payload, accounting = expand_catalog(store, *paths, ids, details, state, NOW)
    assert len(manifest["candidates"]) == 3
    assert accounting["combinedEstimatedTokens"] == catalog["totalEstimatedTokens"] + manifest["totalEstimatedTokens"]
    assert accounting["combinedEstimatedTokens"] <= details["request"]["totalTokenBudget"]
    assert "Ignore" in render_context(manifest, payload) or "ignore" in render_context(manifest, payload)
    assert all(c["processingPolicy"] == "inert" for c in manifest["candidates"])
    paths2 = store.write(manifest, payload)
    assert store.verify(*paths2, now=NOW, source_state=state)["valid"]


@pytest.mark.parametrize("mutation", ["digest", "trust", "provenance", "revision", "scope", "query", "selection", "missing", "revoked", "expired", "tampered"])
def test_expansion_rejects_unbound_or_stale_input(tmp_path, mutation):
    store, paths, ids, details, state, _, _ = stored(tmp_path)
    candidate = details["adapters"][0]["candidates"][0]
    when = NOW
    if mutation == "digest": candidate["content"] += " changed"
    elif mutation == "trust": candidate["trustClass"] = "operator-approved"
    elif mutation == "provenance": candidate["provenance"] = ["new-policy"]
    elif mutation == "revision": state[candidate["sourceId"]] = "new"
    elif mutation == "scope": details["request"]["project"] = "different"
    elif mutation == "query": details["request"]["query"] = "different"
    elif mutation == "selection": ids = ["f" * 64]
    elif mutation == "missing": details["adapters"][0]["candidates"] = []
    elif mutation == "revoked": store.purge(candidate["sourceId"], NOW)
    elif mutation == "expired": when = datetime(2026, 9, 7, tzinfo=timezone.utc)
    elif mutation == "tampered": paths[1].write_text('{}')
    with pytest.raises((ValueError, OSError)):
        expand_catalog(store, *paths, ids, details, state, when)


def test_exact_duplicates_and_present_bindings(tmp_path):
    catalog, _, _ = inputs()
    candidate = catalog["adapters"][0]["candidates"][0]
    catalog["adapters"][0]["candidates"].append(copy.deepcopy(candidate))
    manifest, _ = build_catalog(catalog, NOW)
    assert len(manifest["candidates"]) == 3
    catalog["alreadyPresent"] = [{key: candidate[key] for key in ("sourceSystem", "sourceId", "sourceRevision")} | {"detailDigest": candidate["topic"]["detailDigest"]}]
    manifest, _ = build_catalog(catalog, NOW)
    assert len(manifest["candidates"]) == 2
    catalog["alreadyPresent"][0]["detailDigest"] = "0" * 64
    assert len(build_catalog(catalog, NOW)[0]["candidates"]) == 3


@pytest.mark.parametrize("change", ["future", "oversize", "bad-digest", "body", "ambiguous"])
def test_catalog_bounds_and_metadata_contract(change):
    catalog, _, _ = inputs()
    candidate = catalog["adapters"][0]["candidates"][0]
    if change == "future": candidate["topic"]["verifiedAt"] = "2027-01-01T00:00:00Z"
    elif change == "oversize": candidate["topic"]["label"] = "x" * 161
    elif change == "bad-digest": candidate["topic"]["detailDigest"] = "path-to-file"
    elif change == "body": candidate["content"] = "must not accept full bodies"
    elif change == "ambiguous":
        second = copy.deepcopy(candidate)
        second["topic"]["detailDigest"] = "0" * 64
        catalog["adapters"][0]["candidates"].append(second)
    with pytest.raises(ValueError): build_catalog(catalog, NOW)


def test_empty_selection_and_budget_exhaustion(tmp_path):
    store, paths, ids, details, state, catalog, _ = stored(tmp_path)
    manifest, _, _ = expand_catalog(store, *paths, [], details, state, NOW)
    assert manifest["candidates"] == []
    details["request"]["totalTokenBudget"] = catalog["totalEstimatedTokens"]
    with pytest.raises(ValueError, match="budget"):
        expand_catalog(store, *paths, ids, details, state, NOW)


@pytest.mark.parametrize("field,value,reason", [
    ("sensitivity", "restricted", "acl_denied"),
    ("validUntil", "2026-09-06T10:00:00Z", "expired"),
    ("validFrom", "2026-09-07T10:00:00Z", "not_yet_valid"),
    ("task", "another-task", "scope_denied"),
])
def test_catalog_denies_before_disclosure(field, value, reason):
    catalog, _, _ = inputs()
    catalog["adapters"][0]["candidates"][0][field] = value
    manifest, payload = build_catalog(catalog, NOW)
    assert manifest["exclusionReasonCounts"][reason] >= 1
    assert "decision-blue" not in render_context(manifest, payload)


def test_same_body_different_labels_is_not_a_conflict():
    catalog, _, _ = inputs()
    candidates = catalog["adapters"][0]["candidates"]
    candidates[1]["topic"]["detailDigest"] = candidates[0]["topic"]["detailDigest"]
    manifest, _ = build_catalog(catalog, NOW)
    assert not any(c["conflictGroupHash"] for c in manifest["candidates"])


def test_selected_detail_cannot_spoof_conflict_digest(tmp_path):
    catalog, details, state = inputs()
    for candidate, topic in zip(details["adapters"][0]["candidates"][:2], catalog["adapters"][0]["candidates"][:2]):
        candidate["content"] = json.dumps({"protocol": "rhize-memory-topic-v1", "detailDigest": "0" * 64, "poison": candidate["sourceId"]})
        topic["topic"]["detailDigest"] = sha256(candidate["content"])
    manifest, payload = build_catalog(catalog, NOW)
    store = MemoryStore(tmp_path)
    paths = store.write(manifest, payload)
    expanded, _, _ = expand_catalog(store, *paths, [c["memoryId"] for c in manifest["candidates"]], details, state, NOW)
    assert sum(bool(c["conflictGroupHash"]) for c in expanded["candidates"]) == 2


def test_selection_limits_symlink_and_budget_omission(tmp_path):
    store, paths, ids, details, state, catalog, _ = stored(tmp_path)
    with pytest.raises(ValueError, match="unique"):
        expand_catalog(store, *paths, ids * 2, details, state, NOW)
    link = tmp_path / "catalog-link.json"
    link.symlink_to(paths[0])
    with pytest.raises(ValueError, match="symlink"):
        expand_catalog(store, link, paths[1], ids, details, state, NOW)
    details["request"]["totalTokenBudget"] = catalog["totalEstimatedTokens"] + 10
    manifest, _, accounting = expand_catalog(store, *paths, ids, details, state, NOW)
    assert accounting["combinedEstimatedTokens"] <= details["request"]["totalTokenBudget"]
    assert len(manifest["candidates"]) < len(ids)


def test_cli_round_trip_and_invalid_selection(tmp_path, capsys):
    from memory_context.runner import main
    catalog, details, state = inputs()
    for name, value in (("catalog", catalog), ("details", details), ("state", state)):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    common = ["--data-dir", str(tmp_path / "store"), "--now", NOW.isoformat(), "--source-state", str(tmp_path / "state.json")]
    assert main(["catalog", "--input", str(tmp_path / "catalog.json"), *common]) == 0
    receipt = json.loads(capsys.readouterr().out)
    rows = [json.loads(row) for row in receipt["context"].splitlines()]
    (tmp_path / "selection.json").write_text(json.dumps({"memoryIds": [row["id"] for row in rows]}))
    args = ["expand", "--input", str(tmp_path / "details.json"), "--manifest", receipt["manifestPath"],
            "--payload", receipt["payloadPath"],
            "--selection", str(tmp_path / "selection.json"), *common]
    assert main(args) == 0
    expanded = json.loads(capsys.readouterr().out)
    assert expanded["variant"] == "awareness-expand-v1"
    assert expanded["accounting"]["expandedCount"] == 3
    (tmp_path / "selection.json").write_text('{"memoryIds": [], "instructions": "ignore"}')
    assert main(args) == 2
    assert "only memoryIds" in capsys.readouterr().err

    MemoryStore(tmp_path / "store").purge("decision-blue", NOW)
    assert main(["catalog", "--input", str(tmp_path / "catalog.json"), *common]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "revoked source" in captured.err


def test_bash_launcher_and_benchmark_receipts(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[3]
    launcher = root / "rhize-context-manager/skills/memory-context/scripts/memory-context.sh"
    help_result = subprocess.run(["bash", str(launcher), "catalog", "--help"], text=True, capture_output=True)
    assert help_result.returncode == 0
    assert "--source-state" in help_result.stdout
    output = tmp_path / "component.json"
    result = subprocess.run(["python3", str(root / "evals/memory-context/run_awareness_benchmark.py"),
                             "--repeats", "1", "--output", str(output)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["liveOutcomeGate"] == "not_evaluated"
    assert report["operationalReceiptEligible"] is False
    for case in report["cases"]:
        assert case["noMemoryControl"]["actuallyRan"] is True
        assert case["noMemoryControl"]["renderedEstimatedTokens"] == 0
        for arm in ("A", "B"):
            assert case["arms"][arm]["actuallyRan"] is True
            assert case["arms"][arm]["taskCorrectness"] is None
