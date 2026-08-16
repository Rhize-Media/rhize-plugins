#!/usr/bin/env python3
"""Command-contract tests for rhize-devflow (Task 5 of the Dev Flow 3.0 control-plane plan —
see .claude/plans/rhize-devflow-v3-engineering-control-plane.md, "Target Command Contracts"
and "Task 5 — Implement `/check`").

This is the designated home for command-contract tests per the plan's Planned File Map
(`tests/rhize-devflow/test_command_contracts.py — ownership/safety/verdict contracts`).
`/rhize-devflow:check` is its first occupant.

Two kinds of coverage:

1. Static text-contract checks against `rhize-devflow/commands/check.md` — canonical marker,
   verdict vocabulary, the no-Markdown-derived-execution prohibition, the multi-root
   requirement, the no-external-mutation rule, and the `devflow.py evidence` reference.
   Mirrors the style already established in test_impact_map_contract.py and
   test_plugin_integrity.py (substring/section assertions against the shipped command body,
   not a parser).

2. Fixture-driven evidence tests — `/check` itself is an agent workflow, not something
   pytest executes. These exercise the deterministic half: run `devflow.py evidence --json`
   against each of the seven representative repos built by
   tests/rhize-devflow/fixtures/check_scenarios.py and assert the evidence packet gives the
   agent what the command text needs to reach the right verdict (e.g. the docs-only fixture
   changes only .md files; the unavailable-dependency fixture declares scripts with no
   lockfile present).

devflow.py was not modified for this task — every fixture assertion below is satisfiable
from evidence fields that already existed after Task 3 (changed_files, package_scripts,
package_manager.lockfiles, protected_matches, findings[].severity).
"""
from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVFLOW = REPO_ROOT / "rhize-devflow"
CHECK = DEVFLOW / "commands" / "check.md"
DEVFLOW_SCRIPT = DEVFLOW / "scripts" / "devflow.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

assert CHECK.exists(), f"missing {CHECK}"
assert DEVFLOW_SCRIPT.is_file(), f"missing {DEVFLOW_SCRIPT}"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


scenarios = _load_module("check_scenarios", FIXTURES / "check_scenarios.py")

CANONICAL_MARKER = "<!-- canonical: rhize-devflow:check -->"


def read(path: Path) -> str:
    return path.read_text(errors="ignore")


def run_evidence_cli(repo: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(DEVFLOW_SCRIPT), "evidence", "--json", "--repo", str(repo)],
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# 1. Canonical marker
# ---------------------------------------------------------------------------


def test_check_command_exists_and_carries_the_canonical_marker() -> None:
    assert CHECK.exists()
    text = read(CHECK)
    lines = text.splitlines()
    # "right after its frontmatter" — same convention as impact-map.md's marker placement.
    fm_end = next(i for i, line in enumerate(lines) if i > 0 and line.strip() == "---")
    following = [line for line in lines[fm_end + 1 : fm_end + 3] if line.strip()]
    assert following and following[0] == CANONICAL_MARKER, (
        f"expected {CANONICAL_MARKER!r} immediately after frontmatter, got: {following}"
    )


# ---------------------------------------------------------------------------
# 2. Verdict vocabulary: PASS / PASS_WITH_WARNINGS / BLOCKED, no rogue verdict word
# ---------------------------------------------------------------------------

_BACKTICKED_ALLCAPS = re.compile(r"`([A-Z][A-Z_]+)`")
_EXPECTED_VERDICTS = {"PASS", "PASS_WITH_WARNINGS", "BLOCKED"}


def test_check_verdict_vocabulary_is_exactly_pass_pass_with_warnings_blocked() -> None:
    text = read(CHECK)
    for required in ("`PASS`", "`PASS_WITH_WARNINGS`", "`BLOCKED`"):
        assert required in text, f"missing required verdict token: {required}"

    found = set(_BACKTICKED_ALLCAPS.findall(text))
    rogue = found - _EXPECTED_VERDICTS
    assert rogue == set(), (
        f"check.md contains backticked ALL_CAPS token(s) outside the stable verdict "
        f"vocabulary {_EXPECTED_VERDICTS}: {rogue}"
    )
    assert found == _EXPECTED_VERDICTS, (
        f"check.md must use exactly one verdict vocabulary; found {found}"
    )


def test_check_exactly_one_verdict_is_returned() -> None:
    text = read(CHECK)
    assert "Return exactly one of:" in text or "exactly one" in text.lower()
    assert "one of `PASS`" not in text  # would suggest a fixed list phrased ambiguously
    # The verdict section must not offer a fourth named outcome.
    verdict_section_start = text.index("## Phase 5: Report One Verdict")
    verdict_section = text[verdict_section_start : text.index("## Safety")]
    for verdict in _EXPECTED_VERDICTS:
        assert f"`{verdict}`" in verdict_section


# ---------------------------------------------------------------------------
# 3. No Markdown/provenance/report-derived execution
# ---------------------------------------------------------------------------


def test_check_prohibits_markdown_derived_execution() -> None:
    text = read(CHECK)
    lowered = text.lower()
    assert "never execute shell text extracted from markdown" in lowered
    for source in ("provenance files", "generated reports"):
        assert source in lowered
    assert "evidence, not permission" in lowered or "facts, not permission" in lowered


def test_check_selects_checks_only_from_two_named_sources() -> None:
    text = read(CHECK)
    assert "Select checks from exactly two sources" in text
    assert "Repository instructions" in text
    assert "Known-safe declared package scripts" in text
    assert "never select a check because a readme" in text.lower() or (
        "never select a check because" in text.lower()
    )


# ---------------------------------------------------------------------------
# 4. Multi-root requirement
# ---------------------------------------------------------------------------


def test_check_requires_treating_every_repository_root_independently() -> None:
    text = read(CHECK)
    lowered = text.lower()
    assert "every repository root" in lowered
    assert "treat each independently" in lowered or "treat each root independently" in lowered
    assert "report each separately" in lowered or "report multiple roots separately" in lowered or (
        "never share one verdict" in lowered
    )


# ---------------------------------------------------------------------------
# 5. No external mutation
# ---------------------------------------------------------------------------


def test_check_forbids_commit_push_pr_deploy_or_external_mutation() -> None:
    text = read(CHECK)
    lowered = text.lower()
    assert "## safety" in lowered
    safety_section = text[text.index("## Safety") : text.index("## Related Workflows")]
    safety_lowered = safety_section.lower()
    for forbidden in ("commit", "push", "pr", "deploy", "external mutation"):
        assert forbidden in safety_lowered, f"Safety section missing prohibition of: {forbidden}"
    assert "never" in safety_lowered or "no commit" in safety_lowered


def test_check_never_silently_fixes_protected_file_touches() -> None:
    text = read(CHECK)
    lowered = text.lower()
    assert "never" in lowered and "fixed" in lowered
    assert "protected-file touch" in lowered


def test_check_never_silently_downgrades_a_failure_to_a_warning() -> None:
    text = read(CHECK)
    lowered = text.lower()
    assert "never" in lowered
    assert "downgraded to a warning" in lowered or "downgrade" in lowered


# ---------------------------------------------------------------------------
# 6. References the deterministic evidence CLI
# ---------------------------------------------------------------------------


def test_check_references_devflow_evidence_cli() -> None:
    text = read(CHECK)
    assert "devflow.py evidence" in text
    assert "--json" in text
    assert "--repo" in text


def test_check_never_initializes_codegraph() -> None:
    text = read(CHECK)
    assert "codegraph init" not in text.lower()
    assert "never initialize" in text.lower() or "never initializes" in text.lower()


# ---------------------------------------------------------------------------
# 7. Routing: dev-flow-foundations documents impact-map -> check -> review sequencing
# ---------------------------------------------------------------------------


def test_foundations_skill_routes_to_check() -> None:
    skill = read(DEVFLOW / "skills" / "dev-flow-foundations" / "SKILL.md")
    assert "/rhize-devflow:check" in skill
    assert "impact-map" in skill.lower()
    assert "review" in skill.lower()


# ---------------------------------------------------------------------------
# Fixture-driven evidence tests — the deterministic half of the seven check scenarios
# ---------------------------------------------------------------------------


def test_frontend_root_evidence_exposes_all_four_gate_scripts(tmp_path: Path) -> None:
    repo = scenarios.build_frontend_root(tmp_path)
    doc = run_evidence_cli(repo)
    assert doc["package_scripts"].keys() == {"test", "lint", "typecheck", "build"}
    assert doc["package_manager"]["lockfiles"] == ["npm"]
    changed = {c["path"] for c in doc["git"]["changed_files"]}
    assert "src/Widget.tsx" in changed


def test_backend_root_evidence_exposes_python_stack_no_package_json(tmp_path: Path) -> None:
    repo = scenarios.build_backend_root(tmp_path)
    doc = run_evidence_cli(repo)
    assert doc["package_scripts"] is None
    assert doc["package_manager"]["python"]["pyproject_toml"] is True
    changed = {c["path"] for c in doc["git"]["changed_files"]}
    assert "app/routes.py" in changed


def test_unavailable_dependency_evidence_shows_scripts_with_no_lockfile(tmp_path: Path) -> None:
    """Declared scripts + an empty lockfiles list is the signal that lets the agent report
    the gate as unavailable rather than assuming dependencies are installed."""
    repo = scenarios.build_unavailable_dependency(tmp_path)
    doc = run_evidence_cli(repo)
    assert doc["package_scripts"].keys() == {"test", "build"}
    assert doc["package_manager"]["lockfiles"] == []


def test_failing_focused_test_evidence_reports_exact_command_that_fails(tmp_path: Path) -> None:
    """Evidence reports the script's exact command text; running that exact text (standing
    in for the agent selecting and running it) genuinely fails — proving the evidence packet
    carries what's needed to reach BLOCKED, without devflow.py itself executing anything."""
    repo = scenarios.build_failing_focused_test(tmp_path)
    doc = run_evidence_cli(repo)
    test_command = doc["package_scripts"]["test"]
    assert test_command == 'python3 -c "import sys; sys.exit(1)"'
    result = subprocess.run(shlex.split(test_command), cwd=repo, capture_output=True)
    assert result.returncode != 0


def test_failing_required_build_evidence_reports_exact_command_that_fails(tmp_path: Path) -> None:
    repo = scenarios.build_failing_required_build(tmp_path)
    doc = run_evidence_cli(repo)
    test_command = doc["package_scripts"]["test"]
    build_command = doc["package_scripts"]["build"]
    test_result = subprocess.run(shlex.split(test_command), cwd=repo, capture_output=True)
    build_result = subprocess.run(shlex.split(build_command), cwd=repo, capture_output=True)
    assert test_result.returncode == 0, "focused test must pass in this fixture"
    assert build_result.returncode != 0, "required build must fail in this fixture"


def test_legitimate_warning_evidence_reports_severity_warning_not_error(tmp_path: Path) -> None:
    repo = scenarios.build_legitimate_warning(tmp_path)
    doc = run_evidence_cli(repo)
    assert ".env.local" in doc["protected_matches"]
    protected_findings = [f for f in doc["findings"] if f["id"] == "protected-file-touch"]
    assert len(protected_findings) == 1
    assert protected_findings[0]["severity"] == "warning"
    assert doc["instruction_files"]["CLAUDE.md"] is True


def test_docs_only_change_evidence_changed_files_are_all_markdown(tmp_path: Path) -> None:
    repo = scenarios.build_docs_only_change(tmp_path)
    doc = run_evidence_cli(repo)
    changed_paths = [c["path"] for c in doc["git"]["changed_files"]]
    assert changed_paths, "fixture must have at least one changed file"
    assert all(path.endswith(".md") for path in changed_paths), changed_paths
    # Gate scripts are declared (repo has package.json), but nothing code-related changed —
    # the evidence packet gives the agent no changed source file to justify running them.
    assert doc["package_scripts"].keys() == {"test", "build"}
