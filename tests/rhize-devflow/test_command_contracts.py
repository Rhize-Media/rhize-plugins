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
CONTEXT_MANAGER = REPO_ROOT / "rhize-context-manager"
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
# 8. /rhize-devflow:mutation-check and /rhize-devflow:browser-qa (Task 7)
# ---------------------------------------------------------------------------

MUTATION_CHECK = DEVFLOW / "commands" / "mutation-check.md"
BROWSER_QA = DEVFLOW / "commands" / "browser-qa.md"
MUTATION_CHECK_MARKER = "<!-- canonical: rhize-devflow:mutation-check -->"
BROWSER_QA_MARKER = "<!-- canonical: rhize-devflow:browser-qa -->"

DEPRECATED_MUTATION_COMMANDS = [
    DEVFLOW / "commands" / "mutation-analyze.md",
    DEVFLOW / "commands" / "mutation-fix.md",
]
DEPRECATED_BROWSER_COMMANDS = [
    DEVFLOW / "commands" / "browser-debug.md",
    DEVFLOW / "commands" / "browser-help.md",
    DEVFLOW / "commands" / "browser-perf.md",
    DEVFLOW / "commands" / "browser-test.md",
]


def _canonical_marker_immediately_after_frontmatter(text: str, marker: str) -> bool:
    lines = text.splitlines()
    fm_end = next(i for i, line in enumerate(lines) if i > 0 and line.strip() == "---")
    following = [line for line in lines[fm_end + 1 : fm_end + 3] if line.strip()]
    return bool(following) and following[0] == marker


def test_mutation_check_carries_its_canonical_marker() -> None:
    assert MUTATION_CHECK.exists()
    assert _canonical_marker_immediately_after_frontmatter(read(MUTATION_CHECK), MUTATION_CHECK_MARKER)


def test_browser_qa_carries_its_canonical_marker() -> None:
    assert BROWSER_QA.exists()
    assert _canonical_marker_immediately_after_frontmatter(read(BROWSER_QA), BROWSER_QA_MARKER)


def test_mutation_check_declares_its_three_modes() -> None:
    text = read(MUTATION_CHECK)
    assert "PATH..." in text
    assert "--all" in text
    assert "--fix-plan" in text


def test_mutation_check_is_read_only_and_fix_plan_only() -> None:
    text = read(MUTATION_CHECK)
    lowered = text.lower()
    assert "never edits source" in lowered or "never edit source" in lowered
    assert "never adds todo" in lowered or "no todo" in lowered or "add todo" in lowered
    # --add-todos/--apply may be named only as explicitly prohibited flags (they write to
    # source and generate_fixes.py still implements them) — never presented as something to
    # actually pass.
    assert "never pass `--add-todos`" in lowered or "never pass ‘--add-todos’" in lowered


def test_mutation_check_documents_fail_closed_behavior() -> None:
    text = read(MUTATION_CHECK)
    lowered = text.lower()
    assert "fail" in lowered and "closed" in lowered
    assert "never a partial" in lowered or "not a partial" in lowered or "partial score" in lowered


def test_mutation_check_has_no_unresolved_skill_path_placeholder() -> None:
    assert "/path/to/skill" not in read(MUTATION_CHECK)
    assert "${CLAUDE_PLUGIN_ROOT}" in read(MUTATION_CHECK)


def test_browser_qa_covers_the_five_scenarios() -> None:
    text = read(BROWSER_QA)
    for scenario in (
        "Functional path",
        "Console and network errors",
        "Accessibility smoke",
        "Responsive layout",
        "Performance",
    ):
        assert scenario in text, f"missing scenario section: {scenario}"


def test_browser_qa_detects_capability_rather_than_assuming_one_named_tool() -> None:
    text = read(BROWSER_QA)
    lowered = text.lower()
    assert "detect" in lowered
    assert "do not assume" in lowered or "not assume a specific named mcp" in lowered
    # Names at least two distinct browser-capability families as candidates, not one.
    candidate_families = ["claude browser pane", "chrome-devtools", "claude-in-chrome", "playwright"]
    mentioned = [name for name in candidate_families if name in lowered]
    assert len(mentioned) >= 2, f"expected multiple browser-tool candidates named, found: {mentioned}"


def test_browser_qa_degrades_explicitly_when_no_browser_tool_is_available() -> None:
    text = read(BROWSER_QA)
    lowered = text.lower()
    assert "degrade" in lowered
    assert "never fabricate" in lowered or "not fabricate" in lowered


def test_browser_qa_performance_scenario_is_not_run_by_default() -> None:
    text = read(BROWSER_QA)
    performance_section_start = text.index("### 5. Performance")
    performance_section = text[performance_section_start : performance_section_start + 800]
    lowered = performance_section.lower()
    assert "on request" in lowered or "when relevant" in lowered
    assert "not run this scenario by default" in lowered or "not by default" in lowered


@pytest.mark.parametrize("adapter_path", DEPRECATED_MUTATION_COMMANDS, ids=lambda p: p.name)
def test_deprecated_mutation_commands_are_thin_adapters_to_mutation_check(adapter_path: Path) -> None:
    assert adapter_path.exists()
    text = read(adapter_path)
    assert "> **Deprecated:**" in text
    assert "/rhize-devflow:mutation-check" in text
    assert MUTATION_CHECK_MARKER not in text  # adapter must not carry the canonical body


@pytest.mark.parametrize("adapter_path", DEPRECATED_BROWSER_COMMANDS, ids=lambda p: p.name)
def test_deprecated_browser_commands_are_thin_adapters_to_browser_qa(adapter_path: Path) -> None:
    assert adapter_path.exists()
    text = read(adapter_path)
    assert "> **Deprecated:**" in text
    assert "/rhize-devflow:browser-qa" in text
    assert BROWSER_QA_MARKER not in text  # adapter must not carry the canonical body


def test_foundations_skill_routes_to_review() -> None:
    skill = read(DEVFLOW / "skills" / "dev-flow-foundations" / "SKILL.md")
    assert "/rhize-devflow:review" in skill
    assert "commands/review.md" in skill


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


# ---------------------------------------------------------------------------
# `/rhize-devflow:review` — Task 6 of the control-plane plan (restore the production
# merge/release gate). Same two-tier convention as the `/check` coverage above: static
# text-contract checks against `rhize-devflow/commands/review.md`, plus fixture-driven
# evidence tests exercising the deterministic half of the eight golden review scenarios
# built by tests/rhize-devflow/fixtures/review_scenarios.py.
# ---------------------------------------------------------------------------

REVIEW = DEVFLOW / "commands" / "review.md"
assert REVIEW.exists(), f"missing {REVIEW}"

review_scenarios = _load_module("review_scenarios", FIXTURES / "review_scenarios.py")

REVIEW_CANONICAL_MARKER = "<!-- canonical: rhize-devflow:review -->"
_REVIEW_EXPECTED_VERDICTS = {"PASS", "FAIL_WITH_FIXABLE_GAPS", "FAIL_REQUIRES_HUMAN"}


def run_evidence_cli_with_base(repo: Path, base: str | None = None) -> dict:
    cmd = [sys.executable, str(DEVFLOW_SCRIPT), "evidence", "--json", "--repo", str(repo)]
    if base is not None:
        cmd += ["--base", base]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


# 1. Canonical marker
# ---------------------------------------------------------------------------


def test_review_command_exists_and_carries_the_canonical_marker() -> None:
    assert REVIEW.exists()
    text = read(REVIEW)
    lines = text.splitlines()
    fm_end = next(i for i, line in enumerate(lines) if i > 0 and line.strip() == "---")
    following = [line for line in lines[fm_end + 1 : fm_end + 3] if line.strip()]
    assert following and following[0] == REVIEW_CANONICAL_MARKER, (
        f"expected {REVIEW_CANONICAL_MARKER!r} immediately after frontmatter, got: {following}"
    )


# 2. Verdict vocabulary: exactly PASS / FAIL_WITH_FIXABLE_GAPS / FAIL_REQUIRES_HUMAN,
#    matching the independent verifier's vocabulary at rhize-devflow/agents/verifier.md.
# ---------------------------------------------------------------------------


def test_review_verdict_vocabulary_is_exactly_the_three_merge_verdicts() -> None:
    text = read(REVIEW)
    for required in ("`PASS`", "`FAIL_WITH_FIXABLE_GAPS`", "`FAIL_REQUIRES_HUMAN`"):
        assert required in text, f"missing required verdict token: {required}"

    found = set(_BACKTICKED_ALLCAPS.findall(text))
    rogue = found - _REVIEW_EXPECTED_VERDICTS
    assert rogue == set(), (
        f"review.md contains backticked ALL_CAPS token(s) outside the stable verdict "
        f"vocabulary {_REVIEW_EXPECTED_VERDICTS}: {rogue}"
    )
    assert found == _REVIEW_EXPECTED_VERDICTS, (
        f"review.md must use exactly one verdict vocabulary; found {found}"
    )


def test_review_exactly_one_merge_verdict_is_returned() -> None:
    text = read(REVIEW)
    assert "Return exactly one of:" in text
    verdict_section_start = text.index("## Phase 6: Report One Merge Verdict")
    verdict_section = text[verdict_section_start : text.index("## Safety")]
    for verdict in _REVIEW_EXPECTED_VERDICTS:
        assert f"`{verdict}`" in verdict_section


def test_review_verdict_vocabulary_matches_the_independent_verifier_agent() -> None:
    """review.md routes to agents/verifier.md for non-trivial work (Phase 5) — its verdict
    vocabulary must not drift from the agent it delegates to."""
    verifier_text = read(DEVFLOW / "agents" / "verifier.md")
    for verdict in _REVIEW_EXPECTED_VERDICTS:
        assert verdict in verifier_text, (
            f"rhize-devflow/agents/verifier.md is missing verdict {verdict!r} that "
            "review.md's vocabulary depends on"
        )


# 3. Read-only prohibition
# ---------------------------------------------------------------------------


def test_review_is_read_only_and_never_performs_external_mutation() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    assert "read-only" in lowered
    assert "## safety" in lowered
    safety_section = text[text.index("## Safety") : text.index("## Related Workflows")]
    safety_lowered = safety_section.lower()
    for forbidden in ("commit", "push", "merge", "deploy", "edit", "external"):
        assert forbidden in safety_lowered, f"Safety section missing prohibition of: {forbidden}"
    core_contract_section = text[text.index("## Core Contract") : text.index("## Triggers")]
    assert "never commits, pushes, merges, deploys" in core_contract_section.lower()


def test_review_never_auto_approves_an_unsanctioned_workflow_touch() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    assert ".github/workflows/*" in text
    assert "fail_requires_human" in lowered
    assert "never auto-approved" in lowered


# 4. Base/head resolution — no default-branch assumption
# ---------------------------------------------------------------------------


def test_review_resolves_exact_range_before_analysis() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    assert "## phase 1: resolve the exact comparison range" in lowered
    assert "never assume the default branch is the merge target" in lowered
    assert "ambiguity" in lowered and ("ask" in lowered or "report" in lowered)
    assert "resolved_via" in text


# 5. Independent reviewer requirement with disclosed fallback
# ---------------------------------------------------------------------------


def test_review_requires_independent_reviewer_or_a_disclosed_cold_review() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    assert "independent" in lowered and "reviewer" in lowered
    assert "disclosed cold review" in lowered
    assert "did not write the change" in lowered


# 6. Risk-map coverage terms
# ---------------------------------------------------------------------------

_RISK_CATEGORIES = (
    "deployment",
    "data",
    "security",
    "authorization",
    "billing",
    "migration",
    "cache",
    "external-write",
)


def test_review_risk_map_names_every_required_category() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    risk_section_start = text.index("## Phase 3: Build the Risk Map")
    risk_section = text[risk_section_start : text.index("## Phase 4")].lower()
    for category in _RISK_CATEGORIES:
        assert category in risk_section, f"risk map missing required category: {category}"
    assert lowered.count("no fixed panel") >= 1


# 7. Preserves accepted decisions; distinguishes introduced vs pre-existing failures
# ---------------------------------------------------------------------------


def test_review_preserves_accepted_product_decisions_as_constraints() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    assert "accepted product decision" in lowered
    assert "do not relitigate scope" in lowered or "not relitigate scope" in lowered


def test_review_distinguishes_introduced_from_pre_existing_failures() -> None:
    text = read(REVIEW)
    lowered = text.lower()
    assert "introduced failures from pre-existing failures" in lowered
    assert "dismiss" in lowered


# 8. References the deterministic evidence CLI with --base
# ---------------------------------------------------------------------------


def test_review_references_devflow_evidence_cli_with_base() -> None:
    text = read(REVIEW)
    assert "devflow.py evidence" in text
    assert "--json" in text
    assert "--repo" in text
    assert "--base" in text
    assert "never initialize" in text.lower() or "never initializes" in text.lower()


# 9. done.md delegates using the same verdict vocabulary review.md defines
# ---------------------------------------------------------------------------


def test_done_delegation_verdict_vocabulary_matches_review() -> None:
    done_text = read(CONTEXT_MANAGER / "commands" / "done.md")
    for verdict in _REVIEW_EXPECTED_VERDICTS:
        assert f"`{verdict}`" in done_text, (
            f"rhize-context-manager/commands/done.md's delegation is missing verdict "
            f"{verdict!r} that review.md now defines"
        )
    assert "/rhize-devflow:review" in done_text


# ---------------------------------------------------------------------------
# Fixture-driven evidence tests — the deterministic half of the eight review golden cases
# ---------------------------------------------------------------------------


def test_cross_repo_production_release_evidence_is_reported_per_root(tmp_path: Path) -> None:
    frontend, backend = review_scenarios.build_cross_repo_production_release(tmp_path)
    frontend_doc = run_evidence_cli(frontend)
    backend_doc = run_evidence_cli(backend)
    assert frontend_doc["repo_root"] != backend_doc["repo_root"]
    assert {c["path"] for c in frontend_doc["git"]["changed_files"]} & {"app/page.tsx"}
    assert {c["path"] for c in backend_doc["git"]["changed_files"]} & {"api/handler.py"}
    text = read(REVIEW).lower()
    assert "treat each independently" in text


def test_protected_workflow_touch_evidence_flags_the_workflow_file(tmp_path: Path) -> None:
    repo = review_scenarios.build_protected_workflow_touch(tmp_path)
    doc = run_evidence_cli(repo)
    assert any(p.startswith(".github/workflows/") for p in doc["protected_matches"])
    text = read(REVIEW).lower()
    assert "unsanctioned touch to" in text and "fail_requires_human" in text


def test_migration_change_evidence_shows_migrations_path(tmp_path: Path) -> None:
    repo = review_scenarios.build_migration_change(tmp_path)
    doc = run_evidence_cli(repo)
    changed = {c["path"] for c in doc["git"]["changed_files"]}
    assert any(p.startswith("migrations/") for p in changed)
    risk_section = read(REVIEW)
    risk_section = risk_section[
        risk_section.index("## Phase 3: Build the Risk Map") : risk_section.index("## Phase 4")
    ]
    assert "migrations/" in risk_section


def test_sentry_privacy_change_evidence_shows_changed_config(tmp_path: Path) -> None:
    repo = review_scenarios.build_sentry_privacy_change(tmp_path)
    doc = run_evidence_cli(repo)
    changed = {c["path"] for c in doc["git"]["changed_files"]}
    assert "sentry.server.config.ts" in changed
    risk_section = read(REVIEW)
    risk_section = risk_section[
        risk_section.index("## Phase 3: Build the Risk Map") : risk_section.index("## Phase 4")
    ].lower()
    assert "security" in risk_section and "pii" in risk_section


def test_trivial_docs_diff_evidence_has_no_protected_or_risk_signal(tmp_path: Path) -> None:
    repo = review_scenarios.build_trivial_docs_diff(tmp_path)
    doc = run_evidence_cli(repo)
    changed = [c["path"] for c in doc["git"]["changed_files"]]
    assert changed and all(p.endswith(".md") for p in changed)
    assert doc["protected_matches"] == []
    text = read(REVIEW).lower()
    assert "trivial" in text and "no fixed panel" in text


def test_unavailable_independent_reviewer_is_disclosed_not_silently_skipped(
    tmp_path: Path,
) -> None:
    repo = review_scenarios.build_unavailable_independent_reviewer(tmp_path)
    doc = run_evidence_cli(repo)
    changed = {c["path"] for c in doc["git"]["changed_files"]}
    assert "auth.py" in changed  # non-trivial: matches the security risk category
    text = read(REVIEW).lower()
    assert "disclosed cold review" in text
    assert "never silently skip this step" in text


def test_ambiguous_target_branch_evidence_resolves_via_local_fallback(tmp_path: Path) -> None:
    repo = review_scenarios.build_ambiguous_target_branch(tmp_path)
    doc = run_evidence_cli_with_base(repo)
    assert doc["git"]["base"]["resolved_via"] == "local-fallback"
    text = read(REVIEW).lower()
    assert "local-fallback" in text
    assert "do not silently treat a guess as the merge target" in text


def test_accepted_product_constraint_evidence_shows_instruction_file_present(
    tmp_path: Path,
) -> None:
    repo = review_scenarios.build_accepted_product_constraint(tmp_path)
    doc = run_evidence_cli(repo)
    assert doc["instruction_files"]["CLAUDE.md"] is True
    assert doc["protected_matches"] == []
    text = read(REVIEW).lower()
    assert "accepted product decision" in text
    assert "not relitigate scope" in text
