#!/usr/bin/env python3
"""Framework and fail-closed tests for the data-mutation-consistency analyzers, driven
through the real scripts (`analyze_mutations.py` / `check_single_file.py`) exactly as
`/rhize-devflow:mutation-check` invokes them — not through a reimplementation.

Designated home per the plan's Planned File Map
(`tests/rhize-devflow/test_mutation_analysis.py — framework and truncation tests`) and
Task 7's Verify list: "clean and failing fixtures for Server Actions, React Query, Payload,
Sanity, Supabase, large file sets, parser failure".

Fixtures live under `tests/rhize-devflow/fixtures/mutation/`. Every expected score/status
below was captured by actually running the scripts against the fixture (not hand-computed
from the scoring weights) — see the Task 7 executor notes for the exact commands.

Two documented, pre-existing scoring-model gaps surface here (out of scope for this task —
only fail-closed behavior was in scope, not new pattern-matching coverage):

- Payload collection scoring never calls the shared `_check_elements` step, so
  `has_error_handling`/`has_type_safety` are always False for Payload mutations — even a
  fully-hooked collection tops out at 7.0/10 ("warning"), never "passing". See
  `test_payload_clean_fixture_still_warns_not_passes_a_documented_scoring_gap`.
- The pattern matcher has no Sanity-specific detection: `detect_sub_skills` correctly flags
  a `@sanity/client` dependency, but a real Sanity `client.patch().commit()` mutation is
  never scored (0 mutations found, defaults to a trivial "no_mutations" pass). See
  `test_sanity_dependency_detected_but_mutation_pattern_not_yet_scored`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "rhize-devflow" / "skills" / "data-mutation-consistency" / "scripts"
ANALYZE = SCRIPTS / "analyze_mutations.py"
CHECK_FILE = SCRIPTS / "check_single_file.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mutation"

assert ANALYZE.is_file(), f"missing {ANALYZE}"
assert CHECK_FILE.is_file(), f"missing {CHECK_FILE}"


def run_check_single_file(file_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK_FILE), "--file", str(file_path), "--json", *extra_args],
        capture_output=True,
        text=True,
    )


def run_analyze(root: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ANALYZE), "--root", str(root), "--no-file-output", "--json", *extra_args],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Server Actions (Supabase mutation inside a 'use server' function)
# ---------------------------------------------------------------------------


def test_server_action_clean_fixture_passes() -> None:
    result = run_check_single_file(FIXTURES / "server_action_clean.ts")
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "passing"
    assert payload["score"] == 10.0


def test_server_action_failing_fixture_is_critical() -> None:
    result = run_check_single_file(FIXTURES / "server_action_failing.ts")
    payload = json.loads(result.stdout)
    assert result.returncode == 2  # critical exit code
    assert payload["status"] == "critical"
    assert payload["score"] == 0.0


# ---------------------------------------------------------------------------
# React Query
# ---------------------------------------------------------------------------


def test_react_query_clean_fixture_passes() -> None:
    result = run_check_single_file(
        FIXTURES / "react_query_clean.ts", "--sub-skills", "react-query-mutations"
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "passing"
    assert payload["score"] == 10.0
    assert payload["mutations"][0]["missing"] == []


def test_react_query_failing_fixture_is_critical() -> None:
    result = run_check_single_file(
        FIXTURES / "react_query_failing.ts", "--sub-skills", "react-query-mutations"
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "critical"
    assert payload["score"] == 0.0
    assert set(payload["mutations"][0]["missing"]) == {
        "error_handling",
        "type_safety",
        "query_key_factory",
        "on_error_handler",
        "on_settled_handler",
        "optimistic_ui",
        "rollback_logic",
        "user_feedback",
    }


# ---------------------------------------------------------------------------
# Payload CMS
# ---------------------------------------------------------------------------


def test_payload_clean_fixture_still_warns_not_passes_a_documented_scoring_gap() -> None:
    """Real, currently-shipped behavior: Payload collection mutations never go through
    `_check_elements`, so error_handling/type_safety are structurally unscoreable for this
    category. A collection with every Payload-specific hook present (afterChange,
    afterDelete, beforeChange, both with cache revalidation) still lands at 7.0/10
    ("warning"), not "passing". This test pins that real behavior rather than an
    aspirational one — fixing the underlying pattern-matcher gap is new scope, not part of
    the fail-closed fix this task covers."""
    result = run_check_single_file(FIXTURES / "payload_clean.ts", "--sub-skills", "payload-cms-hooks")
    payload = json.loads(result.stdout)
    assert result.returncode == 1  # warning exit code
    assert payload["status"] == "warning"
    assert payload["score"] == 7.0
    assert set(payload["mutations"][0]["present"]) == {
        "after_change_hook",
        "after_change_cache",
        "after_delete_hook",
        "after_delete_cache",
        "before_change_validation",
    }
    assert set(payload["mutations"][0]["missing"]) == {"error_handling", "type_safety"}


def test_payload_failing_fixture_is_critical() -> None:
    result = run_check_single_file(FIXTURES / "payload_failing.ts", "--sub-skills", "payload-cms-hooks")
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "critical"
    assert payload["score"] == 0.0


# ---------------------------------------------------------------------------
# Supabase (client-side, non-server-action mutation)
# ---------------------------------------------------------------------------


def test_supabase_client_clean_fixture_passes() -> None:
    result = run_check_single_file(FIXTURES / "lib" / "supabase_client_clean.ts")
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "passing"
    assert payload["score"] == 10.0


def test_supabase_client_failing_fixture_is_critical() -> None:
    result = run_check_single_file(FIXTURES / "lib" / "supabase_client_failing.ts")
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "critical"
    assert payload["score"] == 0.0


# ---------------------------------------------------------------------------
# Sanity — dependency detection works; mutation scoring does not exist yet (documented gap)
# ---------------------------------------------------------------------------


def test_sanity_dependency_detected_but_mutation_pattern_not_yet_scored() -> None:
    sys.path.insert(0, str(SCRIPTS))
    try:
        from common.patterns import detect_sub_skills  # type: ignore
    finally:
        sys.path.remove(str(SCRIPTS))

    project = FIXTURES / "sanity_project"
    assert "sanity-cms-hooks" in detect_sub_skills(project)

    result = run_check_single_file(
        project / "lib" / "sanityMutation.ts", "--root", str(project)
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    # Honest current behavior: no Sanity-specific pattern exists, so the real
    # client.patch().commit() call in this fixture is invisible to the matcher.
    assert payload["status"] == "no_mutations"
    assert payload["mutations_found"] == 0


# ---------------------------------------------------------------------------
# Fail-closed: large file sets, unreadable files, malformed config
# ---------------------------------------------------------------------------

FAILED_CLOSED_EXIT_CODE = 3


def test_analyze_fails_closed_on_large_file_set_instead_of_truncating() -> None:
    """5 fixture files exist under large_file_set/; --max-files 2 must refuse the whole
    run rather than silently analyzing 2 of the 5 and reporting a complete-looking score."""
    result = run_analyze(FIXTURES / "large_file_set", "--max-files", "2")
    assert result.returncode == FAILED_CLOSED_EXIT_CODE
    assert "FAILED CLOSED" in result.stderr
    assert "exceeds --max-files" in result.stderr
    # No JSON summary on stdout — a failed-closed run must not emit anything that could be
    # mistaken for a completed analysis.
    assert result.stdout.strip() in ("", "Analyzing mutations...")


def test_analyze_fails_closed_on_unreadable_file_instead_of_skipping_it() -> None:
    """broken.ts contains invalid UTF-8 bytes; the previous behavior silently skipped it
    with a stderr warning and reported the rest of the project as if it were the complete
    picture. It must now abort the run instead."""
    result = run_analyze(FIXTURES / "parse_error_project")
    assert result.returncode == FAILED_CLOSED_EXIT_CODE
    assert "FAILED CLOSED" in result.stderr
    assert "could not be read" in result.stderr
    assert "broken.ts" in result.stderr


def test_analyze_fails_closed_on_malformed_config_instead_of_falling_back_silently() -> None:
    """.claude/mutation-patterns.yaml is malformed YAML. This must not be swallowed and
    replaced with default config (which would silently change scoring weights the user
    thought they had configured) — it must abort with a non-zero exit."""
    result = run_analyze(FIXTURES / "malformed_config_project")
    assert result.returncode != 0
    assert "yaml" in result.stderr.lower() or "scannererror" in result.stderr.lower()


def test_check_single_file_fails_closed_on_missing_file() -> None:
    result = run_check_single_file(FIXTURES / "does-not-exist.ts")
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert result.returncode == FAILED_CLOSED_EXIT_CODE


def test_analyze_within_max_files_default_still_succeeds() -> None:
    """Control case: the default --max-files (5000), and a directory with no unreadable
    files, must not fail closed — fail-closed is a refusal at the threshold/on a genuine
    read failure, not a universal block. Scoped to fixtures/mutation/lib/ (2 small, valid
    files) rather than the fixtures/mutation/ root, which also contains the
    intentionally-broken and malformed-config fixtures used by the tests above."""
    result = run_analyze(FIXTURES / "lib")
    assert result.returncode in (0, 1, 2)  # passing/warning/critical, never fail-closed (3)
