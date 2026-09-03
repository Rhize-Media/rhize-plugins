"""test_platform_fallback_drift.py — the rhize-ops platform fallback (Codex F6, repo-shape R-B)
must never silently diverge from rhize-core's originals, and must be genuinely self-contained
for an install that has only ever seen rhize-ops (no rhize-core installed alongside it yet).

Two concerns, kept separate:

1. Byte-identity: the real, checked-in rhize-ops fallback copies of the four platform scripts,
   the central evaluation catalog, the claude-home gitignore template, and the four JSON Schema
   files must be byte-for-byte identical to rhize-core's originals. A one-release compatibility
   window only works if "fallback" and "canonical" never quietly drift apart.

2. Self-containment: evaluation_setup.catalog_relative_path() and setup_artifacts.
   doc_relative_path() -- the two path-preference functions the platform scripts depend on --
   must resolve to rhize-core's assets when a `rhize-core` plugin directory exists under the
   repo root, and fall back to the running copy's OWN plugin directory otherwise, so an
   rhize-ops-only marketplace clone (pre-repo-shape-R-B, or this fallback copy running before
   rhize-core is installed) never points at a file that does not exist. This is tested against
   synthetic fixtures, not the real 11-component catalog: `evaluation_setup.py validate` also
   enforces a hardcoded `plugin_skills == 56` total-coverage invariant across every declared
   component (by design -- it is a coverage gate, not a parameterized check), so no from-scratch
   fixture smaller than the real marketplace can ever pass it end-to-end. Testing the resolution
   functions directly is what is actually achievable and what actually proves the self-
   containment property; setup_orchestrator.py discover has no such constraint and IS exercised
   end-to-end below, against both an ops-only and a both-plugins synthetic marketplace.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "rhize-core"
OPS = REPO_ROOT / "rhize-ops"

DRIFT_RELATIVE_PATHS = [
    "scripts/evaluation_setup.py",
    "scripts/setup_orchestrator.py",
    "scripts/setup_artifacts.py",
    "scripts/git_preflight.py",
    "setup/evaluation-catalog.json",
    "templates/claude-home.gitignore",
    "schemas/evaluation-catalog-v1.schema.json",
    "schemas/evaluation-config-v1.schema.json",
    "schemas/evaluation-receipt-v1.schema.json",
    "schemas/setup-manifest-v2.schema.json",
]


@pytest.mark.parametrize("relative", DRIFT_RELATIVE_PATHS)
def test_rhize_ops_fallback_copy_matches_rhize_core_original(relative: str) -> None:
    core_path = CORE / relative
    ops_path = OPS / relative
    assert core_path.is_file(), f"missing rhize-core original: {core_path}"
    assert ops_path.is_file(), f"missing rhize-ops fallback copy: {ops_path}"
    assert core_path.read_bytes() == ops_path.read_bytes(), (
        f"{ops_path} has drifted from {core_path} -- the one-release compatibility window "
        "requires these to stay byte-identical (repo-shape R-B, Codex F6/F8)"
    )


# ---------- self-containment: path-preference functions resolve correctly without rhize-core ----------

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ops_evaluation_setup = _load_module(OPS / "scripts" / "evaluation_setup.py", "ops_fallback_evaluation_setup")
ops_setup_artifacts = _load_module(OPS / "scripts" / "setup_artifacts.py", "ops_fallback_setup_artifacts")


def test_catalog_relative_path_prefers_own_plugin_when_rhize_core_absent(tmp_path: Path) -> None:
    (tmp_path / "rhize-ops").mkdir()
    resolved = ops_evaluation_setup.catalog_relative_path(tmp_path)
    # own_plugin is derived from where THIS loaded copy lives on disk (rhize-ops), not tmp_path.
    assert resolved == Path("rhize-ops") / "setup" / "evaluation-catalog.json"


def test_catalog_relative_path_prefers_rhize_core_when_present(tmp_path: Path) -> None:
    (tmp_path / "rhize-ops").mkdir()
    (tmp_path / "rhize-core").mkdir()
    resolved = ops_evaluation_setup.catalog_relative_path(tmp_path)
    assert resolved == Path("rhize-core") / "setup" / "evaluation-catalog.json"


def test_doc_relative_path_prefers_own_plugin_when_rhize_core_absent(tmp_path: Path) -> None:
    (tmp_path / "rhize-ops").mkdir()
    resolved = ops_setup_artifacts.doc_relative_path(tmp_path)
    assert resolved == Path("rhize-ops") / "docs" / "setup-artifacts.md"


def test_doc_relative_path_prefers_rhize_core_when_present(tmp_path: Path) -> None:
    (tmp_path / "rhize-ops").mkdir()
    (tmp_path / "rhize-core").mkdir()
    resolved = ops_setup_artifacts.doc_relative_path(tmp_path)
    assert resolved == Path("rhize-core") / "docs" / "setup-artifacts.md"


# ---------- self-containment: setup_orchestrator.py discover, exercised end-to-end ----------

def _write_marketplace_root(root: Path, plugin_names: list[str]) -> None:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "rhize-plugins", "plugins": [{"name": n} for n in plugin_names]}),
        encoding="utf-8",
    )
    for name in plugin_names:
        plugin_dir = root / name / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": name, "version": "1.0.0"}), encoding="utf-8",
        )


def _run_ops_fallback_discover(*args: str) -> tuple[int, dict]:
    completed = subprocess.run(
        ["python3", str(OPS / "scripts" / "setup_orchestrator.py"), "discover", "--json", *args],
        capture_output=True, text=True, check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout, "stderr": completed.stderr}
    return completed.returncode, payload


def test_discover_recognizes_a_marketplace_with_only_rhize_ops(tmp_path: Path) -> None:
    dev_repo = tmp_path / "dev-repo"
    _write_marketplace_root(dev_repo, ["rhize-ops"])
    home = tmp_path / "home"
    code, result = _run_ops_fallback_discover("--home", str(home), "--project", str(dev_repo))
    assert code == 0, result
    assert result["source"]["kind"] == "dev-repo"
    assert {p["name"] for p in result["plugins"]} == {"rhize-ops"}


def test_discover_recognizes_a_marketplace_with_only_rhize_core(tmp_path: Path) -> None:
    dev_repo = tmp_path / "dev-repo"
    _write_marketplace_root(dev_repo, ["rhize-core"])
    home = tmp_path / "home"
    code, result = _run_ops_fallback_discover("--home", str(home), "--project", str(dev_repo))
    assert code == 0, result
    assert result["source"]["kind"] == "dev-repo"
    assert {p["name"] for p in result["plugins"]} == {"rhize-core"}


def test_discover_recognizes_a_marketplace_with_both_plugins(tmp_path: Path) -> None:
    dev_repo = tmp_path / "dev-repo"
    _write_marketplace_root(dev_repo, ["rhize-ops", "rhize-core"])
    home = tmp_path / "home"
    code, result = _run_ops_fallback_discover("--home", str(home), "--project", str(dev_repo))
    assert code == 0, result
    assert result["source"]["kind"] == "dev-repo"
    assert {p["name"] for p in result["plugins"]} == {"rhize-ops", "rhize-core"}


def test_discover_rejects_a_marketplace_with_neither_signature_plugin(tmp_path: Path) -> None:
    dev_repo = tmp_path / "dev-repo"
    _write_marketplace_root(dev_repo, ["some-other-plugin"])
    home = tmp_path / "home"
    code, result = _run_ops_fallback_discover("--home", str(home), "--project", str(dev_repo))
    assert code == 2
    assert "error" in result
