#!/usr/bin/env python3
"""Read-only Codex plugin configuration/cache inventory; no runtime coverage claim.

Export JSON for `skill-forge audit --plugin-inventory FILE`. Python 3.11+ is
required for the standard TOML parser. Multiple cached versions are ambiguous,
not evidence that the newest one is loaded. No plugin code is executed.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def contained(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError(f"path escapes plugin install: {path}")
    return resolved


def skill_dirs(install: Path, manifest: dict) -> list[str]:
    declared = manifest.get("skills", "./skills/")
    paths = [declared] if isinstance(declared, str) else declared
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise ValueError("manifest skills must be a path or path array")
    result: set[str] = set()
    for value in paths:
        if Path(value).is_absolute() or ".." in Path(value).parts:
            raise ValueError("manifest skill paths must be relative and contained")
        path = install / value
        if not path.exists():
            if "skills" in manifest:
                raise ValueError(f"declared skills path missing: {value}")
            continue
        path = contained(path, install)
        if (path / "SKILL.md").is_file():
            contained(path / "SKILL.md", install)
            result.add(str(path))
        elif path.is_dir():
            for child in path.iterdir():
                if (child / "SKILL.md").is_file():
                    contained(child / "SKILL.md", install)
                    result.add(str(contained(child, install)))
    return sorted(result)


def inventory(home: Path, project: Path | None = None) -> dict:
    try:
        import tomllib
    except ImportError as exc:
        raise ValueError("host inventory requires Python 3.11+ (stdlib tomllib)") from exc
    config_path = home / ".codex/config.toml"
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    configured = config.get("plugins", {})
    if not isinstance(configured, dict):
        raise ValueError("Codex plugins configuration must be a table")
    notices = ["Configuration and cache presence do not verify host discovery or invocation. Claude telemetry does not cover Codex."]
    complete = True
    if project and (project / ".codex/config.toml").exists():
        notices.append("Project Codex config exists; trust/override activation is not verified. Export covers user config only.")
        complete = False
    cache = home / ".codex/plugins/cache"
    plugins = []
    for plugin_id, settings in sorted(configured.items()):
        row = {"pluginId": plugin_id, "host": "codex", "enabled": None, "status": "unknown", "runtimeVerified": False}
        plugins.append(row)
        try:
            if not isinstance(settings, dict) or not isinstance(settings.get("enabled"), bool):
                raise ValueError("missing explicit boolean enabled state")
            row["enabled"] = settings["enabled"]
            if not row["enabled"]:
                row["status"] = "disabled"
                continue
            plugin, market = plugin_id.rsplit("@", 1)
            if not plugin or not market or any(c in plugin + market for c in "/\\") or plugin in (".", "..") or market in (".", ".."):
                raise ValueError("invalid plugin@marketplace identity")
            root = cache / market / plugin
            versions = sorted(p for p in root.iterdir() if p.is_dir() and (p / ".codex-plugin/plugin.json").is_file()) if root.is_dir() else []
            if len(versions) != 1:
                raise ValueError(f"expected one installed manifest; found {len(versions)} cached versions")
            install = contained(versions[0], cache)
            manifest_path = contained(install / ".codex-plugin/plugin.json", install)
            manifest = json.loads(manifest_path.read_text())
            if not isinstance(manifest, dict) or manifest.get("name") != plugin:
                raise ValueError("manifest name does not match configured identity")
            row.update(status="installed", version=str(manifest.get("version", versions[0].name)),
                       installPath=str(install), skillDirs=skill_dirs(install, manifest),
                       capabilities={"skills": "skills" in manifest or (install / "skills").is_dir(),
                                     "commands": "commands" in manifest or (install / "commands").is_dir(),
                                     "hooks": "hooks" in manifest or (install / "hooks/hooks.json").is_file(),
                                     "mcp": "mcpServers" in manifest or (install / ".mcp.json").is_file()})
        except (OSError, ValueError, TypeError) as exc:
            row["reason"] = str(exc)
            complete = False
    return {"schemaVersion": 1, "kind": "skill-forge-host-inventory", "host": "codex",
            "generatedAt": datetime.now(timezone.utc).isoformat(), "complete": complete,
            "configPath": str(config_path), "plugins": plugins, "notices": notices}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        print(json.dumps(inventory(args.home, args.project), indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
