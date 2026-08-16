#!/usr/bin/env python3
"""Plugin integrity contract for rhize-devflow (and the rhize-context-manager seam it shares).

Freezes the current failure surface documented in
`.claude/plans/rhize-devflow-v3-engineering-control-plane.md`, section "Why This Work Is
Needed" and "Task 1 — Freeze the current failure surface with red integrity tests".

Baseline convention
--------------------
This repository auto-pushes to `main`, so we do not leave plainly-failing tests sitting in
the suite. Every assertion that is currently false against the tree is written as the
*desired* (target) assertion and wrapped in ``@pytest.mark.xfail(strict=True, reason=...)``.
`strict=True` means: once a later plan task fixes the underlying defect, the assertion starts
passing, the test XPASSes, and pytest turns that XPASS into a hard failure — forcing whoever
lands the fix to delete the now-stale marker in the same change. Assertions that already hold
today are left unmarked and must stay green.

Each xfail `reason` names the plan task expected to fix it:
    Task 4 — canonical impact-map ownership + done.md verifier claim
    Task 7 — placeholders, byte-identical duplicate commands, adapter conventions
    Task 8 — stale Zen/Serena/Graphiti/legacy-alias requirements, missing error-lifecycle assets

Deprecation-adapter marker convention (used by the duplicate-body and canonical-owner checks)
-----------------------------------------------------------------------------------------
A command file counts as a *deprecation adapter* — exempt from "no byte-identical duplicates"
and "single canonical owner" — only if one of its lines starts with the literal marker
``> **Deprecated:**`` followed by the canonical replacement command/path. A file without that
marker is treated as carrying real, canonical workflow content, even if another copy of it
exists elsewhere.

Canonical-body marker convention (used by the impact-map single-canonical-owner check, Task 4)
-----------------------------------------------------------------------------------------
The Dev Flow canonical impact-map command (``rhize-devflow/commands/impact-map.md``) carries a
literal marker line ``<!-- canonical: rhize-devflow:impact-map -->`` right after its frontmatter.
A file counts as carrying the canonical impact-map body only if it contains this exact marker
string. This is deliberately stricter than matching on a heading name (e.g. the Phase 5
reconciliation heading), which could coincidentally reappear in a rogue copy or a byte-identical
duplicate that was never marked as a deprecation adapter — see the mutation tests below, which
prove the ownership check rejects both a second real copy and an "adapter" that still carries
copied workflow text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVFLOW = REPO_ROOT / "rhize-devflow"
CONTEXT_MANAGER = REPO_ROOT / "rhize-context-manager"

DEPRECATION_MARKER = "> **Deprecated:**"

# Literal marker line present in an impact-map command body only when it carries the real,
# canonical workflow (see the module docstring's "Canonical-body marker convention" section,
# and test_impact_map_contract.py, which pins the same file as the current owner).
IMPACT_MAP_CANONICAL_MARKER = "<!-- canonical: rhize-devflow:impact-map -->"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def read(path: Path) -> str:
    return path.read_text(errors="ignore")


def is_deprecation_adapter(text: str) -> bool:
    return any(line.startswith(DEPRECATION_MARKER) for line in text.splitlines())


def registered_command_files() -> list[Path]:
    """Every file Claude/Codex could load as a Dev Flow command body."""
    files = sorted(DEVFLOW.glob("commands/*.md"))
    files += sorted(DEVFLOW.glob("skills/*/commands/*.md"))
    return files


# ---------------------------------------------------------------------------
# 1. Advertised scripts/templates/references must exist on disk
# ---------------------------------------------------------------------------

_ASSET_PREFIXES = (
    "scripts/",
    "templates/",
    "template/",
    "reference/",
    "references/",
    "config/",
    "sub-skills/",
    "hooks/",
)
_ASSET_PATTERN = re.compile(
    r"`((?:%s)[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+)`" % "|".join(re.escape(p) for p in _ASSET_PREFIXES)
)


def missing_assets_in(markdown_path: Path, base_dir: Path) -> list[str]:
    """Relative asset paths `markdown_path` references (in backticks) that don't exist
    under `base_dir`."""
    missing = []
    for match in _ASSET_PATTERN.finditer(read(markdown_path)):
        rel = match.group(1)
        if not (base_dir / rel).exists():
            missing.append(rel)
    return missing


# (markdown file, xfail marks or None) — base_dir is always the file's own skill root.
_ASSET_CASES = [
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/ARCHITECTURE-PROPOSAL.md",
        marks=pytest.mark.xfail(
            strict=True,
            reason="fixed by Task 8 — ARCHITECTURE-PROPOSAL.md is removed/archived outside "
            "the plugin, or the hooks/sub-skills/config it claims are implemented",
        ),
        id="error-lifecycle-management/ARCHITECTURE-PROPOSAL.md",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/SKILL.md",
        marks=pytest.mark.xfail(
            strict=True,
            reason="fixed by Task 8 — SKILL.md stops advertising nonexistent scripts "
            "(check_dependencies.js, reproduce_build.sh, bundle_analyzer.js, "
            "implement_sentry.ts, add_performance_tracking.ts, performance_bisect.sh, "
            "data_integrity_check.py) and templates/reference (performance-report.md, "
            "data-recovery.md), or ships them",
        ),
        id="error-lifecycle-management/SKILL.md",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/reference/error-patterns.md",
        marks=pytest.mark.xfail(
            strict=True,
            reason="fixed by Task 8 — error-patterns.md stops advertising nonexistent "
            "scripts/check_rls_policies.sql and scripts/detect_memory_leak.js, or ships them",
        ),
        id="error-lifecycle-management/reference/error-patterns.md",
    ),
    # Control cases: these already resolve every advertised asset today and must stay green.
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/SKILL.md",
        marks=(),
        id="data-mutation-consistency/SKILL.md",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/README.md",
        marks=(),
        id="error-lifecycle-management/README.md",
    ),
    pytest.param(
        DEVFLOW / "skills/chrome-devtools-mcp/SKILL.md",
        marks=(),
        id="chrome-devtools-mcp/SKILL.md",
    ),
    pytest.param(
        DEVFLOW / "skills/sanity-development/SKILL.md",
        marks=(),
        id="sanity-development/SKILL.md",
    ),
    pytest.param(
        DEVFLOW / "skills/sentry-instrumentation/SKILL.md",
        marks=(),
        id="sentry-instrumentation/SKILL.md",
    ),
]


def skill_root_of(markdown_path: Path) -> Path:
    rel = markdown_path.relative_to(DEVFLOW / "skills")
    return DEVFLOW / "skills" / rel.parts[0]


@pytest.mark.parametrize("markdown_path", _ASSET_CASES)
def test_advertised_assets_exist(markdown_path: Path) -> None:
    assert markdown_path.exists(), f"fixture file moved or renamed: {markdown_path}"
    skill_root = skill_root_of(markdown_path)
    missing = missing_assets_in(markdown_path, skill_root)
    assert missing == [], (
        f"{markdown_path.relative_to(REPO_ROOT)} advertises assets that do not exist "
        f"under {skill_root.relative_to(REPO_ROOT)}: {missing}"
    )


# ---------------------------------------------------------------------------
# 2. No shipped command contains the unresolved `/path/to/skill` placeholder
# ---------------------------------------------------------------------------

_PLACEHOLDER = "/path/to/skill"

_PLACEHOLDER_CASES = [
    pytest.param(
        DEVFLOW / "commands/mutation-analyze.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 7 — mutation-check.md consolidation resolves the CLI path"),
        id="commands/mutation-analyze.md",
    ),
    pytest.param(
        DEVFLOW / "commands/mutation-check.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 7 — mutation-check.md consolidation resolves the CLI path"),
        id="commands/mutation-check.md",
    ),
    pytest.param(
        DEVFLOW / "commands/mutation-fix.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 7 — mutation-check.md consolidation resolves the CLI path"),
        id="commands/mutation-fix.md",
    ),
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/commands/analyze-mutations.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 7 — skill-local mutation commands become deprecation adapters"),
        id="skills/data-mutation-consistency/commands/analyze-mutations.md",
    ),
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/commands/check-mutation.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 7 — skill-local mutation commands become deprecation adapters"),
        id="skills/data-mutation-consistency/commands/check-mutation.md",
    ),
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/commands/fix-mutations.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 7 — skill-local mutation commands become deprecation adapters"),
        id="skills/data-mutation-consistency/commands/fix-mutations.md",
    ),
    # Control cases: browser commands and the setup wizard never carried this placeholder.
    pytest.param(DEVFLOW / "commands/browser-debug.md", marks=(), id="commands/browser-debug.md"),
    pytest.param(DEVFLOW / "commands/browser-help.md", marks=(), id="commands/browser-help.md"),
    pytest.param(DEVFLOW / "commands/browser-perf.md", marks=(), id="commands/browser-perf.md"),
    pytest.param(DEVFLOW / "commands/browser-test.md", marks=(), id="commands/browser-test.md"),
    pytest.param(DEVFLOW / "commands/devflow-setup.md", marks=(), id="commands/devflow-setup.md"),
]


@pytest.mark.parametrize("command_path", _PLACEHOLDER_CASES)
def test_no_unresolved_skill_path_placeholder(command_path: Path) -> None:
    assert command_path.exists(), f"fixture file moved or renamed: {command_path}"
    assert _PLACEHOLDER not in read(command_path), (
        f"{command_path.relative_to(REPO_ROOT)} still contains the literal placeholder "
        f"'{_PLACEHOLDER}'"
    )


# ---------------------------------------------------------------------------
# 3. No two registered command bodies are byte-identical unless one is a
#    documented deprecation adapter naming its canonical target.
# ---------------------------------------------------------------------------


def unjustified_duplicate_pairs() -> list[tuple[Path, Path]]:
    """(canonical, duplicate) pairs where `duplicate` is byte-identical to `canonical`
    and is not a valid deprecation adapter."""
    by_content: dict[str, list[Path]] = {}
    for path in registered_command_files():
        by_content.setdefault(read(path), []).append(path)

    violations: list[tuple[Path, Path]] = []
    for text, paths in by_content.items():
        if len(paths) < 2:
            continue
        adapters = [p for p in paths if is_deprecation_adapter(text)]
        canonical_candidates = [p for p in paths if p not in adapters]
        if not canonical_candidates:
            # Every copy claims to be an adapter — nothing canonical to point at.
            violations.extend((paths[0], p) for p in paths[1:])
            continue
        canonical = canonical_candidates[0]
        for other in paths:
            if other is canonical:
                continue
            if other not in adapters:
                violations.append((canonical, other))
    return violations


def test_no_unjustified_duplicate_command_bodies() -> None:
    violations = unjustified_duplicate_pairs()
    assert violations == [], (
        "byte-identical command bodies without a `> **Deprecated:**` marker naming a "
        "canonical target: "
        + ", ".join(
            f"{a.relative_to(REPO_ROOT)} == {b.relative_to(REPO_ROOT)}" for a, b in violations
        )
    )


test_no_unjustified_duplicate_command_bodies = pytest.mark.xfail(
    strict=True,
    reason=(
        "fixed by Task 7 — the 4 browser-*.md and 3 mutation command files ship as "
        "skill-local deprecation adapters (or are removed) instead of byte-identical copies"
    ),
)(test_no_unjustified_duplicate_command_bodies)


# ---------------------------------------------------------------------------
# 4. Exactly one canonical owner for impact-map behavior (target state: Dev Flow)
# ---------------------------------------------------------------------------


def carries_canonical_impact_map_body(path: Path) -> bool:
    return path.exists() and IMPACT_MAP_CANONICAL_MARKER in read(path)


def assert_single_canonical_impact_map_owner(devflow_command: Path, cm_command: Path) -> None:
    """Shared assertion body: `devflow_command` must carry the canonical marker, and
    `cm_command` (if present) must be a deprecation adapter that does not also carry it.

    Reused by the real ownership test below and by the mutation tests, which feed it
    synthetic paths to prove the check actually rejects a bad state rather than merely
    describing a good one.
    """
    assert carries_canonical_impact_map_body(devflow_command), (
        f"{devflow_command} should be the canonical impact-map command body (containing "
        f"the {IMPACT_MAP_CANONICAL_MARKER!r} marker), but it is missing or does not carry it"
    )

    if cm_command.exists():
        cm_text = read(cm_command)
        assert not carries_canonical_impact_map_body(cm_command), (
            f"{cm_command} still carries the canonical impact-map body — it must be a "
            "deprecation adapter (or absent) once Dev Flow owns impact-map"
        )
        assert is_deprecation_adapter(cm_text), (
            f"{cm_command} exists but is neither the canonical body nor a "
            "`> **Deprecated:**` adapter naming the Dev Flow replacement"
        )


def test_dev_flow_owns_the_canonical_impact_map_command() -> None:
    assert_single_canonical_impact_map_owner(
        DEVFLOW / "commands/impact-map.md",
        CONTEXT_MANAGER / "commands/impact-map.md",
    )


def test_mutation_second_canonical_marker_anywhere_fails(tmp_path: Path) -> None:
    """A rogue byte-identical copy of the canonical body — with no deprecation-adapter
    marker excusing it — must fail ownership, not be silently treated as harmless."""
    devflow_command = tmp_path / "devflow-impact-map.md"
    devflow_command.write_text(f"# Impact Map\n\n{IMPACT_MAP_CANONICAL_MARKER}\n\nBody.\n")
    rogue_copy = tmp_path / "rogue-impact-map.md"
    rogue_copy.write_text(devflow_command.read_text())

    with pytest.raises(AssertionError):
        assert_single_canonical_impact_map_owner(devflow_command, rogue_copy)


def test_mutation_copied_workflow_text_in_adapter_fails(tmp_path: Path) -> None:
    """An "adapter" that claims `> **Deprecated:**` but still carries the canonical marker
    (i.e. someone pasted the real workflow body back in) must still fail ownership."""
    devflow_command = tmp_path / "devflow-impact-map.md"
    devflow_command.write_text(f"# Impact Map\n\n{IMPACT_MAP_CANONICAL_MARKER}\n\nBody.\n")
    fake_adapter = tmp_path / "cm-impact-map.md"
    fake_adapter.write_text(
        f"{DEPRECATION_MARKER} use `/rhize-devflow:impact-map` instead.\n\n"
        f"{IMPACT_MAP_CANONICAL_MARKER}\n\nCopied workflow body.\n"
    )

    with pytest.raises(AssertionError):
        assert_single_canonical_impact_map_owner(devflow_command, fake_adapter)


# ---------------------------------------------------------------------------
# 5. No shipped Dev Flow workflow text requires Zen, Serena, Graphiti, or a
#    legacy `@...` command alias.
# ---------------------------------------------------------------------------

_STALE_TERM_PATTERNS = {
    "zen": re.compile(r"(?i)\bzen\b|zen_memory|mcp__zen__"),
    "serena": re.compile(r"(?i)\bserena\b|mcp__serena__"),
    "graphiti": re.compile(r"(?i)\bgraphiti\b"),
}
_LEGACY_ALIAS_PATTERN = re.compile(
    r"@(analyze-mutations|check-mutation|fix-mutations|browser-debug|browser-help|"
    r"browser-perf|browser-test)\b"
)


def stale_dependency_terms(text: str) -> list[str]:
    found = [name for name, pattern in _STALE_TERM_PATTERNS.items() if pattern.search(text)]
    if _LEGACY_ALIAS_PATTERN.search(text):
        found.append("legacy-@-alias")
    return found


_STALE_DEPENDENCY_CASES = [
    # dev-flow-foundations legacy sub-skill docs (Zen/Graphiti context-save workflows)
    pytest.param(
        DEVFLOW / "skills/dev-flow-foundations/SKILL-foundations-index.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Zen/Graphiti TODOs removed from foundations index"),
        id="dev-flow-foundations/SKILL-foundations-index.md",
    ),
    pytest.param(
        DEVFLOW / "skills/dev-flow-foundations/SKILL-regression-prevention-v1.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Zen precommit/consensus steps removed or replaced"),
        id="dev-flow-foundations/SKILL-regression-prevention-v1.md",
    ),
    pytest.param(
        DEVFLOW / "skills/dev-flow-foundations/SKILL-context-hygiene-v1.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Zen context save/restore replaced by Context Manager/STATE.md"),
        id="dev-flow-foundations/SKILL-context-hygiene-v1.md",
    ),
    # data-mutation-consistency Zen MCP memory integration
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/SKILL.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Zen MCP Memory dependency/section removed"),
        id="data-mutation-consistency/SKILL.md-zen",
    ),
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/README.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Zen MCP Memory section removed from README"),
        id="data-mutation-consistency/README.md",
    ),
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/references/zen-memory-integration.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — zen-memory-integration.md deleted after confirming no live consumer"),
        id="data-mutation-consistency/references/zen-memory-integration.md",
    ),
    pytest.param(
        DEVFLOW / "skills/data-mutation-consistency/scripts/zen_memory.py",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — zen_memory.py deleted after confirming no live consumer"),
        id="data-mutation-consistency/scripts/zen_memory.py",
    ),
    # error-lifecycle-management Serena-memory templates and stale architecture proposal
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/ARCHITECTURE-PROPOSAL.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — removed/archived outside the plugin"),
        id="error-lifecycle-management/ARCHITECTURE-PROPOSAL.md-stale-deps",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/scripts/validate_error_coverage.py",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Serena navigation reference removed"),
        id="error-lifecycle-management/scripts/validate_error_coverage.py",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/templates/triage-summary.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Serena memory format replaced with Context Manager/STATE.md persistence"),
        id="error-lifecycle-management/templates/triage-summary.md",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/templates/validation-summary.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Serena memory format replaced with Context Manager/STATE.md persistence"),
        id="error-lifecycle-management/templates/validation-summary.md",
    ),
    pytest.param(
        DEVFLOW / "skills/error-lifecycle-management/templates/pattern-doc.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — Serena memory checklist item replaced"),
        id="error-lifecycle-management/templates/pattern-doc.md",
    ),
    # legacy `@...` command aliases in shipped top-level command bodies
    pytest.param(
        DEVFLOW / "commands/mutation-analyze.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @analyze-mutations alias references removed"),
        id="commands/mutation-analyze.md-legacy-alias",
    ),
    pytest.param(
        DEVFLOW / "commands/mutation-check.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @check-mutation alias references removed"),
        id="commands/mutation-check.md-legacy-alias",
    ),
    pytest.param(
        DEVFLOW / "commands/mutation-fix.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @analyze-mutations/@fix-mutations alias references removed"),
        id="commands/mutation-fix.md-legacy-alias",
    ),
    pytest.param(
        DEVFLOW / "commands/browser-debug.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @browser-debug/@browser-test alias references removed"),
        id="commands/browser-debug.md-legacy-alias",
    ),
    pytest.param(
        DEVFLOW / "commands/browser-help.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @browser-help alias reference removed"),
        id="commands/browser-help.md-legacy-alias",
    ),
    pytest.param(
        DEVFLOW / "commands/browser-perf.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @browser-debug/@browser-test alias references removed"),
        id="commands/browser-perf.md-legacy-alias",
    ),
    pytest.param(
        DEVFLOW / "commands/browser-test.md",
        marks=pytest.mark.xfail(strict=True, reason="fixed by Task 8 — legacy @browser-test/@browser-debug alias references removed"),
        id="commands/browser-test.md-legacy-alias",
    ),
    # Control cases: these already avoid every stale dependency term and must stay green.
    pytest.param(DEVFLOW / "skills/dev-flow-foundations/SKILL.md", marks=(), id="dev-flow-foundations/SKILL.md-clean"),
    pytest.param(DEVFLOW / "skills/sanity-development/SKILL.md", marks=(), id="sanity-development/SKILL.md-clean"),
    pytest.param(DEVFLOW / "skills/sentry-instrumentation/SKILL.md", marks=(), id="sentry-instrumentation/SKILL.md-clean"),
    pytest.param(DEVFLOW / "skills/chrome-devtools-mcp/SKILL.md", marks=(), id="chrome-devtools-mcp/SKILL.md-clean"),
    pytest.param(DEVFLOW / "skills/error-lifecycle-management/README.md", marks=(), id="error-lifecycle-management/README.md-clean"),
    pytest.param(DEVFLOW / "commands/devflow-setup.md", marks=(), id="commands/devflow-setup.md-clean"),
]


@pytest.mark.parametrize("workflow_path", _STALE_DEPENDENCY_CASES)
def test_no_zen_serena_graphiti_or_legacy_alias_requirement(workflow_path: Path) -> None:
    assert workflow_path.exists(), f"fixture file moved or renamed: {workflow_path}"
    found = stale_dependency_terms(read(workflow_path))
    assert found == [], (
        f"{workflow_path.relative_to(REPO_ROOT)} requires stale dependency/alias terms: {found}"
    )


# ---------------------------------------------------------------------------
# 6. Context Manager /done must not claim a verifier bundled inside itself
# ---------------------------------------------------------------------------


def test_context_manager_done_does_not_claim_a_bundled_verifier() -> None:
    done_command = CONTEXT_MANAGER / "commands/done.md"
    devflow_verifier = DEVFLOW / "agents/verifier.md"
    cm_bundled_verifier = CONTEXT_MANAGER / "agents/verifier.md"

    assert devflow_verifier.exists(), "the verifier is expected to live at rhize-devflow/agents/verifier.md"

    text = read(done_command)
    if "bundled" in text.lower() and "agents/" in text:
        assert cm_bundled_verifier.exists(), (
            f"{done_command.relative_to(REPO_ROOT)} claims a verifier bundled in this "
            f"plugin's agents/, but {cm_bundled_verifier.relative_to(REPO_ROOT)} does not "
            "exist — the verifier lives only at rhize-devflow/agents/verifier.md"
        )
