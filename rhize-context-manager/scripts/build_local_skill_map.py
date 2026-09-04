#!/usr/bin/env python3
"""build_local_skill_map.py — machine-local overlay + resolved skill map.

Phase 3 ("local overlay") of the skill-map-graph-substrate plan
(.claude/plans/skill-map-graph-substrate.md). Joins three machine-local,
optional inputs against the committed static artifact
(generated/skill-map.static.json) and writes two files under
~/.claude/context-manager/ (gitignored, never committed):

  - skill-map.local.json     — overlay facts only: enabled-plugin set, stack
                                config fingerprint, usage-cooccurs edges.
  - skill-map.resolved.json  — the merged consumer view (static + overlay)
                                that skill-router.js and /start read.

Inputs (each optional; a missing input degrades that piece of the overlay
and is noted in local.json's `sourceNotes` — it never fails the build):

  1. Enabled-plugin set — `~/.claude/plugins/installed_plugins.json`
     (version 2 shape: {"plugins": {"<name>@<marketplace>": [{"scope",
     "projectPath", ...}]}}). A plugin from this repo's own
     .claude-plugin/marketplace.json is "enabled" if it has an install
     entry with scope "user" (applies everywhere) or a "project" entry
     whose projectPath resolves to this repo. If the file is missing or
     unreadable, ALL of this repo's plugins are treated as enabled and the
     degradation is recorded in `sourceNotes.enabledPlugins`.

  2. Stack config — `~/.claude/rhize-context-manager/stack.config.json`
     (schemaVersion 2, written by /context-setup). We only need a cheap
     drift signal here, not the full layer inventory, so we record a
     sha256 fingerprint of the file plus this repo's `repoOverrides` entry
     (keyed by this repo's directory basename) if present.

  3. Usage co-occurrence — the standalone rhize-skill-monitor tool's
     data/skill-cooccurrence.json (Rhize-Media/rhize-skill-monitor, not
     bundled with this plugin; see monitor.py's build_cooccurrence()).
     skill_monitor_data_dir() below resolves that tool's data directory the
     same way its own paths.py does, without importing across the plugin
     boundary. Counts-only: {windowDays, totalSessions, pairs: [{a, b, sessions}],
     totals: {skill: sessions}}. Pair endpoints are "<plugin>:<skill>"
     (monitor's raw Skill-tool name) or a bare name for user-level skills
     outside any plugin. Only pairs where BOTH endpoints resolve to a
     `skill:<plugin>/<name>` node already present in the static artifact
     become `usage-cooccurs` edges — monitor observes skill usage across
     ALL of this machine's repos, most of which aren't in this map.

  4. Third-party ecosystem inventory — every plugin installed on this
     machine (per `~/.claude/plugins/installed_plugins.json`) whose
     marketplace is NOT this repo's own, and which is "enabled" per the
     merge of `~/.claude/settings.json`'s `enabledPlugins` map with this
     repo's `.claude/settings.local.json` override (local wins on
     conflict — the same precedence Claude Code itself uses). For each
     such plugin we emit a `plugin` node (see id convention below), one
     `skill` node per `skills/*/SKILL.md` under its cached install path,
     and one `command` node per `commands/*.md`, all tagged
     `"origin": "third-party"`. `contains` edges connect the plugin to
     each child, attributed `source: "marketplace"` (reusing the existing
     enum value — the relationship was discovered the same way a rhize
     plugin's contains edges are, by reading a plugin's on-disk layout;
     schemas/skill-map.schema.json's provenanceSource enum has no
     third-party-specific value and this task's scope excludes editing
     the schema). No topic/stack-tag edges are emitted — third-party
     skills don't carry `metadata.rhize.*` frontmatter.

     Id convention (collision-proof against this repo's bare
     `plugin:<name>` / `skill:<plugin>/<name>` ids, which never contain a
     second path segment before the leaf): `plugin:<marketplace>/<name>`,
     `skill:<marketplace>/<plugin>/<skill-dir>`,
     `command:<marketplace>/<plugin>/<command-stem>`.

     Descriptions are truncated to ~200 chars (see
     `DESCRIPTION_TRUNCATE_LIMIT`) — routing/overlap needs the gist, not
     the full trigger text, and some of these plugins (ecc alone ships
     280+ skills) would otherwise bloat the overlay. `path` values point
     at the machine-local cache (e.g.
     `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/...`),
     home-relative rather than repo-relative, since these files live
     outside this repo entirely — this whole inventory is machine-local
     by construction (see docs/skill-map.md).

     A missing/unreadable installed_plugins.json degrades to zero
     third-party nodes (same as input 1). A plugin whose cached install
     path is missing, or a SKILL.md/command file that can't be read, is
     skipped and counted (`sourceNotes.thirdParty` reports the counts) —
     never a build failure.

  5. Router-signal tag inference — `catalog/tags.json` (the closed
     topic/stack/condition tag vocabulary; see docs/skill-map.md). Third-
     party skills (input 4) get no topic-tag/stack-tag EDGES (their
     frontmatter isn't ours to edit), but the router INDEX can still use
     half-weight, best-effort SIGNALS: for each third-party skill node,
     infer up to 3 topic/stack tag slugs (never condition — see
     infer_tags_for_skill()) from the skill's name + description, and
     write them into
     ~/.claude/context-manager/skill-map.indexes.resolved.json's
     `router.signals[skillId]` as `{kind: "tag-inferred", weight: 0.5,
     label: <slug>}` entries (see build_resolved_indexes()). Declared
     (rhize) skill signals are copied through unchanged. A missing or
     malformed catalog degrades to zero inferred signals
     (`sourceNotes.tagsCatalog` records why), never a build failure.
     `--report-inferred` prints the per-skill inferred-tag table alone
     (no files written) for a precision review before trusting the
     injected signals.

Resolved-map construction:
  resolved.nodes = static.nodes + third-party nodes (input 4).
  resolved.edges = static.edges + usage-cooccurs edges (input 3) +
                   third-party contains edges (input 4).
  No static node is mutated (e.g. no "enabled" annotation) — this is what
  makes the "missing input degrades cleanly" contract exact: if inputs
  3 and 4 are both absent, resolved.json is byte-for-byte equivalent
  (content-wise) to the static artifact.

Determinism: given identical inputs, two runs produce identical output.
Edges are sorted the same way build_skill_map.py's Graph.to_document()
sorts them; JSON is dumped with sort_keys=True and a trailing newline.

Usage:
  python3 rhize-context-manager/scripts/build_local_skill_map.py
  python3 rhize-context-manager/scripts/build_local_skill_map.py --out-dir <dir>
      # override ~/.claude/context-manager (used by tests with a fake HOME)
  python3 rhize-context-manager/scripts/build_local_skill_map.py --static <path>
      # override generated/skill-map.static.json (used by tests with a fixture)
  python3 rhize-context-manager/scripts/build_local_skill_map.py --cooccurrence <path>
      # override the skill-monitor data dir's skill-cooccurrence.json
      # (see skill_monitor_data_dir(): RHIZE_SKILL_MONITOR_HOME, else the
      # standalone checkout's data/, else ~/.rhize/skill-monitor/data)
  python3 rhize-context-manager/scripts/build_local_skill_map.py --installed-plugins <path>
  python3 rhize-context-manager/scripts/build_local_skill_map.py --stack-config <path>
  python3 rhize-context-manager/scripts/build_local_skill_map.py --tags-catalog <path>
      # override catalog/tags.json (used by tests with a fixture catalog)
  python3 rhize-context-manager/scripts/build_local_skill_map.py --report-inferred
      # print a per-skill inferred-tag table for every third-party skill and
      # exit — no files are written

SHIPS WITH THE PLUGIN (moved from repo-root `scripts/` 2026-09-02, R3 task 8 of the
portability-readiness plan): this file now lives at
`rhize-context-manager/scripts/build_local_skill_map.py`, one directory level deeper
than the repo root instead of directly under it. `_find_source_root()` below resolves
the repo/marketplace-clone root this script needs (for `generated/`, `rhize-ops/`,
`.claude-plugin/`, and `scripts/build_skill_map.py`'s `split_frontmatter()`) — see its
docstring for why a plain two-parents-up guess is not enough once an installed plugin's
isolated per-version cache copy is in play. A two-line compatibility shim remains at
the old `scripts/build_local_skill_map.py` path.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _find_source_root() -> Path:
    """Locate the repo/marketplace-clone root this script needs as a sibling
    of its own directory: `generated/`, `rhize-ops/`, `.claude-plugin/`, and
    `scripts/build_skill_map.py` (for `split_frontmatter()`, reused rather
    than reimplemented — see the import below).

    This script moved from repo-root `scripts/` into
    `rhize-context-manager/scripts/` (R3 task 8, portability-readiness plan),
    so it now sits one directory level deeper. Two parents up still finds the
    root for a dev checkout AND a full marketplace clone under
    `~/.claude/plugins/marketplaces/<name>/` — both are the same repo shape.
    It does NOT work from an installed plugin's isolated per-version cache
    copy (`~/.claude/plugins/cache/<marketplace>/rhize-context-manager/
    <version>/`), which Claude Code populates flat, with none of this
    plugin's siblings — so that case falls back to scanning
    `~/.claude/plugins/marketplaces/*/` for a clone that contains this same
    script (i.e. the actual marketplace clone, not the cache).

    Raises FileNotFoundError if neither resolves. Unlike this script's other
    inputs (installed_plugins.json, stack.config.json, ...), the source root
    is not an optional input the build degrades without — it is where the
    committed static artifact and build_skill_map.py live.
    """
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / ".claude-plugin" / "marketplace.json").is_file():
        return candidate

    marketplaces_dir = Path.home() / ".claude" / "plugins" / "marketplaces"
    if marketplaces_dir.is_dir():
        for marketplace_dir in sorted(marketplaces_dir.iterdir()):
            if (
                marketplace_dir
                / "rhize-context-manager"
                / "scripts"
                / "build_local_skill_map.py"
            ).is_file():
                return marketplace_dir

    raise FileNotFoundError(
        "could not locate the rhize-plugins repo/clone root (looked next to this "
        f"script at {candidate} and under {marketplaces_dir}) — pass --static, "
        "--static-indexes, and --cooccurrence explicitly if running from an "
        "isolated plugin cache install"
    )


def skill_monitor_data_dir() -> Path:
    """Resolve the standalone rhize-skill-monitor tool's data directory on
    this machine (Rhize-Media/rhize-skill-monitor — not bundled with this
    plugin; reached only by this discovered-path resolver, never a
    cross-plugin import). Mirrors that tool's own paths.py precedence:
      1. RHIZE_SKILL_MONITOR_HOME set -> <home>/data
      2. else RHIZE_SKILL_MONITOR_ROOT, or the default checkout
         (~/dev-local/RHIZE/rhize-skill-monitor); if its data/ is a
         directory -> that data/
      3. else ~/.rhize/skill-monitor/data (fresh-install default)
    """
    home_override = os.environ.get("RHIZE_SKILL_MONITOR_HOME", "").strip()
    if home_override:
        return Path(home_override).expanduser() / "data"
    root_override = os.environ.get("RHIZE_SKILL_MONITOR_ROOT", "").strip()
    root = (
        Path(root_override).expanduser()
        if root_override
        else Path.home() / "dev-local" / "RHIZE" / "rhize-skill-monitor"
    )
    checkout_data = root / "data"
    if checkout_data.is_dir():
        return checkout_data
    return Path.home() / ".rhize" / "skill-monitor" / "data"


def _default_cooccurrence_path() -> Path:
    """Where skill-monitor's skill-cooccurrence.json lives on this machine.
    See skill_monitor_data_dir() for the precedence."""
    return skill_monitor_data_dir() / "skill-cooccurrence.json"


REPO_ROOT = _find_source_root()
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
DEFAULT_STATIC_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
DEFAULT_STATIC_INDEXES_PATH = REPO_ROOT / "generated" / "skill-map.indexes.json"

# build_skill_map.py already implements the exact frontmatter-splitting logic
# a third-party SKILL.md/command .md needs (name/description parsing). Reuse
# it rather than writing a third parser — see scripts/build_skill_map.py's
# split_frontmatter(). It stays at the repo-root scripts/ dir (not moved), so
# import it from REPO_ROOT/scripts, not this file's own directory.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from build_skill_map import split_frontmatter  # noqa: E402

# Descriptions in the third-party overlay are truncated to this many chars —
# routing/overlap needs the gist, not the full trigger text, and some
# installed plugins (e.g. ecc) ship 200+ skills.
DESCRIPTION_TRUNCATE_LIMIT = 200

# Third-party node ids may embed a marketplace/plugin/skill/command name we
# don't control. Sanitize any character outside the schema's nodeId pattern
# ([A-Za-z0-9_.\-/]) to '-' so emission can never fail schema validation on
# an unexpected name.
_ID_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_.\-]")


def default_installed_plugins_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def default_stack_config_path() -> Path:
    return Path.home() / ".claude" / "rhize-context-manager" / "stack.config.json"


def default_global_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def default_local_settings_path() -> Path:
    return REPO_ROOT / ".claude" / "settings.local.json"


def default_tags_catalog_path() -> Path:
    return REPO_ROOT / "catalog" / "tags.json"


def default_out_dir() -> Path:
    return Path.home() / ".claude" / "context-manager"


def _load_json(path: Path) -> tuple[dict | None, str | None]:
    """Return (data, error). error is None on success."""
    if not path.is_file():
        return None, f"{path} not found"
    try:
        return json.loads(path.read_text()), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{path} unreadable: {exc}"


def load_tags_catalog(tags_catalog_path: Path) -> tuple[list[dict], str]:
    """Return (entries, note) for catalog/tags.json's raw entry list (each
    `{slug, kind, gloss}`, `condition` entries also carry `patterns` — see
    docs/skill-map.md's "Tag vocabulary"). Degrades to ([], note) on any
    missing/unreadable/malshaped catalog — inferred router-signal tagging is
    a best-effort precision feature, never a build blocker."""
    data, err = _load_json(tags_catalog_path)
    if err:
        return [], f"degraded: {err} — no inferred tag signals added"
    if not isinstance(data, list):
        return [], f"degraded: {tags_catalog_path} is not a JSON array — no inferred tag signals added"
    return [entry for entry in data if isinstance(entry, dict)], f"read from {tags_catalog_path}"


def resolve_enabled_plugins(
    marketplace_name: str,
    repo_plugin_names: list[str],
    installed_plugins_path: Path,
) -> tuple[set[str], str]:
    """Return (enabled_set, note). Degrades to "all enabled" on any failure."""
    data, err = _load_json(installed_plugins_path)
    if err:
        return set(repo_plugin_names), f"degraded: {err} — treating all repo plugins as enabled"

    plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
    enabled: set[str] = set()
    for name in repo_plugin_names:
        pid = f"{name}@{marketplace_name}"
        installs = plugins.get(pid)
        if not isinstance(installs, list):
            continue
        for install in installs:
            scope = install.get("scope")
            if scope == "user":
                enabled.add(name)
                break
            if scope == "project":
                project_path = install.get("projectPath")
                if project_path and Path(project_path).resolve() == REPO_ROOT:
                    enabled.add(name)
                    break
    return enabled, f"read from {installed_plugins_path}"


def resolve_stack_fingerprint(stack_config_path: Path) -> tuple[dict | None, str]:
    data, err = _load_json(stack_config_path)
    if err:
        return None, f"degraded: {err} — no stack overlay applied"
    raw = stack_config_path.read_bytes()
    fingerprint = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "repoOverrides": (data.get("repoOverrides", {}) or {}).get(REPO_ROOT.name),
    }
    return fingerprint, f"read from {stack_config_path}"


# monitor.py's co-occurrence snapshot uses windowDays == 0 to mean "all-time"
# (`--days 0`), but the schema's usageWeight.windowDays has a minimum of 1
# (it measures the size of a rolling window). This sentinel represents
# "unbounded" without violating the schema; scheduled runs use a bounded
# window in practice (see the standalone rhize-skill-monitor tool's
# weekly-skill-audit task).
ALL_TIME_WINDOW_SENTINEL = 36500  # ~100 years


def _skill_id_from_monitor_name(name: str) -> str:
    """Convert a monitor skill name ("<plugin>:<skill>" or a bare user-level
    name) into a skill-map node id ("skill:<plugin>/<skill>"). Bare names
    (no ':') don't belong to any plugin in this repo and never match a
    static node — they're filtered out by the caller, not here."""
    plugin, _, skill = name.partition(":")
    return f"skill:{plugin}/{skill}" if skill else f"skill:{plugin}"


def build_usage_edges(
    cooccurrence_path: Path,
    static_skill_ids: set[str],
) -> tuple[list[dict], dict | None, str]:
    """Return (edges, snapshot_summary, note). Degrades to (no edges) on any
    failure or when a pair's endpoints don't resolve to nodes in the static
    artifact (monitor observes usage across every repo on the machine, not
    just this one)."""
    data, err = _load_json(cooccurrence_path)
    if err:
        return [], None, f"degraded: {err} — no usage-cooccurs edges added"

    window_days = data.get("windowDays") or 0
    total_sessions = data.get("totalSessions") or 0
    totals = data.get("totals") or {}
    pairs = data.get("pairs") or []

    edges: list[dict] = []
    for pair in pairs:
        a_name, b_name = pair.get("a"), pair.get("b")
        sessions_ab = pair.get("sessions") or 0
        if not a_name or not b_name or sessions_ab <= 0:
            continue
        a_id = _skill_id_from_monitor_name(a_name)
        b_id = _skill_id_from_monitor_name(b_name)
        if a_id not in static_skill_ids or b_id not in static_skill_ids:
            continue

        sessions_a = totals.get(a_name) or 0
        sessions_b = totals.get(b_name) or 0
        denom = sessions_a + sessions_b - sessions_ab
        jaccard = round(sessions_ab / denom, 4) if denom > 0 else 0.0
        lift = (
            round((sessions_ab * total_sessions) / (sessions_a * sessions_b), 4)
            if sessions_a > 0 and sessions_b > 0 and total_sessions > 0
            else 0.0
        )

        from_id, to_id = sorted((a_id, b_id))
        edges.append(
            {
                "from": from_id,
                "to": to_id,
                "type": "usage-cooccurs",
                "source": "monitor",
                "usageWeight": {
                    "sessions": sessions_ab,
                    "jaccard": jaccard,
                    "lift": lift,
                    "windowDays": window_days if window_days > 0 else ALL_TIME_WINDOW_SENTINEL,
                },
            }
        )

    edges.sort(key=lambda e: (e["from"], e["to"]))
    summary = {
        "windowDays": window_days,
        "totalSessions": total_sessions,
        "pairsConsidered": len(pairs),
        "edgesResolved": len(edges),
    }
    return edges, summary, f"read from {cooccurrence_path}"


def build_follows_edges(
    cooccurrence_path: Path,
    static_skill_ids: set[str],
) -> tuple[list[dict], dict | None, str]:
    """Return (edges, summary, note) for mined `follows` edges (skill-map
    relationships v2, decision 1). Reads the same skill-cooccurrence.json
    snapshot as build_usage_edges(), but its `orderedPairs` key (directional,
    already thresholded at >=2 distinct sessions by monitor.py). Unlike
    usage-cooccurs, `follows` is directional — `from`/`to` are NOT sorted,
    they preserve the mined A-then-B order. Local-overlay only: never
    written into the committed static artifact."""
    data, err = _load_json(cooccurrence_path)
    if err:
        return [], None, f"degraded: {err} — no follows edges added"

    window_days = data.get("windowDays") or 0
    ordered_pairs = data.get("orderedPairs") or []

    edges: list[dict] = []
    for pair in ordered_pairs:
        a_name, b_name = pair.get("a"), pair.get("b")
        sessions_ab = pair.get("sessions") or 0
        if not a_name or not b_name or sessions_ab <= 0:
            continue
        a_id = _skill_id_from_monitor_name(a_name)
        b_id = _skill_id_from_monitor_name(b_name)
        if a_id not in static_skill_ids or b_id not in static_skill_ids:
            continue
        edges.append(
            {
                "from": a_id,
                "to": b_id,
                "type": "follows",
                "source": "monitor",
                "followWeight": {
                    "sessions": sessions_ab,
                    "windowDays": window_days if window_days > 0 else ALL_TIME_WINDOW_SENTINEL,
                },
            }
        )

    edges.sort(key=lambda e: (e["from"], e["to"]))
    summary = {
        "windowDays": window_days,
        "pairsConsidered": len(ordered_pairs),
        "edgesResolved": len(edges),
    }
    return edges, summary, f"read from {cooccurrence_path}"


def _id_safe(value: str) -> str:
    return _ID_UNSAFE_RE.sub("-", value)


def _truncate(text: str, limit: int = DESCRIPTION_TRUNCATE_LIMIT) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _home_relative(path: Path) -> str:
    home = str(Path.home())
    raw = str(path)
    if raw.startswith(home):
        return "~" + raw[len(home):]
    return raw


_WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")


@functools.lru_cache(maxsize=None)
def _words_of(text: str) -> tuple[str, ...]:
    """Tokenize the same way hooks/lib/route-core.js's wordsOf()/tokenize()
    do: lowercase, split on runs of non-alphanumeric characters, drop
    empties. Kept in lockstep with that JS function so a slug/label match
    here means the same thing a router match at runtime would find. Cached:
    every catalog slug is re-tokenized once per third-party skill otherwise."""
    return tuple(w for w in _WORD_SPLIT_RE.split((text or "").lower()) if w)


def infer_tags_for_skill(
    name: str, description: str, tags_catalog: list[dict]
) -> list[str]:
    """Infer up to 3 topic/stack tag slugs for a third-party skill from its
    name + description. A catalog entry matches when every word of its
    slug (hyphen-separated) — or, if present, every word of any one of its
    optional `aliases` — appears among the tokenized name+description,
    mirroring route-core.js's routeFromIndex() "every word of the label is
    in the prompt tokens" rule. `condition` entries are never inferred —
    they describe a runtime failure state a skill remediates, not a
    skill's subject matter, and this feeds only the router's topic/stack
    signal set.

    Selection prefers multi-word slugs (a more specific match) over
    single-word ones, then alphabetical, capped at 3; the returned list is
    itself sorted alphabetically so output is deterministic regardless of
    catalog order or how many candidates matched."""
    prompt_words = set(_words_of(f"{name} {description}"))

    def _phrase_matches(phrase: str) -> bool:
        words = _words_of(phrase)
        return bool(words) and all(w in prompt_words for w in words)

    candidates: list[tuple[int, str]] = []
    for entry in tags_catalog:
        if entry.get("kind") not in ("topic", "stack"):
            continue
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        aliases = [a for a in (entry.get("aliases") or []) if isinstance(a, str)]
        if any(_phrase_matches(phrase) for phrase in (slug, *aliases)):
            candidates.append((len(_words_of(slug)), slug))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return sorted(slug for _, slug in candidates[:3])


def _pick_install_entry(installs: list) -> dict | None:
    """Pick one install entry to source a plugin's on-disk path from. Most
    pids have a single (sometimes duplicated) entry. When distinct
    installPaths exist (multiple versions installed across projects), pick
    deterministically by (version, installPath) — highest wins."""
    valid = [i for i in installs if isinstance(i, dict) and i.get("installPath")]
    if not valid:
        return None
    unique_paths = {i["installPath"] for i in valid}
    if len(unique_paths) == 1:
        return valid[0]
    return max(valid, key=lambda i: (str(i.get("version", "")), i["installPath"]))


def resolve_third_party_enabled_map(
    global_settings_path: Path, local_settings_path: Path
) -> tuple[dict[str, bool], str]:
    """Merge ~/.claude/settings.json's enabledPlugins with this repo's
    .claude/settings.local.json override (local wins) — the same precedence
    Claude Code itself applies. Returns (merged_map, note)."""
    global_data, global_err = _load_json(global_settings_path)
    local_data, local_err = _load_json(local_settings_path)
    merged: dict[str, bool] = {}
    if isinstance(global_data, dict):
        merged.update(global_data.get("enabledPlugins", {}) or {})
    if isinstance(local_data, dict):
        merged.update(local_data.get("enabledPlugins", {}) or {})
    if global_err and local_err:
        return merged, f"degraded: {global_err}; {local_err} — no plugins treated as enabled"
    notes = [n for n in (global_err, local_err) if n]
    if notes:
        return merged, f"partially degraded: {'; '.join(notes)}"
    return merged, f"read from {global_settings_path} + {local_settings_path}"


def collect_third_party_ecosystem(
    installed_plugins_data: dict | None,
    marketplace_name: str,
    global_settings_path: Path,
    local_settings_path: Path,
) -> tuple[list[dict], list[dict], dict, str]:
    """Scan every installed+enabled plugin whose marketplace is NOT this
    repo's own and emit plugin/skill/command nodes + contains edges for the
    local overlay. Returns (nodes, edges, summary, note). Degrades to empty
    output (never raises) when installed_plugins.json is missing/unreadable,
    a plugin's cached install path doesn't exist, or a source file can't be
    read — those cases are counted in `summary`, not failed on."""
    empty_summary = {
        "plugins": 0,
        "skills": 0,
        "commands": 0,
        "skippedPlugins": 0,
        "skippedEntries": 0,
    }
    if not isinstance(installed_plugins_data, dict):
        return [], [], empty_summary, "degraded: installed_plugins.json unavailable — no third-party inventory"

    enabled_map, enabled_note = resolve_third_party_enabled_map(
        global_settings_path, local_settings_path
    )
    plugins_map = installed_plugins_data.get("plugins", {})
    if not isinstance(plugins_map, dict):
        plugins_map = {}

    nodes: list[dict] = []
    edges: list[dict] = []
    plugin_count = skill_count = command_count = 0
    skipped_plugins = skipped_entries = 0

    for pid in sorted(plugins_map.keys()):
        if "@" not in pid:
            continue
        name, marketplace = pid.rsplit("@", 1)
        if marketplace == marketplace_name:
            continue  # this repo's own plugin — already a static node
        if enabled_map.get(pid) is not True:
            continue  # not currently enabled anywhere on this machine

        installs = plugins_map[pid]
        entry = _pick_install_entry(installs if isinstance(installs, list) else [])
        if entry is None:
            skipped_plugins += 1
            continue
        install_path = Path(entry["installPath"])
        if not install_path.is_dir():
            skipped_plugins += 1
            continue

        safe_marketplace, safe_name = _id_safe(marketplace), _id_safe(name)
        plugin_id = f"plugin:{safe_marketplace}/{safe_name}"

        plugin_description = ""
        manifest_data, manifest_err = _load_json(install_path / ".claude-plugin" / "plugin.json")
        if not manifest_err and isinstance(manifest_data, dict):
            plugin_description = _truncate(str(manifest_data.get("description", "")))

        nodes.append(
            {
                "id": plugin_id,
                "kind": "plugin",
                "name": name,
                "path": _home_relative(install_path),
                "description": plugin_description,
                "origin": "third-party",
            }
        )
        plugin_count += 1

        skills_dir = install_path / "skills"
        if skills_dir.is_dir():
            for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue
                try:
                    raw = skill_md.read_bytes()
                    text = raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    skipped_entries += 1
                    continue
                frontmatter, _ = split_frontmatter(text)
                description = frontmatter.get("description", "")
                if not isinstance(description, str):
                    description = str(description)
                skill_id = f"skill:{safe_marketplace}/{safe_name}/{_id_safe(skill_dir.name)}"
                nodes.append(
                    {
                        "id": skill_id,
                        "kind": "skill",
                        "name": skill_dir.name,
                        "path": _home_relative(skill_md),
                        "description": _truncate(description),
                        "contentHash": hashlib.sha256(raw).hexdigest(),
                        "origin": "third-party",
                    }
                )
                edges.append(
                    {"from": plugin_id, "to": skill_id, "type": "contains", "source": "marketplace"}
                )
                skill_count += 1

        commands_dir = install_path / "commands"
        if commands_dir.is_dir():
            for cmd_md in sorted(commands_dir.glob("*.md")):
                try:
                    text = cmd_md.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    skipped_entries += 1
                    continue
                frontmatter, _ = split_frontmatter(text)
                description = frontmatter.get("description", "")
                if not isinstance(description, str):
                    description = str(description)
                command_id = f"command:{safe_marketplace}/{safe_name}/{_id_safe(cmd_md.stem)}"
                nodes.append(
                    {
                        "id": command_id,
                        "kind": "command",
                        "name": cmd_md.stem,
                        "path": _home_relative(cmd_md),
                        "description": _truncate(description),
                        "origin": "third-party",
                    }
                )
                edges.append(
                    {"from": plugin_id, "to": command_id, "type": "contains", "source": "marketplace"}
                )
                command_count += 1

    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: (e["from"], e["to"], e["type"], e["source"]))

    summary = {
        "plugins": plugin_count,
        "skills": skill_count,
        "commands": command_count,
        "skippedPlugins": skipped_plugins,
        "skippedEntries": skipped_entries,
    }
    return nodes, edges, summary, f"enabled set: {enabled_note}"


def build(
    static_path: Path,
    installed_plugins_path: Path,
    stack_config_path: Path,
    cooccurrence_path: Path,
    global_settings_path: Path | None = None,
    local_settings_path: Path | None = None,
    tags_catalog_path: Path | None = None,
) -> tuple[dict, dict]:
    """Return (local_doc, resolved_doc)."""
    static_doc = json.loads(static_path.read_text())
    marketplace = json.loads(MARKETPLACE_PATH.read_text())
    marketplace_name = marketplace["name"]
    repo_plugin_names = sorted(p["name"] for p in marketplace["plugins"])

    enabled_plugins, enabled_note = resolve_enabled_plugins(
        marketplace_name, repo_plugin_names, installed_plugins_path
    )
    stack_fingerprint, stack_note = resolve_stack_fingerprint(stack_config_path)

    static_skill_ids = {n["id"] for n in static_doc["nodes"] if n["kind"] == "skill"}
    usage_edges, cooc_summary, cooc_note = build_usage_edges(
        cooccurrence_path, static_skill_ids
    )
    follows_edges, follows_summary, follows_note = build_follows_edges(
        cooccurrence_path, static_skill_ids
    )

    installed_plugins_data, _ = _load_json(installed_plugins_path)
    third_party_nodes, third_party_edges, third_party_summary, third_party_note = (
        collect_third_party_ecosystem(
            installed_plugins_data,
            marketplace_name,
            global_settings_path or default_global_settings_path(),
            local_settings_path or default_local_settings_path(),
        )
    )

    # Only the source note is needed here — the loaded catalog itself is
    # reloaded (main()'s report-inferred/resolved-indexes step needs it too;
    # build()'s job is the local/resolved MAP docs, not the resolved
    # INDEXES doc that actually consumes the catalog contents).
    _tags_catalog, tags_catalog_note = load_tags_catalog(
        tags_catalog_path or default_tags_catalog_path()
    )

    generated_at = datetime.now(timezone.utc).isoformat()

    local_doc = {
        "generatedAt": generated_at,
        "enabledPlugins": sorted(enabled_plugins),
        "stack": stack_fingerprint,
        "usageCooccursEdges": usage_edges,
        "cooccurrenceSummary": cooc_summary,
        "followsEdges": follows_edges,
        "followsSummary": follows_summary,
        "thirdParty": {
            "nodes": third_party_nodes,
            "edges": third_party_edges,
            "summary": third_party_summary,
        },
        "sourceNotes": {
            "enabledPlugins": enabled_note,
            "stack": stack_note,
            "cooccurrence": cooc_note,
            "follows": follows_note,
            "thirdParty": third_party_note,
            "tagsCatalog": tags_catalog_note,
        },
    }

    resolved_doc = {
        "schemaVersion": static_doc["schemaVersion"],
        "nodes": static_doc["nodes"] + third_party_nodes,
        "edges": static_doc["edges"] + usage_edges + follows_edges + third_party_edges,
    }

    return local_doc, resolved_doc


# The resolved indexes' own schemaVersion, tracked independently of the
# static indexes' (scripts/build_skill_map.py's SCHEMA_VERSION, currently
# "1.1.0") because this file adds resolved-only, additive features that
# never touch generated/skill-map.indexes.json itself. Bumped to "1.2.0" for
# the tag-inferred router signal kind (see infer_tags_for_skill()).
RESOLVED_INDEXES_SCHEMA_VERSION = "1.2.0"


def build_resolved_indexes(
    static_indexes: dict,
    follows_edges: list[dict],
    third_party_nodes: list[dict] | None = None,
    tags_catalog: list[dict] | None = None,
) -> dict:
    """Merge mined `follows` edges into the succession section, and inferred
    `tag-inferred` router signals for third-party skills into the router
    section, of the static indexes artifact — producing the resolved
    indexes layer consumed at
    ~/.claude/context-manager/skill-map.indexes.resolved.json.
    `disclosure`/`remediation` are copied through unchanged — third-party
    skills carry no topic-tag/stack-tag/remediates edges (see
    docs/skill-map.md's third-party ecosystem inventory note), so there is
    nothing for those sections to merge in from the local overlay.

    Inferred tag signals: for each third-party skill node (`third_party_nodes`,
    e.g. `local_doc["thirdParty"]["nodes"]`), infer_tags_for_skill() picks up
    to 3 topic/stack tags from `tags_catalog`; each becomes a
    `{kind: "tag-inferred", weight: 0.5, label: <slug>}` entry in
    `router.signals[skillId]`. Declared (rhize) skills' existing signal
    entries are copied but never mutated. A third-party skill getting its
    FIRST signal entry here also gets a `name` entry added alongside the
    inferred ones — mirroring build_skill_map.py's build_router_index(),
    which gives every skill a name signal — because an entry made up
    entirely of tag-inferred signals could never qualify a match on its own
    (route-core.js's routeFromIndex() requires >=2 matched signals, at least
    one of which isn't tag-inferred). A skill with zero inferred tags gets
    no signals entry at all."""
    succession = {
        node_id: {"precedes": list(entry.get("precedes", [])), "follows": list(entry.get("follows", []))}
        for node_id, entry in (static_indexes.get("succession") or {}).items()
    }
    for edge in follows_edges:
        from_id, to_id = edge["from"], edge["to"]
        succession.setdefault(from_id, {"precedes": [], "follows": []})
        succession.setdefault(to_id, {"precedes": [], "follows": []})
        succession[to_id]["follows"].append(from_id)
    for entry in succession.values():
        entry["precedes"] = sorted(set(entry["precedes"]))
        entry["follows"] = sorted(set(entry["follows"]))

    router = dict(static_indexes.get("router") or {})
    # Shallow per-skill list copies: signal dicts are appended to and re-sorted, never mutated.
    signals = {
        skill_id: list(entries)
        for skill_id, entries in (router.get("signals") or {}).items()
    }
    for node in third_party_nodes or []:
        if node.get("kind") != "skill":
            continue
        skill_id = node.get("id")
        if not isinstance(skill_id, str):
            continue
        inferred = infer_tags_for_skill(
            str(node.get("name") or ""),
            str(node.get("description") or ""),
            tags_catalog or [],
        )
        if not inferred:
            continue
        entries = signals.get(skill_id)
        if entries is None:
            entries = [{"kind": "name", "weight": 1, "label": str(node.get("name") or "")}]
            signals[skill_id] = entries
        entries.extend({"kind": "tag-inferred", "weight": 0.5, "label": slug} for slug in inferred)
        entries.sort(key=lambda s: (s["kind"], s["label"]))
    router["signals"] = signals

    return {
        "schemaVersion": RESOLVED_INDEXES_SCHEMA_VERSION,
        "router": router,
        "disclosure": static_indexes.get("disclosure", {}),
        "remediation": static_indexes.get("remediation", {}),
        "succession": succession,
    }


def print_inferred_report(third_party_nodes: list[dict], tags_catalog: list[dict]) -> None:
    """`--report-inferred`: print a per-skill table of inferred tags without
    writing anything, so the injection in build_resolved_indexes() can be
    reviewed for precision before it's trusted."""
    skill_nodes = [n for n in third_party_nodes if n.get("kind") == "skill"]
    rows = []
    for node in skill_nodes:
        inferred = infer_tags_for_skill(
            str(node.get("name") or ""), str(node.get("description") or ""), tags_catalog
        )
        if inferred:
            rows.append((node["id"], inferred))

    print(f"Inferred tags: {len(rows)} of {len(skill_nodes)} third-party skills")
    for skill_id, tags in rows:
        print(f"  {skill_id} -> {', '.join(tags)}")


def dump(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--static", default=str(DEFAULT_STATIC_PATH))
    ap.add_argument("--static-indexes", default=str(DEFAULT_STATIC_INDEXES_PATH),
                     help="default: generated/skill-map.indexes.json — merged with mined "
                          "follows edges into skill-map.indexes.resolved.json. Missing file "
                          "degrades to no resolved-indexes output (never a build failure).")
    ap.add_argument("--installed-plugins", default=None,
                     help="default: ~/.claude/plugins/installed_plugins.json")
    ap.add_argument("--stack-config", default=None,
                     help="default: ~/.claude/rhize-context-manager/stack.config.json")
    ap.add_argument(
        "--cooccurrence",
        default=None,
        help="default: skill-monitor data dir's skill-cooccurrence.json "
             "(see skill_monitor_data_dir())",
    )
    ap.add_argument("--global-settings", default=None,
                     help="default: ~/.claude/settings.json")
    ap.add_argument("--local-settings", default=None,
                     help="default: <repo>/.claude/settings.local.json")
    ap.add_argument("--tags-catalog", default=None,
                     help="default: catalog/tags.json — the topic/stack vocabulary used to "
                          "infer third-party router signals (see infer_tags_for_skill())")
    ap.add_argument("--report-inferred", action="store_true",
                     help="print a per-skill inferred-tag table for every third-party skill "
                          "and exit — no files are written")
    ap.add_argument("--out-dir", default=None,
                     help="default: ~/.claude/context-manager")
    args = ap.parse_args()

    static_path = Path(args.static)
    installed_plugins_path = (
        Path(args.installed_plugins) if args.installed_plugins
        else default_installed_plugins_path()
    )
    stack_config_path = (
        Path(args.stack_config) if args.stack_config else default_stack_config_path()
    )
    cooccurrence_path = (
        Path(args.cooccurrence) if args.cooccurrence else _default_cooccurrence_path()
    )
    global_settings_path = (
        Path(args.global_settings) if args.global_settings else default_global_settings_path()
    )
    local_settings_path = (
        Path(args.local_settings) if args.local_settings else default_local_settings_path()
    )
    tags_catalog_path = (
        Path(args.tags_catalog) if args.tags_catalog else default_tags_catalog_path()
    )
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()

    if not static_path.is_file():
        print(f"ERROR: static artifact not found at {static_path}", file=sys.stderr)
        print("  run scripts/build_skill_map.py first", file=sys.stderr)
        return 1

    local_doc, resolved_doc = build(
        static_path, installed_plugins_path, stack_config_path, cooccurrence_path,
        global_settings_path, local_settings_path, tags_catalog_path,
    )
    tags_catalog, tags_catalog_note = load_tags_catalog(tags_catalog_path)

    if args.report_inferred:
        print_inferred_report(local_doc["thirdParty"]["nodes"], tags_catalog)
        print(f"  [tagsCatalog] {tags_catalog_note}")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / "skill-map.local.json"
    resolved_path = out_dir / "skill-map.resolved.json"
    local_path.write_text(dump(local_doc))
    resolved_path.write_text(dump(resolved_doc))

    print(f"Wrote {local_path}")
    print(f"Wrote {resolved_path}")
    print(f"Enabled plugins: {local_doc['enabledPlugins']}")
    print(f"Usage-cooccurs edges: {len(local_doc['usageCooccursEdges'])}")
    print(f"Follows edges: {len(local_doc['followsEdges'])}")
    tp = local_doc["thirdParty"]["summary"]
    print(
        f"Third-party inventory: {tp['plugins']} plugins, {tp['skills']} skills, "
        f"{tp['commands']} commands (skipped {tp['skippedPlugins']} plugins, "
        f"{tp['skippedEntries']} entries)"
    )
    for key, note in local_doc["sourceNotes"].items():
        print(f"  [{key}] {note}")

    static_indexes_path = Path(args.static_indexes)
    static_indexes_data, indexes_err = _load_json(static_indexes_path)
    if indexes_err:
        print(f"  [indexes] degraded: {indexes_err} — no resolved indexes written")
    else:
        resolved_indexes = build_resolved_indexes(
            static_indexes_data,
            local_doc["followsEdges"],
            local_doc["thirdParty"]["nodes"],
            tags_catalog,
        )
        resolved_indexes_path = out_dir / "skill-map.indexes.resolved.json"
        resolved_indexes_path.write_text(dump(resolved_indexes))
        print(f"Wrote {resolved_indexes_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
