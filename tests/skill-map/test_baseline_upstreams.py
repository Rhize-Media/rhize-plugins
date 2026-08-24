#!/usr/bin/env python3
"""test_baseline_upstreams.py — tests for the three-way drift baseline inputs.

Covers the verification bar from
docs/superpowers/specs/2026-08-10-three-way-drift-design.md:
  1. scripts/baseline_upstreams.py idempotency (run twice -> no diff).
  2. scripts/build_skill_map.py's strip_rhize_metadata_block() normalization
     rule: block present (rhize-only metadata), rhize-among-other-keys,
     metadata absent, and no-frontmatter-at-all cases.
  3. The compiler emits `baselineHash` / `contentHashNormalized` only where
     SOURCES.md actually supplies the "Upstream baseline" field / the skill
     is a fork-of source — never unconditionally.

Does not use pytest (matches this repo's other skill-map tests) — runs with
a bare `python3 tests/skill-map/test_baseline_upstreams.py`.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_skill_map.py"
BASELINE_SCRIPT = REPO_ROOT / "scripts" / "baseline_upstreams.py"

bsm = load_module(BUILD_SCRIPT, "build_skill_map")
baseline_mod = load_module(BASELINE_SCRIPT, "baseline_upstreams")


# ---------------------------------------------------------------------------
# strip_rhize_metadata_block() normalization
# ---------------------------------------------------------------------------

RHIZE_ONLY = b"""---
name: foo
description: "does a thing"
metadata:
  rhize:
    topics: [a, b]
    stacks: []
---

# Foo

Body text.
"""

RHIZE_AMONG_OTHERS = b"""---
name: foo
description: "does a thing"
metadata:
  rhize:
    topics: [a, b]
  other:
    setting: true
---

# Foo

Body text.
"""

NO_METADATA_KEY = b"""---
name: foo
description: "does a thing"
---

# Foo

Body text.
"""

NO_FRONTMATTER = b"""# Foo

Body text, no frontmatter block at all.
"""

METADATA_NO_RHIZE = b"""---
name: foo
description: "does a thing"
metadata:
  other:
    setting: true
---

# Foo

Body text.
"""


def test_strips_metadata_when_rhize_is_only_key() -> None:
    result = bsm.strip_rhize_metadata_block(RHIZE_ONLY)
    text = result.decode("utf-8")
    if "metadata:" in text or "rhize:" in text:
        raise AssertionError(f"expected metadata: block fully removed, got:\n{text}")
    if "description:" not in text or "# Foo" not in text:
        raise AssertionError("stripping removed content outside the metadata block")
    print("PASS test_strips_metadata_when_rhize_is_only_key")


def test_strips_only_rhize_subtree_when_metadata_has_other_keys() -> None:
    result = bsm.strip_rhize_metadata_block(RHIZE_AMONG_OTHERS)
    text = result.decode("utf-8")
    if "rhize:" in text:
        raise AssertionError(f"expected rhize: subtree removed, got:\n{text}")
    if "metadata:" not in text or "other:" not in text or "setting: true" not in text:
        raise AssertionError(f"expected metadata:/other: to survive, got:\n{text}")
    print("PASS test_strips_only_rhize_subtree_when_metadata_has_other_keys")


def test_no_metadata_key_is_unchanged() -> None:
    result = bsm.strip_rhize_metadata_block(NO_METADATA_KEY)
    if result != NO_METADATA_KEY:
        raise AssertionError("expected byte-identical passthrough when no metadata: key exists")
    print("PASS test_no_metadata_key_is_unchanged")


def test_no_frontmatter_is_unchanged() -> None:
    result = bsm.strip_rhize_metadata_block(NO_FRONTMATTER)
    if result != NO_FRONTMATTER:
        raise AssertionError("expected byte-identical passthrough when there is no frontmatter block")
    print("PASS test_no_frontmatter_is_unchanged")


def test_metadata_without_rhize_key_is_unchanged() -> None:
    result = bsm.strip_rhize_metadata_block(METADATA_NO_RHIZE)
    if result != METADATA_NO_RHIZE:
        raise AssertionError("expected byte-identical passthrough when metadata has no rhize key")
    print("PASS test_metadata_without_rhize_key_is_unchanged")


# ---------------------------------------------------------------------------
# baseline_upstreams.py idempotency
# ---------------------------------------------------------------------------

_SOURCES_FIXTURE = """# Fixture Ledger

## alpha — 2026-01-01
- **Source:** https://example.invalid/skills/alpha/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /nowhere
- **Took:** installed as-is
- **Verified:** n/a
- **Drift check:** `n/a`
- **Notes:** fixture entry

## beta — 2026-01-01
- **Source:** /some/local/marketplaces/fixture-mp/skills/beta
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /nowhere
- **Took:** installed as-is
- **Verified:** n/a
- **Drift check:** `n/a`
- **Notes:** local-path entry, not baseline-able

## gamma — 2026-01-01
- **Source:** https://example.invalid/skills/gamma/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /nowhere
- **Took:** installed as-is
- **Verified:** n/a
- **Drift check:** `n/a`
- **RETIRED 2026-06-01:** retired, should never be touched
"""


def _fake_fetcher(body_by_url: dict[str, bytes]):
    def fetch(url: str) -> bytes:
        return body_by_url[url]

    return fetch


def test_baseline_idempotent_and_selective() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="baseline-upstreams-test-"))
    try:
        sources_path = tmpdir / "SOURCES.md"
        sources_path.write_text(_SOURCES_FIXTURE)

        fetcher = _fake_fetcher(
            {
                "https://example.invalid/skills/alpha/SKILL.md": b"alpha upstream content v1",
                "https://example.invalid/skills/gamma/SKILL.md": b"should never be fetched",
            }
        )

        rc = baseline_mod.run(sources_path, None, fetcher=fetcher)
        if rc != 0:
            raise AssertionError(f"first run exited {rc}")
        first_pass = sources_path.read_text()

        expected_hash = hashlib.sha256(b"alpha upstream content v1").hexdigest()
        if f"sha256:{expected_hash}" not in first_pass:
            raise AssertionError("alpha's baseline hash was not written")
        if "gamma" in first_pass.split("## beta")[0]:  # sanity: fixture order intact
            pass
        if "Upstream baseline" in first_pass.split("## gamma")[1]:
            raise AssertionError("retired entry 'gamma' must never gain a baseline bullet")
        if "Upstream baseline" in first_pass.split("## beta")[1].split("## gamma")[0]:
            raise AssertionError("local-path entry 'beta' must never gain a baseline bullet")

        rc2 = baseline_mod.run(sources_path, None, fetcher=fetcher)
        if rc2 != 0:
            raise AssertionError(f"second run exited {rc2}")
        second_pass = sources_path.read_text()
        if first_pass != second_pass:
            raise AssertionError(
                "second run against unchanged upstream produced a diff — not idempotent"
            )
        print("PASS test_baseline_idempotent_and_selective")

        # Upstream content changes -> baseline bullet is updated in place.
        fetcher2 = _fake_fetcher(
            {
                "https://example.invalid/skills/alpha/SKILL.md": b"alpha upstream content v2",
                "https://example.invalid/skills/gamma/SKILL.md": b"should never be fetched",
            }
        )
        rc3 = baseline_mod.run(sources_path, "alpha", fetcher=fetcher2)
        if rc3 != 0:
            raise AssertionError(f"third run exited {rc3}")
        third_pass = sources_path.read_text()
        new_hash = hashlib.sha256(b"alpha upstream content v2").hexdigest()
        if f"sha256:{new_hash}" not in third_pass:
            raise AssertionError("alpha's baseline hash was not updated after upstream changed")
        if third_pass.count("Upstream baseline") != 1:
            raise AssertionError("expected exactly one baseline bullet for alpha, no duplicates")
        print("PASS test_baseline_updates_on_changed_upstream")
    finally:
        shutil.rmtree(tmpdir)


def test_baseline_skill_filter_scopes_to_one_entry() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="baseline-upstreams-test-"))
    try:
        sources_path = tmpdir / "SOURCES.md"
        sources_path.write_text(_SOURCES_FIXTURE)
        fetcher = _fake_fetcher(
            {"https://example.invalid/skills/alpha/SKILL.md": b"alpha only"}
        )
        rc = baseline_mod.run(sources_path, "alpha", fetcher=fetcher)
        if rc != 0:
            raise AssertionError(f"run exited {rc}")
        text = sources_path.read_text()
        if "Upstream baseline" not in text.split("## beta")[0]:
            raise AssertionError("alpha should have been baselined")
        print("PASS test_baseline_skill_filter_scopes_to_one_entry")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# Compiler emission conditionality
# ---------------------------------------------------------------------------

_PLUGIN_MARKETPLACE = {
    "plugins": [{"name": "fixtureplug", "source": "./fixtureplug"}]
}


def test_compiler_emits_new_fields_only_when_sources_provides_them() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="build-skill-map-fields-test-"))
    try:
        plugin_dir = tmpdir / "fixtureplug"
        skills_dir = plugin_dir / "skills"
        (skills_dir / "withbaseline").mkdir(parents=True)
        (skills_dir / "nobaseline").mkdir(parents=True)
        (skills_dir / "notfork").mkdir(parents=True)

        skill_md = """---
name: {name}
description: "fixture skill"
metadata:
  rhize:
    topics: []
    stacks: []
---

# Fixture
"""
        (skills_dir / "withbaseline" / "SKILL.md").write_text(skill_md.format(name="withbaseline"))
        (skills_dir / "nobaseline" / "SKILL.md").write_text(skill_md.format(name="nobaseline"))
        (skills_dir / "notfork" / "SKILL.md").write_text(skill_md.format(name="notfork"))

        (skills_dir / "SOURCES.md").write_text(
            """# Fixture Ledger

## withbaseline — 2026-01-01
- **Source:** https://example.invalid/skills/withbaseline/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /nowhere
- **Took:** installed as-is
- **Verified:** n/a
- **Drift check:** `n/a`
- **Upstream baseline:** sha256:{h} (recorded 2026-08-10)
- **Notes:** has a baseline

## nobaseline — 2026-01-01
- **Source:** https://example.invalid/skills/nobaseline/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /nowhere
- **Took:** installed as-is
- **Verified:** n/a
- **Drift check:** `n/a`
- **Notes:** no baseline yet
""".format(h="a" * 64)
        )

        graph = bsm.Graph()
        for skill_name in ("withbaseline", "nobaseline", "notfork"):
            raw = (skills_dir / skill_name / "SKILL.md").read_bytes()
            graph.add_node(
                {
                    "id": f"skill:fixtureplug/{skill_name}",
                    "kind": "skill",
                    "name": skill_name,
                    "path": f"fixtureplug/skills/{skill_name}/SKILL.md",
                    "description": "fixture skill",
                    "contentHash": hashlib.sha256(raw).hexdigest(),
                }
            )
        bsm.load_sources_md(graph, "fixtureplug", plugin_dir)
        doc = graph.to_document()
        nodes_by_id = {n["id"]: n for n in doc["nodes"]}

        with_node = nodes_by_id["external:example.invalid/skills/withbaseline/SKILL.md"]
        no_node = nodes_by_id["external:example.invalid/skills/nobaseline/SKILL.md"]
        if "baselineHash" not in with_node or with_node["baselineHash"] != "a" * 64:
            raise AssertionError(f"expected baselineHash on withbaseline's external node, got {with_node}")
        if "baselineHash" in no_node:
            raise AssertionError(f"nobaseline's external node must NOT have baselineHash, got {no_node}")

        with_skill = nodes_by_id["skill:fixtureplug/withbaseline"]
        no_skill = nodes_by_id["skill:fixtureplug/nobaseline"]
        notfork_skill = nodes_by_id["skill:fixtureplug/notfork"]
        if "contentHashNormalized" not in with_skill:
            raise AssertionError("fork-of skill 'withbaseline' must have contentHashNormalized")
        if "contentHashNormalized" not in no_skill:
            raise AssertionError("fork-of skill 'nobaseline' must have contentHashNormalized")
        if "contentHashNormalized" in notfork_skill:
            raise AssertionError(
                "non-fork-of skill 'notfork' must NOT have contentHashNormalized "
                f"(it has no SOURCES.md entry), got {notfork_skill}"
            )
        print("PASS test_compiler_emits_new_fields_only_when_sources_provides_them")
    finally:
        shutil.rmtree(tmpdir)


def main() -> int:
    tests = [
        test_strips_metadata_when_rhize_is_only_key,
        test_strips_only_rhize_subtree_when_metadata_has_other_keys,
        test_no_metadata_key_is_unchanged,
        test_no_frontmatter_is_unchanged,
        test_metadata_without_rhize_key_is_unchanged,
        test_baseline_idempotent_and_selective,
        test_baseline_skill_filter_scopes_to_one_entry,
        test_compiler_emits_new_fields_only_when_sources_provides_them,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            print(f"FAIL {test.__name__}: {exc}")
            failures += 1
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print("\nAll baseline/normalization tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
