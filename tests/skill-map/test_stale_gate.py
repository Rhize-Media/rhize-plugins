#!/usr/bin/env python3
"""test_stale_gate.py — negative test for the weekly-skill-audit's step 0 gate.

Background: the audit's SKILL.md (~/Documents/Claude/Scheduled/weekly-skill-audit/
SKILL.md, step 0) says "on stale map: rebuild, commit the fix, and STOP the audit".
Before this test, only the *positive* half was covered — tests/skill-map/test_build.py
proves the artifact currently matches sources, and scripts/validate_skill_map.py's
own `--check-stale` exits nonzero when it doesn't (exercised ad hoc, never as a
committed regression test). Nobody had exercised the *negative* branch: seed real
drift, confirm the gate actually fires, confirm the prescribed rebuild clears it,
and confirm the resulting diff is exactly what the audit is allowed to commit.

Mapping of audit-SKILL.md prose to the assertions below (so this docstring is the
audit-step ↔ test-line cross-reference the task asked for):

  Audit step 0, sentence 1 ("Rebuild ... then validate the committed one isn't
  stale"):
    -> test seeds staleness, then runs `validate_skill_map.py --check-stale`
       BEFORE rebuilding and asserts returncode != 0 (test_stale_gate_full_cycle,
       "check-stale must FAIL on seeded drift").

  Audit step 0, sentence 2 ("Rule: if --check-stale fails, commit the freshly
  rebuilt generated/skill-map.static.json ... then STOP the rest of this audit
  run"):
    -> "commit": the test runs the exact rebuild commands the audit lists
       (build_skill_map.py; build_local_skill_map.py), re-runs --check-stale and
       asserts returncode == 0, asserts `git status --porcelain` shows only the
       generated/* artifacts plus the one seeded source file, then git-commits
       those paths and asserts a clean tree afterward.
    -> "STOP the rest of this audit run": there is no script-level object to
       assert on for "stop" — stopping is a behavioral instruction to the LLM
       agent running the audit, not a subprocess exit code. The mechanically
       testable proxy is the exit code --check-stale returns, since that is the
       one and only signal step 0's prose says the audit keys its go/no-go
       decision on. This test asserts that signal flips FAIL -> PASS across the
       seed -> rebuild boundary, which is the full extent of what a script can
       verify about a prose "stop" instruction. See RESIDUAL GAP below.

RESIDUAL GAP (honestly separating "tested" from "untestable"):
  1. Whether a live audit run actually halts before its step 1 upon seeing a
     failed --check-stale is agent behavior compliance with SKILL.md prose, not
     something this repo's test suite can observe or enforce. Untestable here.
  2. The audit's step 0 also lists `build_skill_map.py --install`, which copies
     the artifact to the shared, non-repo path ~/.claude/context-manager/
     skill-map.static.json with NO path-override flag (hardcoded Path.home()).
     Running that literally against a scratch clone would overwrite the real
     machine's installed copy with this test's seeded-then-fixed content — a
     real footgun for any other concurrent session reading that shared file,
     and exactly the kind of live-tree interference this task was told to
     avoid. This test therefore does NOT execute `--install`; it exercises the
     two steps that are what --check-stale itself rebuilds and diffs against
     (`build_skill_map.py`) plus the local/live-routing build
     (`build_local_skill_map.py`, run with `--out-dir` redirected to a temp
     dir so its writes also stay off the shared path). `--install`'s own
     correctness is an unconditional copy of an already-validated artifact —
     it is not part of the stale-detection logic under test.
  3. `build_skill_map.py` reads real third-party plugin/marketplace inventory
     under $HOME (~/.claude/plugins, ~/.claude/rhize-context-manager/…) with no
     override flag; sandboxing $HOME for this test (as tried during
     development) breaks the build with a dangling-edge error unrelated to the
     seeded staleness. So this test runs with the real $HOME for *reads*
     (harmless — build_skill_map.py itself does not write outside the repo
     unless given --install) and only redirects the additional writes
     `build_local_skill_map.py` would otherwise make under $HOME.

Runs against a `git clone --local` scratch copy of this repo (cheap: a --local
clone hardlinks objects), never the live working tree — other test lanes may be
running concurrently there.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_FILE_REL = Path("seo-aeo-geo/skills/content-seo/SKILL.md")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_stale_gate_full_cycle(tmp_path: Path) -> None:
    clone_dir = tmp_path / "repo-clone"
    out_dir = tmp_path / "local-build-out"

    # --- setup: cheap local clone, never the live tree ---
    subprocess.run(
        ["git", "clone", "--local", "--quiet", str(REPO_ROOT), str(clone_dir)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(clone_dir), "config", "user.email", "stale-gate-test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(clone_dir), "config", "user.name", "stale-gate-test"],
        check=True,
    )

    # --- seed genuine staleness: append harmless text to a real skill's
    # frontmatter description so the rebuilt artifact's content-hash for that
    # skill node differs from the committed one. ---
    seed_path = clone_dir / SEED_FILE_REL
    original = seed_path.read_text(encoding="utf-8")
    marker = "(stale-gate-test)"
    assert marker not in original, "seed file already carries the test marker"
    seeded = re.sub(
        r'(?m)^(description: >\n(?:  .*\n)*)',
        lambda m: m.group(1)[:-1] + f" {marker}\n",
        original,
        count=1,
    )
    assert seeded != original, "failed to seed a description change — regex didn't match"
    seed_path.write_text(seeded, encoding="utf-8")

    # --- audit step 0, sentence 1: check-stale must FAIL on seeded drift ---
    pre = _run(["scripts/validate_skill_map.py", "--check-stale"], cwd=clone_dir)
    assert pre.returncode != 0, (
        f"expected --check-stale to FAIL on seeded drift, got exit "
        f"{pre.returncode}\nstdout={pre.stdout}\nstderr={pre.stderr}"
    )
    assert "FAIL" in pre.stdout, pre.stdout

    # --- audit step 0's prescribed rebuild (build_skill_map.py + install +
    # build_local_skill_map.py). --install is deliberately NOT run here — see
    # RESIDUAL GAP #2 in the module docstring. ---
    build = _run(["scripts/build_skill_map.py"], cwd=clone_dir)
    assert build.returncode == 0, f"build_skill_map.py failed:\n{build.stdout}\n{build.stderr}"

    local_build = _run(
        ["scripts/build_local_skill_map.py", "--out-dir", str(out_dir)],
        cwd=clone_dir,
    )
    assert local_build.returncode == 0, (
        f"build_local_skill_map.py failed:\n{local_build.stdout}\n{local_build.stderr}"
    )

    # --- audit step 0, sentence 2: check-stale must now PASS ---
    post = _run(["scripts/validate_skill_map.py", "--check-stale"], cwd=clone_dir)
    assert post.returncode == 0, (
        f"expected --check-stale to PASS after rebuild, got exit "
        f"{post.returncode}\nstdout={post.stdout}\nstderr={post.stderr}"
    )
    assert "PASS" in post.stdout, post.stdout

    # --- verify the diff is exactly what the audit is allowed to commit:
    # the regenerated artifacts plus the one seeded source file, nothing else ---
    status = subprocess.run(
        ["git", "-C", str(clone_dir), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    changed = {line[3:] for line in status.splitlines() if line.strip()}
    allowed = {
        "generated/skill-map.static.json",
        "generated/skill-map.indexes.json",
        str(SEED_FILE_REL),
    }
    required = {"generated/skill-map.static.json", str(SEED_FILE_REL)}
    assert changed <= allowed, f"unexpected changed paths outside generated/* + seed file: {changed - allowed}"
    assert required <= changed, f"expected changes missing: {required - changed}"

    # --- commit the fix, mirroring "commit the freshly rebuilt
    # generated/skill-map.static.json ... then STOP the rest of this audit run" ---
    subprocess.run(
        ["git", "-C", str(clone_dir), "add", *sorted(changed)],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(clone_dir), "commit", "-q", "-m", "test: seeded stale-gate rebuild"],
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0, f"commit failed:\n{commit.stdout}\n{commit.stderr}"

    clean_status = subprocess.run(
        ["git", "-C", str(clone_dir), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert clean_status == "", f"working tree not clean after commit:\n{clean_status}"
