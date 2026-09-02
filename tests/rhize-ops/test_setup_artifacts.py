"""test_setup_artifacts.py — rhize-ops/scripts/setup_artifacts.py (hybrid-setup-wizard.md R2
§5). Same hermetic idempotency pattern as tests/skill-map/test_render_docs.py: --check copies
its exact input set into a temp tree and never writes inside the real repo.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "setup_artifacts.py"
SPEC = importlib.util.spec_from_file_location("setup_artifacts", SCRIPT)
setup_artifacts = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(setup_artifacts)

MARKER_DOC = """# Setup artifacts

Lead paragraph.

<!-- SETUP-ARTIFACTS:BEGIN -->
<!-- SETUP-ARTIFACTS:END -->
"""


def make_repo(tmp_path: Path, artifacts_by_plugin: dict[str, list[dict]]) -> Path:
    root = tmp_path / "repo"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": [{"name": name} for name in artifacts_by_plugin]}), encoding="utf-8",
    )
    for plugin, artifacts in artifacts_by_plugin.items():
        setup_dir = root / plugin / "setup"
        setup_dir.mkdir(parents=True)
        (setup_dir / "manifest.json").write_text(
            json.dumps({"schema": 3, "plugin": plugin, "items": [], "dependencies": [], "artifacts": artifacts,
                        "evaluations": {"catalog": "rhize-evaluations-v1", "component": plugin}}),
            encoding="utf-8",
        )
    doc_path = root / "rhize-ops" / "docs" / "setup-artifacts.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text(MARKER_DOC, encoding="utf-8")
    return root


def sample_artifact(artifact_id: str = "cfg") -> dict:
    return {
        "id": artifact_id, "path": "<home>/.widgets/config.json", "kind": "file",
        "purpose": "Widget config.", "viewer": "cat ~/.widgets/config.json", "lifetime": "persistent",
        "confidentiality": "config", "source": "authored", "tracked": "outside-repo", "optional": False,
    }


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


def test_render_inserts_a_row_per_artifact(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"widgets": [sample_artifact("cfg")], "gadgets": []})
    completed = run_cli("--markdown", "--repo-root", str(root))
    assert completed.returncode == 0, completed.stderr
    text = (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text()
    assert "cfg" in text
    assert "widgets" in text
    assert "<!-- SETUP-ARTIFACTS:BEGIN -->" in text and "<!-- SETUP-ARTIFACTS:END -->" in text


def test_render_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"widgets": [sample_artifact("cfg")]})
    run_cli("--markdown", "--repo-root", str(root))
    before = (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text()
    completed = run_cli("--markdown", "--repo-root", str(root))
    assert "No changes" in completed.stdout
    after = (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text()
    assert before == after


def test_render_escapes_pipe_characters(tmp_path: Path) -> None:
    artifact = sample_artifact("cfg")
    artifact["viewer"] = "Contains a | pipe and a\nnewline."
    root = make_repo(tmp_path, {"widgets": [artifact]})
    run_cli("--markdown", "--repo-root", str(root))
    text = (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text()
    assert "Contains a \\| pipe and a newline." in text


def test_refuses_without_markers(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"widgets": [sample_artifact()]})
    (root / "rhize-ops" / "docs" / "setup-artifacts.md").write_text("# No markers\n", encoding="utf-8")
    completed = run_cli("--markdown", "--repo-root", str(root))
    assert completed.returncode != 0
    assert "marker pair" in completed.stderr


def test_check_passes_when_current(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"widgets": [sample_artifact()]})
    run_cli("--markdown", "--repo-root", str(root))
    completed = run_cli("--check", "--repo-root", str(root))
    assert completed.returncode == 0, completed.stderr
    assert "PASS" in completed.stdout


def test_check_fails_when_stale(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"widgets": [sample_artifact()]})
    run_cli("--markdown", "--repo-root", str(root))
    # Drift: add a second artifact after the doc was last rendered, without re-rendering.
    manifest_path = root / "widgets" / "setup" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"].append(sample_artifact("cfg-2"))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    committed_before = (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text()
    completed = run_cli("--check", "--repo-root", str(root))
    assert completed.returncode == 1
    assert "stale" in completed.stderr

    # --check must never write inside the real repo tree.
    assert (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text() == committed_before


def test_check_never_writes_the_real_repo() -> None:
    """Hermeticity, mirroring tests/skill-map/test_render_docs.py's own guardrail: running
    --check against the actual rhize-plugins repo must not modify its committed doc."""
    doc_path = REPO / "rhize-ops" / "docs" / "setup-artifacts.md"
    before = doc_path.read_text(encoding="utf-8")
    completed = run_cli("--check")
    assert doc_path.read_text(encoding="utf-8") == before
    assert completed.returncode in (0, 1)


def test_no_artifacts_renders_a_placeholder_line(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"widgets": []})
    completed = run_cli("--markdown", "--repo-root", str(root))
    assert completed.returncode == 0, completed.stderr
    text = (root / "rhize-ops" / "docs" / "setup-artifacts.md").read_text()
    assert "No plugin currently declares a setup artifact" in text


def test_resolve_repo_root_falls_back_to_the_marketplace_clone_from_an_installed_cache(tmp_path: Path) -> None:
    """From `~/.claude/plugins/cache/<mkt>/rhize-ops/<ver>/scripts/` two-parents-up is not the
    marketplace, so the script must locate the clone under `~/.claude/plugins/marketplaces/`
    (found live on 2026-09-02: the installed copy raised FileNotFoundError on --check)."""
    home = tmp_path / "home"
    cache_copy = home / ".claude" / "plugins" / "cache" / "rhize-plugins" / "rhize-ops" / "9.9.9" / "scripts" / "setup_artifacts.py"
    cache_copy.parent.mkdir(parents=True)
    cache_copy.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("setup_artifacts_installed", cache_copy)
    installed = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(installed)

    # No clone yet: falls back to the (wrong, but only) checkout guess rather than raising.
    assert installed.resolve_repo_root(home=home) == cache_copy.resolve().parents[2]

    clone = home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins"
    (clone / ".claude-plugin").mkdir(parents=True)
    (clone / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
    (clone / "rhize-ops").mkdir()
    other = home / ".claude" / "plugins" / "marketplaces" / "another-marketplace"
    (other / ".claude-plugin").mkdir(parents=True)
    (other / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
    assert installed.resolve_repo_root(home=home) == clone

    # The dev checkout still wins when the script sits inside one.
    assert setup_artifacts.resolve_repo_root(home=home) == REPO
