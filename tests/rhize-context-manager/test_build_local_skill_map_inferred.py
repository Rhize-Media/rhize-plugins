"""test_build_local_skill_map_inferred.py — WP-I: inferred router signals for
third-party skills (skill-governance-optimization plan, .claude/plans/
skill-governance-optimization.md).

Covers three layers, matching how the feature is actually consumed:

  1. `rhize-context-manager/scripts/build_local_skill_map.py` — the pure
     inference logic (`infer_tags_for_skill`, `load_tags_catalog`) and the
     router-signal injection (`build_resolved_indexes`), both loaded by file
     path (matching tests/rhize-context-manager/test_skill_monitor_data_dir.py's
     importlib pattern — this script is not an importable package member),
     plus an end-to-end CLI/subprocess pass covering `--report-inferred` and
     the missing-catalog degrade path.
  2. `rhize-context-manager/hooks/lib/route-core.js` — the qualification
     rule (an inferred-only match must not qualify) and the shared
     `formatSkillRef`/`formatSignalLabel` formatters, exercised via
     `node -e` (no JS test framework/package.json exists in this repo — see
     CLAUDE.md's "Tests live under tests/<plugin>/").
  3. `rhize-context-manager/hooks/skill-router.js` and
     `agent-brief-router.js` — end-to-end via spawnSync (the same harness
     tests/skill-map/test_router.js and test_agent_brief_router.js use),
     proving the three-segment id + "(inferred)" suffix rendering actually
     reaches each hook's real output, not just the shared helper.

No `.js` file is added here: this executor's file ownership is scoped to
`tests/rhize-context-manager/` (tests/skill-map/ belongs to a different
change), so every check below is driven from a `.py` test module that pytest
already discovers and runs.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_LOCAL_SKILL_MAP = (
    REPO_ROOT / "rhize-context-manager" / "scripts" / "build_local_skill_map.py"
)
ROUTE_CORE = REPO_ROOT / "rhize-context-manager" / "hooks" / "lib" / "route-core.js"
SKILL_ROUTER = REPO_ROOT / "rhize-context-manager" / "hooks" / "skill-router.js"
AGENT_BRIEF_ROUTER = REPO_ROOT / "rhize-context-manager" / "hooks" / "agent-brief-router.js"
REAL_TAGS_CATALOG = REPO_ROOT / "catalog" / "tags.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. infer_tags_for_skill() / load_tags_catalog() — pure Python unit tests
# ---------------------------------------------------------------------------


class InferTagsForSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module(
            BUILD_LOCAL_SKILL_MAP, "test_inferred__build_local_skill_map_units"
        )
        self.catalog = json.loads(REAL_TAGS_CATALOG.read_text())

    def test_matches_multi_word_and_single_word_tags(self) -> None:
        # The plan's own fixture: "keyword research for SEO" matches the
        # 2-word topic slug "keyword-research" and the 1-word stack slug
        # "seo" — both, sorted alphabetically, well under the cap of 3.
        tags = self.module.infer_tags_for_skill(
            "seo-helper", "keyword research for SEO", self.catalog
        )
        self.assertEqual(tags, ["keyword-research", "seo"])

    def test_capped_at_3_prefers_multi_word_then_alphabetical(self) -> None:
        # 6 total candidate matches (4 two-word, 2 one-word). Multi-word
        # wins over single-word; among the 4 multi-word matches only 3 fit
        # the cap, so alphabetical tie-break drops "seo-audit" (the last of
        # backlink-analysis < keyword-research < rank-tracking < seo-audit).
        description = (
            "SEO audit, keyword research, backlink analysis and rank "
            "tracking dashboard automation."
        )
        tags = self.module.infer_tags_for_skill("seo-toolkit", description, self.catalog)
        self.assertEqual(tags, ["backlink-analysis", "keyword-research", "rank-tracking"])

    def test_no_match_returns_empty_list(self) -> None:
        tags = self.module.infer_tags_for_skill(
            "widget-builder", "Builds widgets fast.", self.catalog
        )
        self.assertEqual(tags, [])

    def test_condition_tags_are_never_inferred(self) -> None:
        # A description matching only condition-vocabulary words (never
        # topic/stack) must infer nothing — conditions describe a runtime
        # failure state, not a skill's subject matter.
        catalog_with_only_conditions = [e for e in self.catalog if e["kind"] == "condition"]
        tags = self.module.infer_tags_for_skill(
            "fixer", "Fixes a build failure or type error fast.", catalog_with_only_conditions
        )
        self.assertEqual(tags, [])



    def test_deterministic_across_calls(self) -> None:
        description = "keyword research for SEO"
        first = self.module.infer_tags_for_skill("a", description, self.catalog)
        second = self.module.infer_tags_for_skill("a", description, self.catalog)
        self.assertEqual(first, second)

    def test_missing_catalog_degrades_to_no_signals_never_a_failure(self) -> None:
        entries, note = self.module.load_tags_catalog(Path("/nonexistent/tags.json"))
        self.assertEqual(entries, [])
        self.assertIn("degraded", note)
        tags = self.module.infer_tags_for_skill("seo-helper", "keyword research for SEO", entries)
        self.assertEqual(tags, [])

    def test_malformed_catalog_shape_degrades_to_no_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "tags.json"
            bad_path.write_text(json.dumps({"not": "a list"}))
            entries, note = self.module.load_tags_catalog(bad_path)
            self.assertEqual(entries, [])
            self.assertIn("degraded", note)


# ---------------------------------------------------------------------------
# 2. build_resolved_indexes() — router.signals injection
# ---------------------------------------------------------------------------


class BuildResolvedIndexesInferredTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module(
            BUILD_LOCAL_SKILL_MAP, "test_inferred__build_resolved_indexes"
        )
        self.catalog = json.loads(REAL_TAGS_CATALOG.read_text())
        self.static_indexes = {
            "schemaVersion": "1.1.0",
            "router": {
                "signals": {
                    "skill:rhize-context-manager/graphify": [
                        {"kind": "name", "weight": 1, "label": "graphify"},
                    ]
                },
                "extendsBases": {},
            },
            "disclosure": {},
            "remediation": {},
            "succession": {},
        }

    def test_schema_version_bumped_to_1_2_0(self) -> None:
        result = self.module.build_resolved_indexes(self.static_indexes, [])
        self.assertEqual(result["schemaVersion"], "1.2.0")

    def test_declared_signals_are_copied_but_never_mutated(self) -> None:
        third_party_nodes = [
            {
                "id": "skill:acme-marketplace/acme-plugin/widget-builder",
                "kind": "skill",
                "name": "widget-builder",
                "description": "Builds widgets fast.",  # matches nothing
            }
        ]
        result = self.module.build_resolved_indexes(
            self.static_indexes, [], third_party_nodes, self.catalog
        )
        self.assertEqual(
            result["router"]["signals"]["skill:rhize-context-manager/graphify"],
            [{"kind": "name", "weight": 1, "label": "graphify"}],
        )
        # Original static_indexes dict must not have been mutated in place.
        self.assertEqual(
            self.static_indexes["router"]["signals"]["skill:rhize-context-manager/graphify"],
            [{"kind": "name", "weight": 1, "label": "graphify"}],
        )

    def test_third_party_skill_gets_name_plus_tag_inferred_entries_sorted(self) -> None:
        third_party_nodes = [
            {
                "id": "skill:claude-plugins-official/mattpocock-skills/tdd",
                "kind": "skill",
                "name": "tdd",
                "description": "keyword research for SEO",
            }
        ]
        result = self.module.build_resolved_indexes(
            self.static_indexes, [], third_party_nodes, self.catalog
        )
        entries = result["router"]["signals"]["skill:claude-plugins-official/mattpocock-skills/tdd"]
        self.assertEqual(
            entries,
            [
                {"kind": "name", "weight": 1, "label": "tdd"},
                {"kind": "tag-inferred", "weight": 0.5, "label": "keyword-research"},
                {"kind": "tag-inferred", "weight": 0.5, "label": "seo"},
            ],
        )

    def test_zero_matches_still_gets_a_name_only_entry(self) -> None:
        third_party_nodes = [
            {
                "id": "skill:acme-marketplace/acme-plugin/widget-builder",
                "kind": "skill",
                "name": "widget-builder",
                "description": "Builds widgets fast.",
            }
        ]
        result = self.module.build_resolved_indexes(
            self.static_indexes, [], third_party_nodes, self.catalog
        )
        # Index membership never depends on inference hitting: a name-only entry keeps the
        # skill visible to consumers such as agent-brief-router's named-skill detection,
        # while route-core's floor (>= 2 matches, one full-weight) keeps it from qualifying.
        self.assertEqual(
            result["router"]["signals"]["skill:acme-marketplace/acme-plugin/widget-builder"],
            [{"kind": "name", "weight": 1, "label": "widget-builder"}],
        )

    def test_non_skill_third_party_nodes_are_ignored(self) -> None:
        third_party_nodes = [
            {
                "id": "plugin:acme-marketplace/acme-plugin",
                "kind": "plugin",
                "name": "acme-plugin",
                "description": "keyword research for SEO",
            }
        ]
        result = self.module.build_resolved_indexes(
            self.static_indexes, [], third_party_nodes, self.catalog
        )
        self.assertNotIn("plugin:acme-marketplace/acme-plugin", result["router"]["signals"])

    def test_deterministic_across_repeated_calls(self) -> None:
        third_party_nodes = [
            {
                "id": "skill:claude-plugins-official/mattpocock-skills/tdd",
                "kind": "skill",
                "name": "tdd",
                "description": "keyword research for SEO",
            }
        ]
        first = self.module.build_resolved_indexes(
            self.static_indexes, [], third_party_nodes, self.catalog
        )
        second = self.module.build_resolved_indexes(
            self.static_indexes, [], third_party_nodes, self.catalog
        )
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# 3. build_local_skill_map.py CLI — --report-inferred, missing catalog,
#    byte-identical reruns
# ---------------------------------------------------------------------------


def _run_build(*extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD_LOCAL_SKILL_MAP), *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


class BuildLocalSkillMapCliInferredTests(unittest.TestCase):
    def _write_fixture(self, tmp_path: Path) -> dict:
        """Mirrors tests/skill-map/test_local_build.py's fixture shape: a
        fake cached third-party plugin whose one skill's description
        matches the plan's own "keyword research for SEO" example."""
        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
        tp_marketplace, tp_plugin = "wp-i-marketplace", "wp-i-plugin"
        tp_root = tmp_path / "cache" / tp_marketplace / tp_plugin / "1.0.0"
        (tp_root / ".claude-plugin").mkdir(parents=True)
        (tp_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"description": "WP-I fixture plugin."})
        )
        (tp_root / "skills" / "seo-helper").mkdir(parents=True)
        (tp_root / "skills" / "seo-helper" / "SKILL.md").write_text(
            "---\nname: seo-helper\ndescription: keyword research for SEO\n---\n\nBody.\n"
        )

        installed_path = tmp_path / "installed_plugins.json"
        installed_plugins = {
            f"{p['name']}@{marketplace['name']}": [{"scope": "user"}]
            for p in marketplace["plugins"]
        }
        installed_plugins[f"{tp_plugin}@{tp_marketplace}"] = [
            {"scope": "user", "installPath": str(tp_root), "version": "1.0.0"}
        ]
        installed_path.write_text(json.dumps({"version": 2, "plugins": installed_plugins}))

        global_settings_path = tmp_path / "global-settings.json"
        global_settings_path.write_text(
            json.dumps({"enabledPlugins": {f"{tp_plugin}@{tp_marketplace}": True}})
        )
        local_settings_path = tmp_path / "local-settings.json"

        stack_path = tmp_path / "stack.config.json"
        stack_path.write_text(json.dumps({"schemaVersion": 2, "layers": []}))

        cooc_path = tmp_path / "no-cooccurrence.json"

        return {
            "skill_id": f"skill:{tp_marketplace}/{tp_plugin}/seo-helper",
            "args": [
                "--cooccurrence", str(cooc_path),
                "--installed-plugins", str(installed_path),
                "--stack-config", str(stack_path),
                "--global-settings", str(global_settings_path),
                "--local-settings", str(local_settings_path),
            ],
        }

    def test_report_inferred_prints_table_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = self._write_fixture(tmp_path)
            out_dir = tmp_path / "context-manager"
            result = _run_build(
                "--out-dir", str(out_dir), "--report-inferred", *fixture["args"]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(fixture["skill_id"], result.stdout)
            self.assertIn("keyword-research, seo", result.stdout)
            self.assertFalse(out_dir.exists(), "report-inferred must write nothing")

    def test_resolved_indexes_get_inferred_signal_and_schema_1_2_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = self._write_fixture(tmp_path)
            out_dir = tmp_path / "context-manager"
            result = _run_build("--out-dir", str(out_dir), *fixture["args"])
            self.assertEqual(result.returncode, 0, result.stderr)

            resolved_indexes_path = out_dir / "skill-map.indexes.resolved.json"
            self.assertTrue(resolved_indexes_path.is_file())
            doc = json.loads(resolved_indexes_path.read_text())
            self.assertEqual(doc["schemaVersion"], "1.2.0")
            entries = doc["router"]["signals"].get(fixture["skill_id"])
            self.assertIsNotNone(entries, f"expected signals for {fixture['skill_id']}")
            kinds = {(e["kind"], e["label"]) for e in entries}
            self.assertIn(("tag-inferred", "keyword-research"), kinds)
            self.assertIn(("tag-inferred", "seo"), kinds)
            self.assertIn(("name", "seo-helper"), kinds)

            local_doc = json.loads((out_dir / "skill-map.local.json").read_text())
            self.assertIn("tagsCatalog", local_doc["sourceNotes"])

    def test_two_runs_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = self._write_fixture(tmp_path)
            out_dir_a = tmp_path / "context-manager-a"
            out_dir_b = tmp_path / "context-manager-b"
            result_a = _run_build("--out-dir", str(out_dir_a), *fixture["args"])
            result_b = _run_build("--out-dir", str(out_dir_b), *fixture["args"])
            self.assertEqual(result_a.returncode, 0, result_a.stderr)
            self.assertEqual(result_b.returncode, 0, result_b.stderr)
            a_bytes = (out_dir_a / "skill-map.indexes.resolved.json").read_bytes()
            b_bytes = (out_dir_b / "skill-map.indexes.resolved.json").read_bytes()
            self.assertEqual(a_bytes, b_bytes)

    def test_missing_tags_catalog_degrades_without_failing_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = self._write_fixture(tmp_path)
            out_dir = tmp_path / "context-manager"
            result = _run_build(
                "--out-dir", str(out_dir),
                "--tags-catalog", str(tmp_path / "no-such-tags.json"),
                *fixture["args"],
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            doc = json.loads((out_dir / "skill-map.indexes.resolved.json").read_text())
            # No catalog -> no inferred signals, but the unconditional name signal stays.
            self.assertTrue(
                all(s["kind"] == "name" for s in doc["router"]["signals"][fixture["skill_id"]])
            )
            local_doc = json.loads((out_dir / "skill-map.local.json").read_text())
            self.assertIn("degraded", local_doc["sourceNotes"]["tagsCatalog"])


# ---------------------------------------------------------------------------
# 4. route-core.js — qualification rule + formatters, via `node -e`
# ---------------------------------------------------------------------------


class RouteCoreInferredNodeTests(unittest.TestCase):
    def _node(self, script: str):
        result = subprocess.run(
            ["node", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout!r} stderr={result.stderr!r}")
        return result.stdout.strip()

    def test_two_segment_id_format_is_byte_identical(self) -> None:
        script = f"""
        const rc = require({json.dumps(str(ROUTE_CORE))});
        process.stdout.write(rc.formatSkillRef('skill:rhize-context-manager/graphify'));
        """
        self.assertEqual(self._node(script), "rhize-context-manager:graphify")

    def test_three_segment_id_drops_marketplace_segment(self) -> None:
        script = f"""
        const rc = require({json.dumps(str(ROUTE_CORE))});
        process.stdout.write(
          rc.formatSkillRef('skill:claude-plugins-official/mattpocock-skills/tdd')
        );
        """
        self.assertEqual(self._node(script), "mattpocock-skills:tdd")

    def test_signal_label_suffixes_only_tag_inferred(self) -> None:
        script = f"""
        const rc = require({json.dumps(str(ROUTE_CORE))});
        const out = [
          rc.formatSignalLabel({{kind: 'tag-inferred', label: 'seo', weight: 0.5}}),
          rc.formatSignalLabel({{kind: 'tag', label: 'context', weight: 2}}),
          rc.formatSignalLabel({{kind: 'name', label: 'graphify', weight: 1}}),
          rc.formatSignalLabel({{label: 'graphify', weight: 1}}),
        ];
        process.stdout.write(JSON.stringify(out));
        """
        self.assertEqual(
            json.loads(self._node(script)),
            ["seo (inferred)", "context", "graphify", "graphify"],
        )

    def test_name_plus_one_inferred_qualifies(self) -> None:
        script = f"""
        const rc = require({json.dumps(str(ROUTE_CORE))});
        const idx = {{
          signals: {{
            'skill:x/y/thirdparty-skill': [
              {{kind: 'name', label: 'thirdparty-skill', weight: 1}},
              {{kind: 'tag-inferred', label: 'seo', weight: 0.5}},
            ],
          }},
          extendsBases: {{}},
        }};
        const tokens = rc.tokenize('thirdparty-skill seo tool');
        const match = rc.routeFromIndex(idx, tokens);
        process.stdout.write(JSON.stringify(match && match.skillId));
        """
        self.assertEqual(json.loads(self._node(script)), "skill:x/y/thirdparty-skill")

    def test_two_inferred_alone_does_not_qualify(self) -> None:
        script = f"""
        const rc = require({json.dumps(str(ROUTE_CORE))});
        const idx = {{
          signals: {{
            'skill:only-inferred/x': [
              {{kind: 'tag-inferred', label: 'seo', weight: 0.5}},
              {{kind: 'tag-inferred', label: 'automation', weight: 0.5}},
            ],
          }},
          extendsBases: {{}},
        }};
        const tokens = rc.tokenize('seo automation only');
        const match = rc.routeFromIndex(idx, tokens);
        process.stdout.write(JSON.stringify(match));
        """
        self.assertIsNone(json.loads(self._node(script)))

    def test_declared_signal_set_outranks_inferred_backed_match(self) -> None:
        script = f"""
        const rc = require({json.dumps(str(ROUTE_CORE))});
        const idx = {{
          signals: {{
            'skill:x/y/thirdparty-skill': [
              {{kind: 'name', label: 'thirdparty-skill', weight: 1}},
              {{kind: 'tag-inferred', label: 'seo', weight: 0.5}},
              {{kind: 'tag-inferred', label: 'keyword-research', weight: 0.5}},
              {{kind: 'tag-inferred', label: 'automation', weight: 0.5}},
            ],
            'skill:rhize/declared': [
              {{kind: 'name', label: 'declared', weight: 1}},
              {{kind: 'tag', label: 'seo', weight: 2}},
            ],
          }},
          extendsBases: {{}},
        }};
        const tokens = rc.tokenize(
          'declared seo thirdparty-skill keyword-research automation tool'
        );
        const match = rc.routeFromIndex(idx, tokens);
        process.stdout.write(JSON.stringify({{ id: match.skillId, score: match.score }}));
        """
        result = json.loads(self._node(script))
        self.assertEqual(result["id"], "skill:rhize/declared")
        self.assertEqual(result["score"], 3)


# ---------------------------------------------------------------------------
# 5. skill-router.js / agent-brief-router.js — end-to-end hook rendering
# ---------------------------------------------------------------------------


def _write_indexes(home: Path, doc: dict) -> None:
    context_dir = home / ".claude" / "context-manager"
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "skill-map.indexes.json").write_text(json.dumps(doc))


THIRD_PARTY_SKILL_ID = "skill:acme-marketplace/acme-plugin/widget-builder"
THIRD_PARTY_INDEXES_DOC = {
    "schemaVersion": "1.2.0",
    "disclosure": {},
    "remediation": {},
    "succession": {},
    "router": {
        "extendsBases": {},
        "signals": {
            THIRD_PARTY_SKILL_ID: [
                {"kind": "name", "weight": 1, "label": "widget-builder"},
                {"kind": "tag-inferred", "weight": 0.5, "label": "automation"},
            ]
        },
    },
}


class RouterHookInferredRenderingTests(unittest.TestCase):
    def test_skill_router_renders_three_segment_id_with_inferred_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_indexes(home, THIRD_PARTY_INDEXES_DOC)
            result = subprocess.run(
                ["node", str(SKILL_ROUTER)],
                input=json.dumps({"prompt": "help me with widget-builder automation tooling"}),
                env={**os.environ, "HOME": str(home)},
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            stdout = result.stdout.strip()
            self.assertTrue(stdout, "expected a suggestion")
            parsed = json.loads(stdout.splitlines()[0])
            ctx = parsed["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(
                ctx,
                "Consider the acme-plugin:widget-builder skill "
                "(matches widget-builder, automation (inferred))",
            )

    def test_agent_brief_router_names_three_segment_id_via_invoke_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_indexes(home, THIRD_PARTY_INDEXES_DOC)
            log_path = home / "suggestion-log.jsonl"
            brief = (
                "Invoke acme-plugin:widget-builder first, then do the rest of the task "
                "without naming any other skill."
            )
            result = subprocess.run(
                ["node", str(AGENT_BRIEF_ROUTER)],
                input=json.dumps(
                    {"tool_input": {"prompt": brief, "subagent_type": "general-purpose"}}
                ),
                env={**os.environ, "HOME": str(home), "RHIZE_SUGGESTION_LOG": str(log_path)},
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(log_path.exists())
            entry = json.loads(log_path.read_text().strip().splitlines()[0])
            self.assertIn(THIRD_PARTY_SKILL_ID, entry["namedSkills"])


if __name__ == "__main__":
    unittest.main()
