#!/usr/bin/env python3
"""Static schema validator for a `claude plugin eval` suite.

`claude plugin eval` is gated per-organization (early access) and is not yet
runnable in this environment (see evals/README.md). There is no public docs
page for the harness's case-file format. This validator's rule set is taken
from Claude Code's own internal reference doc for `claude plugin eval` —
compiled into the CLI binary and surfaced to a `claude-code-guide` agent
session — extracted verbatim to a scratch file and read in full on
2026-08-25 against Claude Code 2.1.241.

This is a *schema* validator only. It confirms case.yaml / prompt.md /
graders/*.md are structurally well-formed per that reference and flags a
couple of authoring foot-guns the doc calls out explicitly (a `tool_used`
grader that can never pass; a Skill-routing grader silently excluded from
scoring). It does NOT run a single agent, call a grader, or measure whether
any skill actually triggers on a prompt — none of that is knowable until the
early-access gate opens and the real harness can be run.

RE-CHECK WHEN THE GATE LIFTS: this rule set was never diffed against a real
`claude plugin eval` run or its `--help` output — only against the extracted
reference doc. Once the harness is runnable, re-derive these rules from
`claude plugin eval --help` and a real run's behavior, and correct anything
this file got wrong.

Requires only the Python 3 standard library plus PyYAML (`import yaml`).
Does NOT use `jsonschema` — it is not installed in this environment.

Usage:
    python3 evals/validate-suite.py [--eval-dir DIR]

Exit status: 1 if any ERROR was reported, 0 otherwise (WARNs do not fail
the run).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# --------------------------------------------------------------------------
# Schema constants, transcribed from the reference doc's "Authoring cases"
# and "Graders" sections.
# --------------------------------------------------------------------------

SKIP_DIR_NAMES = {"node_modules", ".git", ".claude", "results"}

MAX_FILE_BYTES = 1024 * 1024  # "each file <= 1 MiB"
MAX_GRADER_FILES = 256  # "<= 256 grader files"

MIN_RUNS, MAX_RUNS = 1, 50  # "runs | int 1-50"
MAX_MAX_TURNS = 200  # "max_turns | int <= 200"
MAX_TIMEOUT_SECONDS = 3600  # "timeout_seconds | int <= 3600"

# prompt.md frontmatter -> case fields. "Any other key is an error naming
# the allowed set." context.* is deliberately absent: it can only live in
# case.yaml.
PROMPT_MD_ALLOWED_KEYS = {
    "schema_version", "name", "description", "tags", "plugins", "runs",
    "expected_outcome", "model", "max_turns", "timeout_seconds",
    "allowed_tools", "append_system_prompt", "env",
}

# case.yaml top-level keys the harness recognizes. Anything else is
# "ignored (forward compatibility)" -> WARN, not ERROR.
CASE_YAML_KNOWN_TOP_KEYS = {
    "schema_version", "name", "description", "tags", "plugins", "runs",
    "expected_outcome", "context", "execution", "graders",
}

# "Unknown top-level, context, and execution keys are ignored"
CASE_YAML_KNOWN_CONTEXT_KEYS = {"scaffold_script", "history_file", "add_dirs"}
CASE_YAML_KNOWN_EXECUTION_KEYS = {
    "prompt", "model", "max_turns", "timeout_seconds", "allowed_tools",
    "append_system_prompt", "env",
}

# "unknown keys inside a grader are an error" (unlike case-level keys)
GRADER_TYPES = {"regex", "tool_used", "tool_order", "file_exists", "llm", "baseline"}
GRADER_COMMON_KEYS = {"type", "name", "weight", "arm"}
GRADER_TYPE_KEYS = {
    "regex": {"pattern", "flags", "match", "target"},
    "tool_used": {"tool", "input_match", "min", "max"},
    "tool_order": {"before", "after"},
    "file_exists": {"path", "exists"},
    "llm": {"criteria", "focus"},
    "baseline": {"baseline_file", "criteria"},
}

# The keys a grader of this type cannot function without, per the reference
# doc's Graders table (§ Graders, the type/keys/"passes when" table). Every
# key here is documented with no default value — contrast `tool_used`'s
# required `tool` with its explicitly-"optional" `input_match`, or
# `file_exists`'s required `path` with its `exists` (default `true`).
GRADER_REQUIRED_KEYS: dict[str, set[str]] = {
    "regex": {"pattern"},
    "tool_used": {"tool"},
    "tool_order": {"before", "after"},
    "file_exists": {"path"},
    "llm": {"criteria"},
    "baseline": {"baseline_file", "criteria"},
}

# For a PROSE grader file (graders/<name>.md) only, exactly one required
# field per type may be satisfied by the file's body instead of frontmatter
# — "### Prose layout": "<grader>.md  frontmatter -> grader fields; body ->
# criteria (llm/baseline) or pattern (regex)". This is not hypothetical:
# this suite's own graders/surfaces-the-refusal.md (type: llm) has no
# `criteria:` in frontmatter and relies entirely on its body. case.yaml
# graders are YAML list entries with no body, so for them the key must
# always be given explicitly (see the full case.yaml example, which spells
# out `pattern:`/`criteria:` for every regex/llm/baseline grader).
GRADER_BODY_FALLBACK_FIELD = {"regex": "pattern", "llm": "criteria", "baseline": "criteria"}

VALID_TARGET_FOCUS_LITERALS = {"last_message", "trace", "files"}

# "env: Keys must match EVAL_[A-Z0-9_]*; any other key fails the run"
ENV_KEY_RE = re.compile(r"^EVAL_[A-Z0-9_]*$")

EXECUTION_BOUNDS_KEYS = {"runs", "max_turns", "timeout_seconds"}


# --------------------------------------------------------------------------
# Issue tracking / reporting
# --------------------------------------------------------------------------

class Reporter:
    def __init__(self) -> None:
        self.error_count = 0
        self.warn_count = 0
        self.ok_count = 0
        self._case_had_issue: set[str] = set()

    def error(self, loc: str, msg: str) -> None:
        print(f"ERROR {loc}: {msg}")
        self.error_count += 1
        self._case_had_issue.add(loc.split("/", 1)[0])

    def warn(self, loc: str, msg: str) -> None:
        print(f"WARN {loc}: {msg}")
        self.warn_count += 1
        self._case_had_issue.add(loc.split("/", 1)[0])

    def ok_if_clean(self, case_name: str) -> None:
        if case_name not in self._case_had_issue:
            print(f"OK {case_name}: no schema issues found")
            self.ok_count += 1


# --------------------------------------------------------------------------
# Frontmatter parsing (shared by prompt.md and graders/*.md)
# --------------------------------------------------------------------------

_MALFORMED = object()


def split_frontmatter(text: str):
    """Returns (frontmatter_text_or_None_or_MALFORMED, body_text).

    None means the file has no frontmatter block at all (didn't open with a
    `---` line) — that is valid for prompt.md (all defaults apply) and means
    "ignored by the harness" for a grader file.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_text = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return fm_text, body
    return _MALFORMED, text


def read_file(path: Path, r: Reporter, loc: str) -> str | None:
    try:
        data = path.read_bytes()
    except OSError as e:
        r.error(loc, f"could not read file: {e}")
        return None
    if len(data) > MAX_FILE_BYTES:
        r.error(loc, f"file exceeds the 1 MiB per-file limit ({len(data)} bytes)")
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        r.error(loc, f"file is not valid UTF-8: {e}")
        return None


def load_frontmatter(text: str, r: Reporter, loc: str):
    """Parses a file's frontmatter block. Returns (dict_or_None, body, had_block).

    dict is None if there was no frontmatter block, if it was malformed
    (opened but never closed), if the YAML failed to parse, or if it parsed
    to something other than a mapping — each case is reported by the caller
    (some of these are valid states depending on file type, so this
    function does not itself decide ERROR vs. "this is fine").
    """
    fm_text, body = split_frontmatter(text)
    if fm_text is None:
        return None, body, False
    if fm_text is _MALFORMED:
        r.error(loc, "frontmatter opened with '---' but was never closed with a second '---'")
        return None, body, True
    if fm_text.strip() == "":
        return {}, body, True
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        r.error(loc, f"frontmatter is not valid YAML: {e}")
        return None, body, True
    if data is None:
        return {}, body, True
    if not isinstance(data, dict):
        r.error(loc, f"frontmatter must be a YAML mapping, got {type(data).__name__}")
        return None, body, True
    return data, body, True


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def discover_cases(eval_dir: Path) -> list[Path]:
    """Recursively finds case directories under eval_dir.

    Per the doc: a directory holding prompt.md and/or case.yaml is a case
    and is NOT recursed into further. A directory that is not itself a case
    is skipped as a case but is searched beneath for nested case groups.
    node_modules/.git/.claude/results are skipped entirely, anywhere.
    """
    cases: list[Path] = []

    def walk(d: Path) -> None:
        if not d.is_dir():
            return
        has_prompt = (d / "prompt.md").is_file()
        has_case_yaml = (d / "case.yaml").is_file()
        if has_prompt or has_case_yaml:
            cases.append(d)
            return  # discovery does not recurse into a case directory
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name in SKIP_DIR_NAMES:
                continue
            if entry.is_dir():
                walk(entry)

    walk(eval_dir)
    # "Cases run in lexicographic directory order."
    return sorted(cases, key=lambda p: str(p.relative_to(eval_dir)))


# --------------------------------------------------------------------------
# Grader validation
# --------------------------------------------------------------------------

class GraderInfo:
    __slots__ = ("name", "type", "tool", "has_arm", "arm_value", "loc")

    def __init__(self, name, gtype, tool, has_arm, arm_value, loc):
        self.name = name
        self.type = gtype
        self.tool = tool
        self.has_arm = has_arm
        self.arm_value = arm_value
        self.loc = loc


def check_regex_field(pattern, r: Reporter, loc: str, field: str) -> None:
    """Compiles a regex-bearing field with `re.compile`; ERROR if it can't.

    Silent when `pattern` is None — a missing required field is already
    reported by the required-key check; this only judges a *present* value.
    """
    if pattern is None:
        return
    if not isinstance(pattern, str):
        r.error(loc, f"'{field}' must be a string regex source, got {type(pattern).__name__}")
        return
    try:
        re.compile(pattern)
    except re.error as e:
        r.error(loc, f"'{field}' is not a valid regex — it can never compile, so the grader can never run: {e}")


def validate_grader_config(cfg: dict, gtype: str, r: Reporter, loc: str, body: str | None = None) -> None:
    if gtype not in GRADER_TYPE_KEYS:
        return  # unknown type already reported by the caller
    allowed = GRADER_COMMON_KEYS | GRADER_TYPE_KEYS[gtype]
    for key in cfg.keys():
        if key not in allowed:
            r.error(loc, f"unknown key '{key}' inside a '{gtype}' grader (unknown grader keys are an error, unlike case-level keys)")

    weight = cfg.get("weight", 1)
    if not isinstance(weight, bool) and isinstance(weight, (int, float)):
        if weight <= 0:
            r.error(loc, f"grader 'weight' must be > 0 (there is no weight: 0 — remove the grader or use 'arm'), got {weight}")
    else:
        r.error(loc, f"grader 'weight' must be a number, got {type(weight).__name__}")

    # "Must not call" idiom: max: 0 alone can never pass because min stays 1.
    if gtype == "tool_used":
        if cfg.get("max") == 0 and not isinstance(cfg.get("max"), bool) and "min" not in cfg:
            r.error(loc, "tool_used grader has max: 0 with no explicit min: — this can never pass, because `min` defaults to 1. Add `min: 0` for the 'must not call' idiom (min: 0, max: 0).")

    # target (regex) / focus (llm) enum-or-mapping check
    target_key = "target" if gtype == "regex" else ("focus" if gtype == "llm" else None)
    if target_key and target_key in cfg:
        val = cfg[target_key]
        valid = False
        if isinstance(val, str) and val in VALID_TARGET_FOCUS_LITERALS:
            valid = True
        elif isinstance(val, dict) and val.get("source") == "file" and "path" in val:
            valid = True
        if not valid:
            r.error(loc, f"'{target_key}' must be one of {sorted(VALID_TARGET_FOCUS_LITERALS)} or a mapping {{source: file, path: ...}} — got {val!r} (a free-text string is an error)")

    # Type-specific required fields the grader cannot function without.
    body_fallback_field = GRADER_BODY_FALLBACK_FIELD.get(gtype)
    body_has_content = bool(body) and body.strip() != ""
    for req_key in sorted(GRADER_REQUIRED_KEYS.get(gtype, ())):
        if cfg.get(req_key):
            continue
        if req_key == body_fallback_field and body_has_content:
            continue  # satisfied by the prose grader file's body
        via_body = " (or a non-empty body, for a prose grader file)" if req_key == body_fallback_field else ""
        r.error(loc, f"'{gtype}' grader is missing required '{req_key}'{via_body} — it cannot function without it")

    # tool_order: `before`/`after`, when given as a mapping, need `tool`.
    if gtype == "tool_order":
        for key in ("before", "after"):
            val = cfg.get(key)
            if isinstance(val, dict) and not val.get("tool"):
                r.error(loc, f"tool_order '{key}' is a mapping but has no 'tool' key — expected a tool name or {{ tool, input_match }}")

    # Compile every regex-bearing field this grader type can hold.
    if gtype == "regex":
        pattern = cfg.get("pattern")
        if pattern is None and body_fallback_field == "pattern" and body_has_content:
            pattern = body.strip()
        check_regex_field(pattern, r, loc, "pattern")
    if gtype == "tool_used" and "input_match" in cfg:
        check_regex_field(cfg.get("input_match"), r, loc, "input_match")
    if gtype == "tool_order":
        for key in ("before", "after"):
            val = cfg.get(key)
            if isinstance(val, dict) and "input_match" in val:
                check_regex_field(val.get("input_match"), r, loc, f"{key}.input_match")


def make_grader_info(name, cfg: dict, gtype, loc: str) -> GraderInfo:
    has_arm = "arm" in cfg
    return GraderInfo(
        name=name,
        gtype=gtype if gtype in GRADER_TYPES else None,
        tool=cfg.get("tool"),
        has_arm=has_arm,
        arm_value=cfg.get("arm"),
        loc=loc,
    )


def validate_yaml_grader(entry, idx: int, case_name: str, r: Reporter) -> GraderInfo | None:
    loc = f"{case_name}/case.yaml"
    if not isinstance(entry, dict):
        r.error(loc, f"graders[{idx}] must be a mapping, got {type(entry).__name__}")
        return None
    gtype = entry.get("type")
    if gtype is None:
        r.error(loc, f"graders[{idx}] is missing required 'type'")
        return None
    if gtype not in GRADER_TYPES:
        r.error(loc, f"graders[{idx}] has unknown type '{gtype}' — valid types: {sorted(GRADER_TYPES)}")
        return None
    name = entry.get("name")
    if not name:
        r.error(loc, f"graders[{idx}] (type: {gtype}) is missing required 'name' (name is required in case.yaml graders, unlike prose graders which take it from the filename)")
        name = f"<unnamed-{idx}>"
    validate_grader_config(entry, gtype, r, loc)
    return GraderInfo(name=name, gtype=gtype, tool=entry.get("tool"), has_arm=("arm" in entry), arm_value=entry.get("arm"), loc=loc)


def validate_prose_grader(path: Path, case_name: str, r: Reporter) -> GraderInfo | None:
    rel = f"{case_name}/graders/{path.name}"
    text = read_file(path, r, rel)
    if text is None:
        return None
    fm, body, had_block = load_frontmatter(text, r, rel)
    if not had_block:
        r.warn(rel, "file has no frontmatter block — the harness ignores it entirely (it is inert, not a grader). Add frontmatter with at least 'type:', or delete the file if it's meant as a note.")
        return None
    if fm is None:
        return None  # already reported (malformed / bad YAML / not a mapping)
    gtype = fm.get("type")
    if gtype is None:
        r.error(rel, "grader file has frontmatter but no 'type' key — every grader needs 'type:' in frontmatter")
        return None
    if gtype not in GRADER_TYPES:
        r.error(rel, f"unknown grader type '{gtype}' — valid types: {sorted(GRADER_TYPES)}")
        return None
    name = fm.get("name") or path.stem
    validate_grader_config(fm, gtype, r, rel, body=body)
    return GraderInfo(name=name, gtype=gtype, tool=fm.get("tool"), has_arm=("arm" in fm), arm_value=fm.get("arm"), loc=rel)


def collect_and_validate_graders(case_dir: Path, case_name: str, case_yaml_data: dict | None, r: Reporter) -> list[GraderInfo]:
    graders: list[GraderInfo] = []

    if case_yaml_data is not None:
        yaml_graders = case_yaml_data.get("graders")
        if yaml_graders is not None:
            if not isinstance(yaml_graders, list):
                r.error(f"{case_name}/case.yaml", f"'graders' must be a list, got {type(yaml_graders).__name__}")
            else:
                for idx, entry in enumerate(yaml_graders):
                    gi = validate_yaml_grader(entry, idx, case_name, r)
                    if gi is not None:
                        graders.append(gi)

    graders_dir = case_dir / "graders"
    if graders_dir.is_dir():
        grader_files = sorted(p for p in graders_dir.iterdir() if p.is_file() and p.suffix == ".md")
        if len(grader_files) > MAX_GRADER_FILES:
            r.error(f"{case_name}/graders", f"{len(grader_files)} grader files exceeds the limit of {MAX_GRADER_FILES}")
        for p in grader_files:
            gi = validate_prose_grader(p, case_name, r)
            if gi is not None:
                graders.append(gi)

    # Structural checks over the combined grader set.
    if len(graders) == 0:
        r.error(case_name, "case has no graders — at least 1 grader is required (from case.yaml's 'graders' list and/or graders/*.md)")

    seen_names: dict[str, str] = {}
    for gi in graders:
        if gi.name in seen_names:
            r.error(gi.loc, f"duplicate grader name '{gi.name}' within this case (also defined at {seen_names[gi.name]}) — grader names must be unique within a case")
        else:
            seen_names[gi.name] = gi.loc

    # Baseline-arm "with-only" implicit-Skill warning, per doc:
    # "every tool_used grader on Skill with no explicit arm" is dropped from
    # the without-arm and excluded from scoring in BOTH arms under the
    # default --ablation with-without — "unless every grader is with-only,
    # in which case they are scored normally."
    implicit_with_only = [g for g in graders if g.type == "tool_used" and g.tool == "Skill" and not g.has_arm]
    explicit_with_only = [g for g in graders if g.arm_value == "with-only"]
    with_only_total = len(implicit_with_only) + len(explicit_with_only)
    suppress = len(graders) > 0 and with_only_total == len(graders)
    if not suppress:
        for g in implicit_with_only:
            r.warn(g.loc, "tool_used grader on tool: Skill has no explicit `arm:` — it is dropped from the without-arm and EXCLUDED FROM THE SCORE IN BOTH ARMS under the default --ablation with-without. Set `arm: both` if this is a 'must NOT fire' check that should actually be scored.")

    return graders


# --------------------------------------------------------------------------
# case.yaml / prompt.md validation
# --------------------------------------------------------------------------

def check_type(value, expected, r: Reporter, loc: str, field: str) -> bool:
    if expected is list and not isinstance(value, list):
        r.error(loc, f"'{field}' must be a list, got {type(value).__name__}")
        return False
    if expected is dict and not isinstance(value, dict):
        r.error(loc, f"'{field}' must be a mapping, got {type(value).__name__}")
        return False
    if expected is int and (isinstance(value, bool) or not isinstance(value, int)):
        r.error(loc, f"'{field}' must be an integer, got {type(value).__name__}")
        return False
    return True


def check_schema_version(version, r: Reporter, loc: str) -> None:
    if not isinstance(version, str):
        r.error(loc, f"'schema_version' must be a string, got {type(version).__name__}")
        return
    major = version.split(".", 1)[0]
    try:
        major_n = int(major)
    except ValueError:
        r.error(loc, f"'schema_version' \"{version}\" is not parseable (expected e.g. \"1.1\")")
        return
    if major_n != 1:
        r.error(loc, f"'schema_version' \"{version}\" requires a newer Claude Code (this validator, matching the current binary, supports up to major version 1.x)")


def check_env(env, r: Reporter, loc: str) -> None:
    if not check_type(env, dict, r, loc, "env"):
        return
    for key in env.keys():
        if not isinstance(key, str) or not ENV_KEY_RE.match(key):
            r.error(loc, f"env key '{key}' does not match ^EVAL_[A-Z0-9_]*$ — any key outside that pattern fails the run at execution time")


def check_bounds(effective: dict, origin: dict, case_name: str) -> list:
    issues = []
    if "runs" in effective:
        v = effective["runs"]
        loc = f"{case_name}/{origin['runs']}"
        if isinstance(v, bool) or not isinstance(v, int):
            issues.append(("error", loc, f"'runs' must be an integer, got {type(v).__name__}"))
        elif not (MIN_RUNS <= v <= MAX_RUNS):
            issues.append(("error", loc, f"'runs' must be between {MIN_RUNS} and {MAX_RUNS}, got {v}"))
    if "max_turns" in effective:
        v = effective["max_turns"]
        loc = f"{case_name}/{origin['max_turns']}"
        if isinstance(v, bool) or not isinstance(v, int):
            issues.append(("error", loc, f"'max_turns' must be an integer, got {type(v).__name__}"))
        elif v > MAX_MAX_TURNS:
            issues.append(("error", loc, f"'max_turns' must be <= {MAX_MAX_TURNS}, got {v}"))
    if "timeout_seconds" in effective:
        v = effective["timeout_seconds"]
        loc = f"{case_name}/{origin['timeout_seconds']}"
        if isinstance(v, bool) or not isinstance(v, int):
            issues.append(("error", loc, f"'timeout_seconds' must be an integer, got {type(v).__name__}"))
        elif v > MAX_TIMEOUT_SECONDS:
            issues.append(("error", loc, f"'timeout_seconds' must be <= {MAX_TIMEOUT_SECONDS}, got {v}"))
    return issues


def validate_case(case_dir: Path, eval_dir: Path, r: Reporter) -> None:
    case_name = str(case_dir.relative_to(eval_dir))
    prompt_path = case_dir / "prompt.md"
    case_yaml_path = case_dir / "case.yaml"

    case_yaml_data: dict | None = None
    if case_yaml_path.is_file():
        loc = f"{case_name}/case.yaml"
        text = read_file(case_yaml_path, r, loc)
        if text is not None:
            try:
                parsed = yaml.safe_load(text)
            except yaml.YAMLError as e:
                r.error(loc, f"not valid YAML: {e}")
                parsed = None
            if parsed is not None and not isinstance(parsed, dict):
                r.error(loc, f"top-level document must be a mapping, got {type(parsed).__name__}")
                parsed = None
            case_yaml_data = parsed if isinstance(parsed, dict) else None

        if case_yaml_data is not None:
            if "schema_version" not in case_yaml_data:
                r.error(loc, "'schema_version' is required whenever case.yaml exists")
            else:
                check_schema_version(case_yaml_data["schema_version"], r, loc)
            if not case_yaml_data.get("name"):
                r.error(loc, "'name' is required whenever case.yaml exists")

            for key in case_yaml_data.keys():
                if key not in CASE_YAML_KNOWN_TOP_KEYS:
                    r.warn(loc, f"unknown top-level key '{key}' — the harness silently IGNORES unknown case.yaml keys (forward compatibility), it does not reject them. This setting will be silently dropped, not applied.")

            ctx = case_yaml_data.get("context")
            if ctx is not None and check_type(ctx, dict, r, loc, "context"):
                for key in ctx.keys():
                    if key not in CASE_YAML_KNOWN_CONTEXT_KEYS:
                        r.warn(loc, f"unknown key 'context.{key}' — unknown context keys are silently IGNORED by the harness, not rejected. This setting will be silently dropped, not applied.")
                add_dirs = ctx.get("add_dirs")
                if add_dirs is not None and check_type(add_dirs, list, r, loc, "context.add_dirs"):
                    for d in add_dirs:
                        target = (case_dir / str(d)).resolve()
                        try:
                            target.relative_to(case_dir.resolve())
                        except ValueError:
                            r.error(loc, f"context.add_dirs entry '{d}' resolves outside the case directory — add_dirs must stay inside the case dir")
                for file_field in ("scaffold_script", "history_file"):
                    val = ctx.get(file_field)
                    if val:
                        if not (case_dir / str(val)).is_file():
                            r.error(loc, f"context.{file_field} '{val}' does not exist relative to the case directory")

            execu = case_yaml_data.get("execution")
            if execu is not None and check_type(execu, dict, r, loc, "execution"):
                for key in execu.keys():
                    if key not in CASE_YAML_KNOWN_EXECUTION_KEYS:
                        r.warn(loc, f"unknown key 'execution.{key}' — unknown execution keys are silently IGNORED by the harness, not rejected. This setting will be silently dropped, not applied.")
                if "env" in execu:
                    check_env(execu["env"], r, loc)

    prompt_fm: dict | None = None
    prompt_body = ""
    if prompt_path.is_file():
        loc = f"{case_name}/prompt.md"
        text = read_file(prompt_path, r, loc)
        if text is not None:
            fm, body, _had_block = load_frontmatter(text, r, loc)
            prompt_body = body
            if fm is not None:
                prompt_fm = fm
                for key in fm.keys():
                    if key == "context":
                        r.error(loc, "'context' cannot be set from prompt.md frontmatter (context.scaffold_script/history_file/add_dirs can only live in case.yaml)")
                    elif key not in PROMPT_MD_ALLOWED_KEYS:
                        r.error(loc, f"unknown prompt.md frontmatter key '{key}' — allowed keys: {sorted(PROMPT_MD_ALLOWED_KEYS)}")
                if "env" in fm:
                    check_env(fm["env"], r, loc)
                if "schema_version" in fm:
                    check_schema_version(fm["schema_version"], r, loc)

    # Required prompt: execution.prompt (case.yaml) or a non-empty prompt.md body.
    has_body = bool(prompt_body.strip())
    has_exec_prompt = bool(
        case_yaml_data
        and isinstance(case_yaml_data.get("execution"), dict)
        and str(case_yaml_data["execution"].get("prompt") or "").strip()
    )
    if not has_body and not has_exec_prompt:
        r.error(case_name, "no prompt found — need either execution.prompt in case.yaml or a non-empty prompt.md body")

    # Effective (merged) execution fields: prompt.md frontmatter overrides
    # case.yaml, per "prompt.md frontmatter overrides it" in the merge order.
    case_exec = case_yaml_data.get("execution") if isinstance(case_yaml_data, dict) else None
    case_exec = case_exec if isinstance(case_exec, dict) else {}
    effective: dict = {}
    origin: dict = {}
    for key in EXECUTION_BOUNDS_KEYS:
        if prompt_fm is not None and key in prompt_fm:
            effective[key] = prompt_fm[key]
            origin[key] = "prompt.md"
        elif key in case_exec:
            effective[key] = case_exec[key]
            origin[key] = "case.yaml"
    for lvl, loc, msg in check_bounds(effective, origin, case_name):
        r.error(loc, msg) if lvl == "error" else r.warn(loc, msg)

    # Graders (combined case.yaml + graders/*.md)
    collect_and_validate_graders(case_dir, case_name, case_yaml_data, r)

    r.ok_if_clean(case_name)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def resolve_eval_dir(arg: str | None) -> Path:
    if arg is not None:
        return Path(arg).resolve()
    candidate = Path.cwd() / "evals"
    if candidate.is_dir():
        return candidate
    # Convenience fallback: this script lives inside the eval directory
    # itself, so if "./evals" isn't found relative to cwd (e.g. this script
    # was invoked while already cd'd into evals/), fall back to its own
    # containing directory.
    script_dir = Path(__file__).resolve().parent
    return script_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Static schema validator for a claude plugin eval suite.")
    parser.add_argument("--eval-dir", default=None, help="Path to the eval directory (default: ./evals, falling back to this script's own directory)")
    args = parser.parse_args()

    eval_dir = resolve_eval_dir(args.eval_dir)
    if not eval_dir.is_dir():
        print(f"ERROR {eval_dir}: eval directory does not exist")
        return 1

    r = Reporter()
    cases = discover_cases(eval_dir)
    if not cases:
        r.warn(str(eval_dir), "no eval cases found (no directory under it holds prompt.md or case.yaml)")
    for case_dir in cases:
        validate_case(case_dir, eval_dir, r)

    print(f"== {len(cases)} case(s), {r.error_count} error(s), {r.warn_count} warning(s), {r.ok_count} clean ==")
    return 1 if r.error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
