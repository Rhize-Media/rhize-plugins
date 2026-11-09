"""Lifecycle contracts for reviewed, source-bound multi-page transactions."""
import copy
import json
from pathlib import Path
from unittest import mock

import pytest
from test_compiled_knowledge import NOW, VaultFixture, compiler


@pytest.fixture
def vault(tmp_path):
    fixture = VaultFixture(tmp_path)
    (fixture.sources / "meeting.md").write_text("The project ships Friday.\nDecisions need evidence.\n")
    compiler.register_source(fixture.settings, "Sources/meeting.md", "source-2", ["internal"], "local-only", "standard", NOW, None)
    return fixture


def proposal():
    return {"schema_version": 2, "pages": [
        {"page_id": "project", "path": "Project.md", "title": "Project", "claims": [
            {"claim_id": "decision", "text": "Ship Friday using authoritative sources.", "citations": [
                {"source_id": "source-1", "start_line": 1, "end_line": 1},
                {"source_id": "source-2", "start_line": 1, "end_line": 1}]}], "links": ["Evidence"], "contradiction_candidates": []},
        {"page_id": "evidence", "path": "Evidence.md", "title": "Evidence", "claims": [
            {"claim_id": "evidence", "text": "Decisions need evidence.", "citations": [
                {"source_id": "source-2", "start_line": 2, "end_line": 2}]}], "links": ["Project"], "contradiction_candidates": []}]}


def preview(vault, raw=None):
    vault.proposal.write_text(json.dumps(raw or proposal()))
    return vault.preview()


def test_batch_lifecycle_provenance_frontmatter_and_noop(vault):
    result = preview(vault)
    assert result["pages"] == 2 and result["sources"] == 2
    review = Path(result["review"]).read_text()
    assert "The project ships Friday." in review and "A source stays authoritative." in review
    assert not list(vault.output.iterdir())
    assert vault.apply(result["preview_id"])["status"] == "applied"
    index = compiler.load_index(vault.settings)
    assert index["pages"]["project"]["source_ids"] == ["source-1", "source-2"]
    assert index["pages"]["evidence"]["source_ids"] == ["source-2"]
    project = (vault.output / "Project.md").read_text()
    assert project.startswith("---\n") and "rhize-source-ids:" in project
    assert "[Source](../Sources/meeting.md)" in project
    assert vault.apply(result["preview_id"])["status"] == "noop"
    report = compiler.status_report(vault.settings, NOW)
    assert all(page["status"] == "clean" for page in report["pages"])
    assert report["batches"][0]["status"] == "accepted"
    journal = json.loads(next((vault.settings.state_root / "batch-transactions").glob("*.json")).read_text())
    assert journal["operations"] == []  # No retained payload backups after commit.


@pytest.mark.parametrize("point", ["batch-prepared"] + [f"batch-write-{n}" for n in range(1, 7)])
def test_every_interrupted_write_rolls_back_all_pages_and_can_retry(vault, point):
    result = preview(vault)
    with pytest.raises(compiler.InjectedCrash):
        vault.apply(result["preview_id"], fault_after=point)
    report = compiler.status_report(vault.settings, NOW)
    assert len(report["recovered_transactions"]) == 1
    assert not list(vault.output.iterdir()) and report["pages"] == []
    assert vault.apply(result["preview_id"])["status"] == "applied"


def test_crash_after_acceptance_keeps_complete_state(vault):
    result = preview(vault)
    with pytest.raises(compiler.InjectedCrash):
        vault.apply(result["preview_id"], fault_after="batch-accepted")
    assert vault.apply(result["preview_id"])["status"] == "noop"
    assert len(compiler.status_report(vault.settings, NOW)["pages"]) == 2


def test_recovery_conflict_preserves_human_edits_and_pending_transaction(vault):
    result = preview(vault)
    with pytest.raises(compiler.InjectedCrash):
        vault.apply(result["preview_id"], fault_after="batch-write-3")
    target = vault.output / "Project.md"
    rendered = target.read_bytes()
    target.write_bytes(rendered + b"Human decision.\n")
    with pytest.raises(compiler.CompilerError, match="recovery conflict"):
        compiler.status_report(vault.settings, NOW)
    assert target.read_bytes().endswith(b"Human decision.\n")
    assert (vault.output / "Evidence.md").exists()  # No partial rollback on conflict.
    # Simulate operator preserving the edit elsewhere and restoring reviewed bytes.
    (vault.root / "Personal decision.md").write_bytes(target.read_bytes())
    target.write_bytes(rendered)
    assert compiler.status_report(vault.settings, NOW)["pages"] == []


def test_interrupted_rollback_is_idempotent(vault):
    result = preview(vault)
    with pytest.raises(compiler.InjectedCrash):
        vault.apply(result["preview_id"], fault_after="batch-write-6")
    real_restore = compiler.restore
    calls = 0
    def crash_restore(*args):
        nonlocal calls
        real_restore(*args)
        calls += 1
        if calls == 3:
            raise compiler.InjectedCrash("during-rollback")
    with mock.patch.object(compiler, "restore", side_effect=crash_restore), pytest.raises(compiler.InjectedCrash):
        compiler.status_report(vault.settings, NOW)
    assert compiler.status_report(vault.settings, NOW)["pages"] == []
    assert not list(vault.output.iterdir())


@pytest.mark.parametrize("change", ["source", "target", "artifact", "review", "policy", "snapshot"])
def test_invalid_last_page_or_dependency_writes_nothing(vault, change):
    result = preview(vault)
    if change == "source":
        (vault.sources / "meeting.md").write_text("Changed.\n")
    elif change == "target":
        (vault.output / "Evidence.md").write_text("Human-owned.\n")
    elif change == "artifact":
        (compiler.preview_dir(vault.settings, result["child_previews"][-1]) / "page.md").write_text("Tampered")
    elif change == "review":
        Path(result["review"]).write_text("Tampered")
    elif change == "policy":
        path = compiler.registration_path(vault.settings, "source-2")
        raw = json.loads(path.read_text()); raw["acl"] = ["private"]; path.write_text(json.dumps(raw))
    else:
        registration = compiler.load_registration(vault.settings, "source-2")
        compiler.snapshot_path(vault.settings, "source-2", registration["current_revision_hash"]).unlink()
    with pytest.raises(compiler.CompilerError):
        vault.apply(result["preview_id"])
    assert not (vault.output / "Project.md").exists()
    assert compiler.load_index(vault.settings)["pages"] == {}


def test_existing_human_edits_block_fresh_preview(vault):
    result = preview(vault); vault.apply(result["preview_id"])
    target = vault.output / "Project.md"
    target.write_text(target.read_text() + "Human edits before the next preview.\n")
    with pytest.raises(compiler.CompilerError, match="human edits"):
        preview(vault)


@pytest.mark.parametrize("mutation", ["duplicate_id", "duplicate_path", "case_path", "boolean_line", "unknown_source", "unknown_field", "beyond_source"])
def test_strict_batch_contract(vault, mutation):
    raw = proposal()
    if mutation == "duplicate_id": raw["pages"][1]["page_id"] = "project"
    elif mutation == "duplicate_path": raw["pages"][1]["path"] = "Project.md"
    elif mutation == "case_path": raw["pages"][1]["path"] = "project.md"
    elif mutation == "boolean_line": raw["pages"][0]["claims"][0]["citations"][0]["start_line"] = True
    elif mutation == "unknown_source": raw["pages"][0]["claims"][0]["citations"][0]["source_id"] = "unknown"
    elif mutation == "unknown_field": raw["pages"][1]["tools"] = ["shell"]
    else: raw["pages"][1]["claims"][0]["citations"][0]["end_line"] = 500
    with pytest.raises(compiler.CompilerError): preview(vault, raw)
    assert not list(vault.output.iterdir())


@pytest.mark.parametrize("mixed", ["within_page", "between_pages"])
def test_mixed_privacy_boundary_fails_closed(vault, mixed):
    registration = compiler.load_registration(vault.settings, "source-2")
    registration["acl"] = ["private"]
    compiler.atomic_write(compiler.registration_path(vault.settings, "source-2"), compiler.canonical_json(registration))
    raw = proposal()
    if mixed == "between_pages": raw["pages"][0]["claims"][0]["citations"].pop()
    with pytest.raises(compiler.CompilerError, match="mixed source policies"): preview(vault, raw)
    assert not list(vault.output.iterdir())


def test_purge_dependency_graph_preserves_unrelated_page_and_source(vault):
    result = preview(vault); vault.apply(result["preview_id"])
    confirmation = "source-1:" + vault.registration["current_revision_hash"]
    purged = compiler.purge_source(vault.settings, "source-1", confirmation, NOW)
    assert purged["suppressed_pages"] == ["project"]
    assert not (vault.output / "Project.md").exists()
    assert (vault.output / "Evidence.md").exists() and vault.source.exists()
    assert not Path(result["preview_dir"]).exists()
    assert [p["status"] for p in compiler.status_report(vault.settings, NOW)["pages"]] == ["clean", "purged"]


def test_purge_shared_source_removes_all_dependents(vault):
    result = preview(vault); vault.apply(result["preview_id"])
    registration = compiler.load_registration(vault.settings, "source-2")
    purged = compiler.purge_source(vault.settings, "source-2", "source-2:" + registration["current_revision_hash"], NOW)
    assert purged["suppressed_pages"] == ["evidence", "project"]
    assert not list(vault.output.iterdir())
    assert (vault.sources / "meeting.md").exists()


def test_rebuild_keeps_each_citation_source_and_refuses_stale_rebinding(vault):
    result = preview(vault); vault.apply(result["preview_id"])
    rebuilt = compiler.rebuild_page(vault.settings, "project", None, NOW.replace(minute=1))
    manifest = json.loads((Path(rebuilt["preview_dir"]) / "manifest.json").read_text())
    assert [item["source_id"] for item in manifest["source_revisions"]] == ["source-1", "source-2"]
    (vault.sources / "meeting.md").write_text("Different meaning at the same line.\n")
    with pytest.raises(compiler.CompilerError, match="source changed"):
        compiler.rebuild_page(vault.settings, "project", None, NOW)


def test_tampered_journal_cannot_write_another_target(vault):
    result = preview(vault)
    with pytest.raises(compiler.InjectedCrash): vault.apply(result["preview_id"], fault_after="batch-prepared")
    path = next((vault.settings.state_root / "batch-transactions").glob("*.json"))
    raw = json.loads(path.read_text())
    raw["operations"][0]["path"] = str(vault.output / "Human.md")
    compiler.write_batch_journal(path, raw)  # Even recomputing integrity cannot expand path authority.
    with pytest.raises(compiler.CompilerError, match="canonical path"):
        compiler.status_report(vault.settings, NOW)
    assert not (vault.output / "Human.md").exists()


def tree_fingerprint(root):
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None, p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.rglob("*")}


@pytest.mark.parametrize("pending", [False, True])
def test_inspect_has_no_filesystem_mutation_and_never_recovers(vault, pending):
    result = preview(vault)
    if pending:
        with pytest.raises(compiler.InjectedCrash): vault.apply(result["preview_id"], fault_after="batch-write-3")
    else:
        vault.apply(result["preview_id"])
    before = tree_fingerprint(vault.root)
    settings = compiler.load_settings(vault.config, initialize=False)
    report = compiler.inspect_report(settings, NOW)
    assert report["inspection"] == ("recovery-required" if pending else "observed")
    assert tree_fingerprint(vault.root) == before


def test_inspect_does_not_initialize_state(vault):
    config = json.loads(vault.config.read_text()); config["state_root"] = ".rhize/new-state"
    vault.config.write_text(json.dumps(config))
    before = tree_fingerprint(vault.root)
    assert compiler.inspect_report(compiler.load_settings(vault.config, initialize=False), NOW)["inspection"] == "uninitialized"
    assert tree_fingerprint(vault.root) == before


def test_single_page_recovery_preserves_human_edits(vault):
    result = vault.preview()
    with pytest.raises(compiler.InjectedCrash): vault.apply(result["preview_id"], fault_after="target-written")
    target = vault.output / "compiled-page.md"
    target.write_text(target.read_text() + "Human edit after crash.\n")
    with pytest.raises(compiler.CompilerError, match="recovery conflict"):
        compiler.status_report(vault.settings, NOW)
    assert target.read_text().endswith("Human edit after crash.\n")


def test_update_crash_restores_both_previous_pages_and_index(vault):
    original = preview(vault); vault.apply(original["preview_id"])
    old_pages = {p.name: p.read_bytes() for p in vault.output.iterdir()}
    old_index = compiler.index_path(vault.settings).read_bytes()
    raw = proposal(); raw["pages"][0]["claims"][0]["text"] = "Revised synthesis for review."
    revised = preview(vault, raw)
    with pytest.raises(compiler.InjectedCrash): vault.apply(revised["preview_id"], fault_after="batch-write-5")
    compiler.status_report(vault.settings, NOW)
    assert {p.name: p.read_bytes() for p in vault.output.iterdir()} == old_pages
    assert compiler.index_path(vault.settings).read_bytes() == old_index


def test_expired_batch_and_source_retention(vault):
    result = preview(vault)
    with pytest.raises(compiler.CompilerError, match="expired"):
        compiler.apply_preview(vault.settings, result["preview_id"], NOW.replace(hour=14))
    registration = compiler.load_registration(vault.settings, "source-2")
    registration["expires_at"] = compiler.format_time(NOW)
    compiler.atomic_write(compiler.registration_path(vault.settings, "source-2"), compiler.canonical_json(registration))
    with pytest.raises(compiler.CompilerError, match="state changed|metadata changed"):
        compiler.apply_preview(vault.settings, result["preview_id"], NOW.replace(minute=1))
    assert not list(vault.output.iterdir())


@pytest.mark.parametrize("point", ["purge-prepared", "purge-targets-deleted", "purge-accepted-manifests-deleted",
                                   "purge-previews-deleted", "purge-source-store-deleted", "purge-tombstone-written",
                                   "purge-index-written", "purge-registration-written"])
def test_batch_purge_recovers_at_every_boundary(vault, point):
    result = preview(vault); vault.apply(result["preview_id"])
    registration = compiler.load_registration(vault.settings, "source-2")
    with pytest.raises(compiler.InjectedCrash):
        compiler.purge_source(vault.settings, "source-2", "source-2:" + registration["current_revision_hash"], NOW, point)
    report = compiler.status_report(vault.settings, NOW)
    assert all(page["status"] == "purged" for page in report["pages"])
    assert not list(vault.output.iterdir())
    assert not Path(result["preview_dir"]).exists()
    assert not (vault.settings.state_root / "sources" / "source-2").exists()
    assert (vault.sources / "meeting.md").exists()


def test_batch_purge_preserves_human_page_conflict(vault):
    result = preview(vault); vault.apply(result["preview_id"])
    target = vault.output / "Project.md"
    target.write_text(target.read_text() + "Human-edited source-dependent content.\n")
    result = compiler.purge_source(vault.settings, "source-1", "source-1:" + vault.registration["current_revision_hash"], NOW)
    assert result["human_edit_conflicts"] == ["project"]
    assert target.read_text().endswith("Human-edited source-dependent content.\n")


def test_malformed_proposal_returns_controlled_error(vault):
    vault.proposal.write_text("{bad json")
    with pytest.raises(compiler.CompilerError, match="not valid JSON"):
        vault.preview()


def test_native_frontmatter_parses_as_properties(vault):
    import yaml
    result = preview(vault); vault.apply(result["preview_id"])
    page = (vault.output / "Project.md").read_text()
    properties = yaml.safe_load(page.split("---\n", 2)[1])
    assert properties["type"] == "compiled-knowledge"
    assert properties["rhize-source-ids"] == ["source-1", "source-2"]


def test_cli_end_to_end(vault, capsys):
    import subprocess
    import sys
    from test_compiled_knowledge import SCRIPT
    raw = proposal()
    vault.proposal.write_text(json.dumps(raw))
    def run(command, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), command, "--config", str(vault.config),
                                 "--now", compiler.format_time(NOW), *args], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    result = run("preview", "--proposal", str(vault.proposal))
    assert run("apply", "--preview-id", result["preview_id"])["pages"] == 2
    assert run("inspect")["inspection"] == "observed"


def test_legacy_100_preview_and_marker_page_migrate_only_after_review(vault):
    old = vault.preview()
    directory = Path(old["preview_dir"])
    manifest = json.loads((directory / "manifest.json").read_text())
    legacy = b'<!-- rhize-compiled-knowledge:page-id=page-1 -->\n---\ntype: compiled-knowledge\n---\n\n# Compiled Page\n\nSources remain authoritative.\n'
    manifest["compiler"]["version"] = "1.0.0"
    manifest["provenance"]["source_metadata_hash"] = compiler.digest(compiler.canonical_json(compiler.load_registration(vault.settings, "source-1")))
    manifest["diff"]["rendered_hash"] = compiler.digest(legacy)
    payload = copy.deepcopy(manifest); payload["preview"].pop("id")
    manifest["preview"]["id"] = compiler.digest(compiler.canonical_json(payload))
    destination = compiler.preview_dir(vault.settings, manifest["preview"]["id"])
    for name in ("diff.patch", "change-brief.md"):
        compiler.atomic_write(destination / name, (directory / name).read_bytes())
    compiler.atomic_write(destination / "page.md", legacy)
    compiler.atomic_write(destination / "manifest.json", compiler.canonical_json(manifest))
    vault.apply(manifest["preview"]["id"])
    target = vault.output / "compiled-page.md"
    assert target.read_bytes() == legacy
    rebuilt = compiler.rebuild_page(vault.settings, "page-1", None, NOW.replace(minute=1))
    assert target.read_bytes() == legacy  # Preview is not migration approval.
    vault.apply(rebuilt["preview_id"])
    assert target.read_bytes().startswith(b"---\n")
    assert compiler.inspect_report(vault.settings, NOW)["pages"][0]["status"] == "clean"


def test_batch_limit_and_path_takeover_are_rejected(vault):
    raw = proposal(); raw["pages"] = raw["pages"] * 51
    with pytest.raises(compiler.CompilerError, match="1 to 100"): preview(vault, raw)
    result = preview(vault); vault.apply(result["preview_id"])
    raw = proposal(); raw["pages"][0]["page_id"] = "another-id"
    with pytest.raises(compiler.CompilerError, match="another page id"): preview(vault, raw)


def test_separately_applied_child_requires_fresh_bundle(vault):
    result = preview(vault)
    vault.apply(result["child_previews"][0])
    with pytest.raises(compiler.CompilerError, match="partly applied"):
        vault.apply(result["preview_id"])
    assert not (vault.output / "Evidence.md").exists()


def test_purge_removes_legacy_backup_even_after_page_changes_source(vault):
    first = vault.preview(); vault.apply(first["preview_id"])
    old_target = (vault.output / "compiled-page.md").read_bytes()
    old_manifest = compiler.accepted_manifest_path(vault.settings, "page-1").read_bytes()
    raw = {"schema_version": 2, "page": {"page_id": "page-1", "path": "compiled-page.md", "title": "Meeting"},
           "claims": [{"claim_id": "meeting", "text": "Decisions need evidence.",
                       "citations": [{"source_id": "source-2", "start_line": 2, "end_line": 2}]}],
           "links": [], "contradiction_candidates": []}
    second = compiler.preview_payload(vault.settings, compiler.canonical_json(raw), NOW)
    vault.apply(second["preview_id"])
    journal_path = vault.settings.state_root / "transactions" / (second["preview_id"].removeprefix("sha256:") + ".json")
    journal = json.loads(journal_path.read_text())
    # Simulate a completed legacy journal that retained the prior source-dependent page.
    journal["backups"]["target"] = compiler.backup(old_target)
    journal["backups"]["accepted_manifest"] = compiler.backup(old_manifest)
    compiler.write_journal(journal_path, journal)
    result = compiler.purge_source(vault.settings, "source-1", "source-1:" + vault.registration["current_revision_hash"], NOW)
    assert result["suppressed_pages"] == []
    assert not journal_path.exists()
    assert (vault.output / "compiled-page.md").exists()
    assert compiler.inspect_report(vault.settings, NOW)["pages"][0]["status"] == "clean"
