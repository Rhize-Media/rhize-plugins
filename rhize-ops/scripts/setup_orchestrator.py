#!/usr/bin/env python3
"""setup_orchestrator.py — deterministic backend for /rhize-ops:rhize-setup (R2, the hybrid
setup wizard). `/rhize-ops:rhize-setup` (the command .md) keeps only interaction — questions,
confirmations, and invoking plugin wizards via the Skill tool — and calls these subcommands by
path for every deterministic step. Stdlib-only, argv-array subprocess, no shell strings.

Subcommands:
  discover --json                              marketplace clone or dev repo, enabled plugins,
                                                parsed manifests (schema 1/2/3), effective hook
                                                state, per-item wired/not-wired/disabled labels,
                                                clone vs installed cache version per plugin.
  hooks plan --plugin P --item I --json        portable command + sh -c smoke test result.
  hooks apply --plan <path-to-json>            merge approved hook plans into the project's
                                                .claude/settings.json only.
  artifacts snapshot --before|--after --run ID existence-only snapshot of declared artifacts.
  install-skill-map --source <root>            install the compiled skill map for this machine.
  report --run ID                              render every recorded section of a run's state.
  report record --run ID --section S --data F  persist a JSON fragment into a run's state (used
                                                by the command .md for phases this script does
                                                not itself compute, e.g. the dependency check).

Every subcommand accepts a --home override (and --project where it reads or writes project
state) so tests never touch the real machine.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import evaluation_setup as evalsetup  # noqa: E402

SCHEMA_DISCOVER = "rhize-setup-discover-v1"
SCHEMA_HOOKS_PLAN = "rhize-setup-hooks-plan-v1"
SCHEMA_HOOKS_APPLY = "rhize-setup-hooks-apply-v1"
SCHEMA_ARTIFACTS_SNAPSHOT = "rhize-setup-artifacts-snapshot-v1"
SCHEMA_INSTALL_SKILL_MAP = "rhize-setup-install-skill-map-v1"

RHIZE_SIGNATURE_PLUGIN = "rhize-ops"
STDIN_TOOL_CALL_EVENTS = {"PreToolUse", "PostToolUse"}
ECC_HOOK_ID_MARKERS = ("gateguard", "gate-guard")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


class OrchestratorError(ValueError):
    pass


# ---------- small shared helpers ----------

def resolve_cli_path(raw: str | Path) -> Path:
    return Path(raw).expanduser().resolve()


def load_json_or(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def private_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)
    path.chmod(0o600)


def run_state_path(home: Path, run_id: str) -> Path:
    return home / ".rhize" / "setup" / "runs" / f"{run_id}.json"


def record_run_section(home: Path, run_id: str | None, section: str, data: Any) -> None:
    if not run_id:
        return
    path = run_state_path(home, run_id)
    state = load_json_or(path, {})
    if not isinstance(state, dict):
        state = {}
    state[section] = data
    private_write_json(path, state)


# ---------- source discovery ----------

def find_dev_repo(project: Path) -> Path | None:
    if (project / ".claude-plugin" / "marketplace.json").is_file():
        return project
    return None


def find_marketplace_clones(home: Path) -> list[Path]:
    root = home / ".claude" / "plugins" / "marketplaces"
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir()
        if p.is_dir() and (p / ".claude-plugin" / "marketplace.json").is_file()
    )


def is_rhize_marketplace(root: Path) -> bool:
    return (root / RHIZE_SIGNATURE_PLUGIN / ".claude-plugin" / "plugin.json").is_file()


def discover_source(home: Path, project: Path) -> dict[str, Any]:
    """Prefer a dev-repo checkout (cwd/--project IS the rhize-plugins source tree);
    otherwise the installed marketplace clone. Identifies "the rhize-plugins one" among
    however many marketplace clones exist by content (a stable, distinctive plugin dir),
    not by directory name, so a renamed marketplace clone is still found."""
    dev_repo = find_dev_repo(project)
    if dev_repo is not None and is_rhize_marketplace(dev_repo):
        return {
            "kind": "dev-repo",
            "root": str(dev_repo),
            "clone_name": dev_repo.name,
            "portability": "dev-repo",
        }
    candidates = [c for c in find_marketplace_clones(home) if is_rhize_marketplace(c)]
    if not candidates:
        raise OrchestratorError(
            "no rhize-plugins marketplace clone found under "
            f"{home / '.claude' / 'plugins' / 'marketplaces'} and {project} is not a "
            "rhize-plugins dev checkout"
        )
    chosen = candidates[0]
    result: dict[str, Any] = {
        "kind": "marketplace-clone",
        "root": str(chosen),
        "clone_name": chosen.name,
        "portability": "portable",
    }
    if len(candidates) > 1:
        result["ambiguous_clones"] = [str(c) for c in candidates[1:]]
    return result


def discover_plugins(source_root: Path) -> list[Path]:
    return sorted(
        p for p in source_root.iterdir()
        if p.is_dir() and (p / ".claude-plugin" / "plugin.json").is_file()
    )


def enabled_plugin_map(home: Path) -> dict[str, Any]:
    settings = load_json_or(home / ".claude" / "settings.json", {})
    enabled = settings.get("enabledPlugins") if isinstance(settings, dict) else None
    return enabled if isinstance(enabled, dict) else {}


def plugin_enabled(name: str, source: dict[str, Any], enabled_map: dict[str, Any]) -> tuple[bool, str]:
    key = f"{name}@{source['clone_name']}"
    if key in enabled_map:
        return enabled_map[key] is True, "enabledPlugins"
    if source["kind"] == "dev-repo":
        return True, "dev-repo-default"
    return False, "not in enabledPlugins"


# ---------- versions ----------

def plugin_version(plugin_dir: Path) -> str | None:
    manifest = load_json_or(plugin_dir / ".claude-plugin" / "plugin.json", {})
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) else None


def semver_tuple(version: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(version)
    if not match:
        return None
    a, b, c = match.groups()
    return int(a), int(b), int(c)


def installed_cache_version(home: Path, marketplace_name: str, plugin_name: str) -> str | None:
    cache_dir = home / ".claude" / "plugins" / "cache" / marketplace_name / plugin_name
    if not cache_dir.is_dir():
        return None
    parsed = [(semver_tuple(p.name), p.name) for p in cache_dir.iterdir() if p.is_dir()]
    parsed = [item for item in parsed if item[0] is not None]
    if not parsed:
        return None
    parsed.sort()
    return parsed[-1][1]


def clone_ahead_of_installed(clone_version: str | None, installed_version: str | None) -> bool | None:
    if clone_version is None or installed_version is None:
        return None
    a, b = semver_tuple(clone_version), semver_tuple(installed_version)
    if a is None or b is None:
        return None
    return a > b


# ---------- effective hook state ----------

def read_settings_hooks_and_env(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    data = load_json_or(path, {})
    if not isinstance(data, dict):
        return {}, {}
    hooks = data.get("hooks")
    env = data.get("env")
    return (hooks if isinstance(hooks, dict) else {}), (env if isinstance(env, dict) else {})


def collect_wired_commands(project: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    wired: dict[str, set[str]] = {}
    merged_env: dict[str, str] = {}
    for relative in (".claude/settings.json", ".claude/settings.local.json"):
        hooks, env = read_settings_hooks_and_env(project / relative)
        merged_env.update({k: v for k, v in env.items() if isinstance(v, str)})
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                continue
            bucket = wired.setdefault(event, set())
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    continue
                for hook in group["hooks"]:
                    if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                        bucket.add(hook["command"])
    return wired, merged_env


def portable_root(source: dict[str, Any], plugin_name: str) -> str | None:
    if source["kind"] != "marketplace-clone":
        return None
    return f"$HOME/.claude/plugins/marketplaces/{source['clone_name']}/{plugin_name}"


def classify_item(
    item: dict[str, Any],
    plugin_name: str,
    source: dict[str, Any],
    wired_commands: dict[str, set[str]],
    env: dict[str, str],
) -> dict[str, Any]:
    event = item["event"]
    template = item["command"]
    absolute_command = template.replace("${CLAUDE_PLUGIN_ROOT}", str(Path(source["root"]) / plugin_name))
    candidates: list[tuple[str, str]] = [(absolute_command, "machine-specific" if source["kind"] == "marketplace-clone" else "dev-repo")]
    root = portable_root(source, plugin_name)
    if root is not None:
        candidates.append((template.replace("${CLAUDE_PLUGIN_ROOT}", root), "portable"))

    matched_portability = None
    for candidate, portability in candidates:
        if candidate in wired_commands.get(event, set()):
            matched_portability = portability
            break

    if matched_portability is None:
        status = "not wired"
    else:
        disabled_ids = {x.strip() for x in env.get("ECC_DISABLED_HOOKS", "").split(",") if x.strip()}
        item_id = item.get("id") or ""
        if env.get("ECC_GATEGUARD") == "off" and any(marker in item_id for marker in ECC_HOOK_ID_MARKERS):
            status = "wired but ECC_GATEGUARD=off"
        elif item_id in disabled_ids:
            status = "wired but disabled (ECC_DISABLED_HOOKS)"
        elif matched_portability == "machine-specific":
            status = "wired (machine-specific path)"
        else:
            status = "wired"

    classified: dict[str, Any] = {
        "id": item.get("id"),
        "title": item.get("title"),
        "tier": item.get("tier"),
        "event": event,
        "matcher": item.get("matcher"),
        "default": bool(item.get("default", False)),
        "resolved_command": absolute_command,
        "status": status,
    }
    if status == "wired (machine-specific path)" and root is not None:
        # Never rewritten by this tool; tell the reader how to make the entry portable.
        classified["migration_hint"] = (
            f"this entry starts with {source['root']}, which only exists on this machine; "
            f"replace that prefix with {root} in .claude/settings.json so teammates share it"
        )
    return classified


# ---------- vault placeholder resolution ----------

def resolve_vault_paths_for(source_root: Path) -> tuple[list[str], bool]:
    """Loads resolve_vault_paths() from the discovered obsidian-second-brain plugin's own
    hook script via importlib — never a second copy of that resolution logic (hybrid-setup-
    wizard.md decision 4 / R2 §1). Returns (paths, plugin_absent)."""
    module_path = source_root / "obsidian-second-brain" / "hooks" / "scripts" / "vault_resolve.py"
    if not module_path.is_file():
        return [], True
    spec = importlib.util.spec_from_file_location("rhize_setup_vault_resolve", module_path)
    if spec is None or spec.loader is None:
        return [], True
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        paths = module.resolve_vault_paths()
    except Exception:
        return [], False
    return (paths if isinstance(paths, list) else []), False


def vault_resolution_status(paths: list[str], plugin_absent: bool) -> str:
    if plugin_absent:
        return "unresolved (obsidian-second-brain plugin not found)"
    if not paths:
        return "unresolved (no vault found)"
    if len(paths) > 1:
        return f"unresolved (multiple vaults found: {len(paths)})"
    return "resolved"


# ---------- discover ----------

def discover_command(args: argparse.Namespace) -> int:
    home = resolve_cli_path(args.home)
    project = resolve_cli_path(args.project)
    try:
        source = discover_source(home, project)
    except OrchestratorError as exc:
        print(json.dumps({"schema": SCHEMA_DISCOVER, "error": str(exc)}, indent=2))
        return 2

    source_root = Path(source["root"])
    wired_commands, env = collect_wired_commands(project)
    enabled_map = enabled_plugin_map(home)

    plugins_out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for plugin_dir in discover_plugins(source_root):
        name = plugin_dir.name
        enabled, reason = plugin_enabled(name, source, enabled_map)
        clone_version = plugin_version(plugin_dir)
        installed_version = (
            installed_cache_version(home, source["clone_name"], name)
            if source["kind"] == "marketplace-clone" else None
        )
        entry: dict[str, Any] = {
            "name": name,
            "enabled": enabled,
            "enabled_reason": reason,
            "clone_version": clone_version,
            "installed_version": installed_version,
            "clone_ahead_of_installed": clone_ahead_of_installed(clone_version, installed_version),
        }
        manifest_path = plugin_dir / "setup" / "manifest.json"
        if not manifest_path.is_file():
            entry["manifest"] = None
        else:
            try:
                inventory = evalsetup.read_manifest_inventory(source_root, name)
            except evalsetup.SetupError as exc:
                warnings.append(f"{name}: {exc}")
                entry["manifest"] = {"found": True, "parse_error": str(exc)}
            else:
                items = [classify_item(item, name, source, wired_commands, env) for item in inventory["items"]]
                entry["manifest"] = {
                    "found": True,
                    "parse_error": None,
                    "schema": inventory["schema"],
                    "evaluation_status": inventory["evaluation_status"],
                    "wizard": inventory["wizard"],
                    "doctor": inventory["doctor"],
                    "artifacts": inventory["artifacts"],
                    "items": items,
                    "dependencies": inventory["dependencies"],
                }
                if inventory["evaluation_status"] == "missing":
                    warnings.append(f"{name}: evaluation catalog missing (schema 1)")
        plugins_out.append(entry)

    result = {"schema": SCHEMA_DISCOVER, "source": source, "plugins": plugins_out, "warnings": warnings}
    print(json.dumps(result, indent=2))
    record_run_section(home, args.run, "discover", result)
    return 0


# ---------- hooks plan / apply ----------

def smoke_test_command(resolved_command: str, event: str, home: Path) -> dict[str, Any]:
    if event in STDIN_TOOL_CALL_EVENTS:
        stdin_payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}})
        stdin_kind = "tool-call"
    else:
        stdin_payload = ""
        stdin_kind = "empty"
    env = dict(os.environ)
    env["HOME"] = str(home)
    try:
        completed = subprocess.run(
            ["sh", "-c", resolved_command],
            input=stdin_payload,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ran": False, "exit_code": None, "passed": False, "stdin_kind": stdin_kind, "error": str(exc)}
    return {"ran": True, "exit_code": completed.returncode, "passed": completed.returncode == 0, "stdin_kind": stdin_kind}


def hooks_plan_command(args: argparse.Namespace) -> int:
    home = resolve_cli_path(args.home)
    project = resolve_cli_path(args.project)
    try:
        source = discover_source(home, project)
    except OrchestratorError as exc:
        print(json.dumps({"schema": SCHEMA_HOOKS_PLAN, "error": str(exc)}, indent=2))
        return 2

    source_root = Path(source["root"])
    manifest_path = source_root / args.plugin / "setup" / "manifest.json"
    if not manifest_path.is_file():
        print(json.dumps({"schema": SCHEMA_HOOKS_PLAN, "error": f"no manifest for plugin {args.plugin!r}"}, indent=2))
        return 2
    try:
        inventory = evalsetup.read_manifest_inventory(source_root, args.plugin)
    except evalsetup.SetupError as exc:
        print(json.dumps({"schema": SCHEMA_HOOKS_PLAN, "error": str(exc)}, indent=2))
        return 2
    item = next((i for i in inventory["items"] if i.get("id") == args.item), None)
    if item is None:
        print(json.dumps({"schema": SCHEMA_HOOKS_PLAN, "error": f"no item {args.item!r} in {args.plugin} manifest"}, indent=2))
        return 2

    absolute_command = item["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(source_root / args.plugin))
    root = portable_root(source, args.plugin)
    if root is not None:
        resolved_command = item["command"].replace("${CLAUDE_PLUGIN_ROOT}", root)
        portability = "portable"
    else:
        resolved_command = absolute_command
        portability = "dev-repo"

    smoke = smoke_test_command(resolved_command, item["event"], home)
    result = {
        "schema": SCHEMA_HOOKS_PLAN,
        "plugin": args.plugin,
        "item": args.item,
        "event": item["event"],
        "matcher": item.get("matcher"),
        "portability": portability,
        "resolved_command": resolved_command,
        "smoke_test": smoke,
    }
    print(json.dumps(result, indent=2))
    record_run_section(home, args.run, f"hooks_plan:{args.plugin}:{args.item}", result)
    return 0 if smoke["passed"] else 1


def hooks_apply_command(args: argparse.Namespace) -> int:
    project = resolve_cli_path(args.project)
    home = resolve_cli_path(args.home)
    plan_path = resolve_cli_path(args.plan)
    try:
        raw_plans = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA_HOOKS_APPLY, "error": f"unreadable plan file: {exc}"}, indent=2))
        return 2
    plans = raw_plans if isinstance(raw_plans, list) else [raw_plans]

    settings_path = project / ".claude" / "settings.json"
    settings = load_json_or(settings_path, {})
    if not isinstance(settings, dict):
        settings = {}
    if not isinstance(settings.get("hooks"), dict):
        settings["hooks"] = {}

    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for plan in plans:
        event = plan["event"]
        matcher = plan.get("matcher")
        command = plan["resolved_command"]
        bucket = settings["hooks"].setdefault(event, [])
        already_wired = any(
            isinstance(group, dict)
            and group.get("matcher") == matcher
            and any(isinstance(h, dict) and h.get("command") == command for h in group.get("hooks", []) if isinstance(group.get("hooks"), list))
            for group in bucket
        )
        if already_wired:
            skipped.append({"plugin": plan.get("plugin"), "item": plan.get("item"), "reason": "already wired"})
            continue
        entry: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
        if matcher is not None:
            entry = {"matcher": matcher, "hooks": entry["hooks"]}
        bucket.append(entry)
        applied.append({"plugin": plan.get("plugin"), "item": plan.get("item"), "event": event, "matcher": matcher})

    if applied:
        # Only touch the file when something changed: a hand-formatted settings.json must not be
        # reflowed by a run that wired nothing.
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    result = {"schema": SCHEMA_HOOKS_APPLY, "settings_path": str(settings_path), "applied": applied, "skipped": skipped}
    print(json.dumps(result, indent=2))
    record_run_section(home, args.run, "hooks_apply", result)
    return 0


# ---------- artifacts snapshot ----------

def resolve_artifact_path(path_template: str, project: Path, home: Path, vault: Path | None) -> Path | None:
    for placeholder, base in (("<project>", project), ("<home>", home), ("<vault>", vault)):
        if path_template == placeholder or path_template.startswith(placeholder + "/"):
            if base is None:
                return None
            remainder = path_template[len(placeholder):].lstrip("/")
            return base / remainder if remainder else base
    return None


def artifact_exists(path: Path, kind: str) -> bool:
    if kind == "glob":
        parent = path.parent
        return parent.is_dir() and any(parent.glob(path.name))
    return path.exists() or path.is_symlink()


def artifacts_snapshot_command(args: argparse.Namespace) -> int:
    home = resolve_cli_path(args.home)
    project = resolve_cli_path(args.project)
    try:
        source = discover_source(home, project)
    except OrchestratorError as exc:
        print(json.dumps({"schema": SCHEMA_ARTIFACTS_SNAPSHOT, "error": str(exc)}, indent=2))
        return 2
    source_root = Path(source["root"])

    vault_paths, plugin_absent = resolve_vault_paths_for(source_root)
    vault = Path(vault_paths[0]) if len(vault_paths) == 1 else None
    vault_status = vault_resolution_status(vault_paths, plugin_absent)

    plugin_names = args.plugin or [p.name for p in discover_plugins(source_root)]
    rows: list[dict[str, Any]] = []
    for plugin_name in plugin_names:
        manifest_path = source_root / plugin_name / "setup" / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            inventory = evalsetup.read_manifest_inventory(source_root, plugin_name)
        except evalsetup.SetupError:
            continue
        for artifact in inventory["artifacts"]:
            resolved = resolve_artifact_path(artifact["path"], project, home, vault)
            rows.append({
                "plugin": plugin_name,
                "id": artifact["id"],
                "path": artifact["path"],
                "resolved_path": str(resolved) if resolved else None,
                "vault_status": vault_status if artifact["path"].startswith("<vault>") else None,
                "exists": bool(resolved and artifact_exists(resolved, artifact["kind"])),
            })

    phase = "after" if args.after else "before"
    result = {"schema": SCHEMA_ARTIFACTS_SNAPSHOT, "phase": phase, "rows": rows}
    print(json.dumps(result, indent=2))
    record_run_section(home, args.run, f"artifacts_{phase}", result)
    return 0


# ---------- install-skill-map ----------

def install_skill_map_command(args: argparse.Namespace) -> int:
    home = resolve_cli_path(args.home)
    source = resolve_cli_path(args.source)
    dest_dir = home / ".claude" / "context-manager"
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    for name in ("skill-map.static.json", "skill-map.indexes.json"):
        src = source / "generated" / name
        if src.is_file():
            shutil.copy2(src, dest_dir / name)
            copied.append(name)
        else:
            missing.append(name)

    builder = source / "rhize-context-manager" / "scripts" / "build_local_skill_map.py"
    if not builder.is_file():
        overlay_status = "local overlay unavailable in installed mode"
    else:
        completed = subprocess.run(
            [sys.executable, str(builder)],
            cwd=source,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "HOME": str(home)},
        )
        if completed.returncode == 0:
            overlay_status = "local overlay built"
        else:
            overlay_status = f"local overlay build failed: {completed.stderr.strip()[:200]}"

    result = {
        "schema": SCHEMA_INSTALL_SKILL_MAP,
        "dest": str(dest_dir),
        "copied": copied,
        "missing": missing,
        "overlay_status": overlay_status,
    }
    print(json.dumps(result, indent=2))
    record_run_section(home, args.run, "install_skill_map", result)
    return 0


# ---------- report ----------

def escape_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "(none)"
    header = " | ".join(columns)
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(" | ".join(escape_cell(row.get(column)) for column in columns))
    return "\n".join(lines)


def display_home_relative(path: str | None, home: Path) -> str:
    if not path:
        return ""
    try:
        return "~/" + str(Path(path).relative_to(home))
    except ValueError:
        return path


def report_record_command(args: argparse.Namespace) -> int:
    home = resolve_cli_path(args.home)
    if args.data == "-":
        payload = json.loads(sys.stdin.read())
    else:
        payload = json.loads(resolve_cli_path(args.data).read_text(encoding="utf-8"))
    record_run_section(home, args.run, args.section, payload)
    print(json.dumps({"status": "recorded", "run": args.run, "section": args.section}, indent=2))
    return 0


def report_render_command(args: argparse.Namespace) -> int:
    home = resolve_cli_path(args.home)
    path = run_state_path(home, args.run)
    if not path.is_file():
        print(f"error: no run state found for run {args.run!r} at {path}", file=sys.stderr)
        return 2
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: run state at {path} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    sections: list[tuple[str, str]] = []

    discover = state.get("discover")
    if isinstance(discover, dict):
        plugin_rows = [
            {
                "plugin": plugin.get("name"),
                "enabled": plugin.get("enabled"),
                "clone_version": plugin.get("clone_version"),
                "installed_version": plugin.get("installed_version"),
                "clone_ahead_of_installed": plugin.get("clone_ahead_of_installed"),
            }
            for plugin in discover.get("plugins", [])
        ]
        sections.append(("Discovery", render_table(
            plugin_rows, ["plugin", "enabled", "clone_version", "installed_version", "clone_ahead_of_installed"],
        )))

        hook_rows = [
            {
                "plugin": plugin.get("name"), "item": item.get("id"), "tier": item.get("tier"),
                "event": item.get("event"), "matcher": item.get("matcher"),
                "status": (
                    f"{item.get('status')} — {item['migration_hint']}"
                    if item.get("migration_hint") else item.get("status")
                ),
            }
            for plugin in discover.get("plugins", [])
            for item in (plugin.get("manifest") or {}).get("items", []) if isinstance(plugin.get("manifest"), dict)
        ]
        if hook_rows:
            sections.append(("Hooks", render_table(hook_rows, ["plugin", "item", "tier", "event", "matcher", "status"])))

    for key, label in (("dependency_check", "Dependencies"), ("evaluations", "Evaluations"), ("version_control", "Version control")):
        section = state.get(key)
        rows = section.get("rows") if isinstance(section, dict) else section if isinstance(section, list) else None
        if rows:
            columns = (section.get("columns") if isinstance(section, dict) else None) or list(rows[0].keys())
            sections.append((label, render_table(rows, columns)))

    for key, label in (("artifacts_before", "Artifacts (before)"), ("artifacts_after", "Artifacts (after)")):
        section = state.get(key)
        rows = section.get("rows") if isinstance(section, dict) else None
        if rows:
            display_rows = [{**row, "path": display_home_relative(row.get("resolved_path") or row.get("path"), home)} for row in rows]
            sections.append((label, render_table(display_rows, ["plugin", "id", "path", "exists", "vault_status"])))

    install_skill_map = state.get("install_skill_map")
    if isinstance(install_skill_map, dict):
        sections.append(("Skill map install", render_table(
            [{"copied": ", ".join(install_skill_map.get("copied", [])) or "(none)",
              "missing": ", ".join(install_skill_map.get("missing", [])) or "(none)",
              "overlay": install_skill_map.get("overlay_status")}],
            ["copied", "missing", "overlay"],
        )))

    if not sections:
        print("(no sections recorded for this run)")
        return 0
    for label, table in sections:
        print(f"## {label}")
        print(table)
        print()
    return 0


# ---------- argparse wiring ----------

def add_home_project_args(parser: argparse.ArgumentParser, *, project: bool = True) -> None:
    parser.add_argument("--home", type=Path, default=Path.home())
    if project:
        parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run", help="run id to persist this subcommand's output under ~/.rhize/setup/runs/<id>.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover")
    add_home_project_args(discover)
    discover.add_argument("--json", action="store_true")
    discover.set_defaults(handler=discover_command)

    hooks = sub.add_parser("hooks")
    hooks_sub = hooks.add_subparsers(dest="hooks_command", required=True)

    plan = hooks_sub.add_parser("plan")
    add_home_project_args(plan)
    plan.add_argument("--plugin", required=True)
    plan.add_argument("--item", required=True)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=hooks_plan_command)

    apply_ = hooks_sub.add_parser("apply")
    add_home_project_args(apply_)
    apply_.add_argument("--plan", required=True, help="path to a JSON hooks-plan object or array of them")
    apply_.set_defaults(handler=hooks_apply_command)

    artifacts = sub.add_parser("artifacts")
    artifacts_sub = artifacts.add_subparsers(dest="artifacts_command", required=True)

    snapshot = artifacts_sub.add_parser("snapshot")
    add_home_project_args(snapshot)
    phase = snapshot.add_mutually_exclusive_group(required=True)
    phase.add_argument("--before", action="store_true")
    phase.add_argument("--after", action="store_true")
    snapshot.add_argument("--plugin", action="append")
    snapshot.set_defaults(handler=artifacts_snapshot_command)

    install_skill_map = sub.add_parser("install-skill-map")
    add_home_project_args(install_skill_map, project=False)
    install_skill_map.add_argument("--source", type=Path, required=True)
    install_skill_map.set_defaults(handler=install_skill_map_command)

    report = sub.add_parser("report")
    report_sub = report.add_subparsers(dest="report_command")

    record = report_sub.add_parser("record")
    record.add_argument("--home", type=Path, default=Path.home())
    record.add_argument("--run", required=True)
    record.add_argument("--section", required=True)
    record.add_argument("--data", required=True, help="path to a JSON file, or '-' for stdin")
    record.set_defaults(handler=report_record_command)

    report.add_argument("--home", type=Path, default=Path.home())
    report.add_argument("--run")
    report.set_defaults(handler=report_render_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    if args.command == "report" and args.report_command == "record":
        return args.handler(args)
    if args.command == "report" and args.run is None:
        print("error: report requires --run <id> (or the 'record' subcommand)", file=sys.stderr)
        return 2
    try:
        return args.handler(args)
    except OrchestratorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
