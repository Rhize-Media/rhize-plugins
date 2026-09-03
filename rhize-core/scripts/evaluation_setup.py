#!/usr/bin/env python3
"""Validate and initialize Rhize evaluation coverage and privacy-safe local capture."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import site
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIG_VERSION = "rhize-evaluation-config-v1"
RECEIPT_VERSION = "rhize-evaluation-receipt-v1"
CAPTURE_MODES = {"aggressive_local", "deterministic_only", "disabled"}
CONFIG_CAPTURE_MODES = CAPTURE_MODES | {"mixed"}
BASELINE_STATUSES = {"confirmed", "greenfield", "declined"}
TERMINAL_STATUSES = {"completed", "failed", "incomplete"}
UNAVAILABLE_REASONS = {"host_not_exposed", "not_measured", None}
DEPENDENCY_KINDS = {"plugin", "cli", "mcp", "data", "runtime", "platform"}

# Setup manifest schema 3 (hybrid-setup-wizard.md) — schema 2 keeps the exact
# four-plus-evaluations key set; schema 3 allows the same core keys plus the
# optional wizard/doctor/artifacts blocks. Schema 1 (inventory-only, no
# evaluation binding) is handled separately by read_manifest_inventory().
MANIFEST_SCHEMA1_KEYS = {"schema", "plugin", "items", "dependencies"}
MANIFEST_CORE_KEYS = {"schema", "plugin", "items", "dependencies", "evaluations"}
MANIFEST_V3_OPTIONAL_KEYS = {"wizard", "doctor", "artifacts"}
WIZARD_KEYS = {"skill", "purpose", "when", "args"}
WIZARD_REQUIRED_KEYS = {"skill", "purpose", "when"}
WIZARD_WHEN_VALUES = {"optional", "recommended", "required"}
DOCTOR_KEYS = {"kind", "value"}
DOCTOR_KINDS = {"skill", "shell"}
ARTIFACT_KEYS = {
    "id", "path", "kind", "purpose", "viewer", "lifetime",
    "confidentiality", "source", "tracked", "optional",
}
ARTIFACT_KINDS = {"file", "directory", "glob"}
ARTIFACT_LIFETIMES = {"persistent", "per-run", "append-only", "regenerated"}
ARTIFACT_CONFIDENTIALITY_LEVELS = {"none", "config", "personal", "client", "secret"}
ARTIFACT_SOURCES = {"authored", "derived", "transcript-derived"}
ARTIFACT_TRACKED_VALUES = {"project", "home", "ignored", "outside-repo"}
ARTIFACT_PLACEHOLDERS = ("<project>", "<home>", "<vault>")
SKILL_REF_RE = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")
METRIC_KEYS = {
    "correctness_pass", "verification_required", "verification_completed",
    "verification_passed", "routing_true_positives", "routing_false_positives",
    "routing_false_negatives", "tokens", "tokens_unavailable_reason", "latency_ms",
    "tool_calls", "tool_calls_unavailable_reason", "follow_up_reads", "corrections",
    "rework_events", "failures", "refusals",
}
TOKEN_KEYS = {"input", "output", "cache_read", "cache_write"}


class SetupError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"{label} is not readable JSON: {exc}") from exc


def exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise SetupError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def private_write(path: Path, content: str) -> None:
    private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def append_private_json(path: Path, row: dict[str, Any]) -> None:
    private_directory(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def safe_repo_path(repo_root: Path, relative: str, label: str, *, directory: bool = False) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SetupError(f"{label} must be a repository-relative path without traversal")
    try:
        resolved_root = repo_root.resolve(strict=True)
        resolved = (resolved_root / candidate).resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise SetupError(f"{label} escapes or does not exist under the repository root") from exc
    if directory and not resolved.is_dir():
        raise SetupError(f"{label} must resolve to a directory")
    if not directory and not resolved.is_file():
        raise SetupError(f"{label} must resolve to a file")
    return resolved


def validate_suite(repo_root: Path, suite: Any, label: str) -> dict[str, Any]:
    required = {"id", "kind", "path", "args", "cwd", "network", "cost", "timeout_seconds", "automatic"}
    optional = {"requires"}
    if not isinstance(suite, dict) or not required <= set(suite) or set(suite) - required - optional:
        raise SetupError(f"{label} has invalid fields")
    if suite["kind"] != "python" or suite["network"] != "none" or suite["cost"] != "free":
        raise SetupError(f"{label} must be a free, offline Python suite")
    if not isinstance(suite["args"], list) or not all(isinstance(item, str) for item in suite["args"]):
        raise SetupError(f"{label}.args must be a string array")
    timeout = suite["timeout_seconds"]
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 600:
        raise SetupError(f"{label}.timeout_seconds must be between 1 and 600")
    if not isinstance(suite["automatic"], bool):
        raise SetupError(f"{label}.automatic must be boolean")
    if "requires" in suite and (
        not isinstance(suite["requires"], list)
        or not all(isinstance(item, str) and item.strip() for item in suite["requires"])
    ):
        raise SetupError(f"{label}.requires must be a non-empty string array")
    safe_repo_path(repo_root, suite["path"], f"{label}.path")
    safe_repo_path(repo_root, suite["cwd"], f"{label}.cwd", directory=True)
    return suite


def command_has_description_frontmatter(text: str) -> bool:
    """True if `text` opens with a `---`-delimited frontmatter block containing a
    `description:` key -- the contract that makes a plugin command Skill-tool-invocable
    with `args` substituted into `$ARGUMENTS` (verified empirically 2026-09-02)."""
    stripped = text.lstrip("﻿")
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    body: list[str] = []
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        body.append(line)
    if not closed:
        return False
    return any(re.match(r"^description\s*:", line) for line in body)


def resolve_skill_command_path(repo_root: Path, skill: Any, label: str) -> Path:
    """Resolve a `plugin:command` reference to its command file and confirm it exists
    and carries the `description:` frontmatter the Skill tool requires."""
    if not isinstance(skill, str) or not SKILL_REF_RE.match(skill):
        raise SetupError(f"{label} must be a 'plugin:command' reference")
    plugin_dir, command_name = skill.split(":", 1)
    command_path = repo_root / plugin_dir / "commands" / f"{command_name}.md"
    if not command_path.is_file():
        raise SetupError(f"{label} references a command that does not exist: {command_path}")
    try:
        text = command_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"{label} command file is not readable: {exc}") from exc
    if not command_has_description_frontmatter(text):
        raise SetupError(
            f"{label} command {command_path} must start with frontmatter containing "
            "'description' to be Skill-tool-invocable"
        )
    return command_path


def validate_wizard(repo_root: Path, wizard: Any, label: str) -> dict[str, Any]:
    if (
        not isinstance(wizard, dict)
        or not WIZARD_REQUIRED_KEYS <= set(wizard)
        or set(wizard) - WIZARD_KEYS
    ):
        raise SetupError(f"{label} must contain {sorted(WIZARD_REQUIRED_KEYS)} and only optionally 'args'")
    resolve_skill_command_path(repo_root, wizard["skill"], f"{label}.skill")
    if not isinstance(wizard["purpose"], str) or not wizard["purpose"].strip():
        raise SetupError(f"{label}.purpose must be a non-empty string")
    if wizard["when"] not in WIZARD_WHEN_VALUES:
        raise SetupError(f"{label}.when must be one of {sorted(WIZARD_WHEN_VALUES)}")
    if "args" in wizard:
        args = wizard["args"]
        if not isinstance(args, list) or not args or not all(isinstance(item, str) and item for item in args):
            raise SetupError(f"{label}.args must be a non-empty string array")
    return wizard


def validate_doctor(doctor: Any, label: str) -> dict[str, Any]:
    doctor = exact_keys(doctor, DOCTOR_KEYS, label)
    if doctor["kind"] not in DOCTOR_KINDS:
        raise SetupError(f"{label}.kind must be one of {sorted(DOCTOR_KINDS)}")
    if not isinstance(doctor["value"], str) or not doctor["value"].strip():
        raise SetupError(f"{label}.value must be a non-empty string")
    return doctor


def validate_artifact_path(path: Any, label: str) -> str:
    if not isinstance(path, str) or not path:
        raise SetupError(f"{label}.path must be a non-empty string")
    if path.startswith("/") or path.startswith("~") or "\\" in path:
        raise SetupError(f"{label}.path must not be an absolute path")
    placeholder = next(
        (p for p in ARTIFACT_PLACEHOLDERS if path == p or path.startswith(p + "/")), None,
    )
    if placeholder is None:
        raise SetupError(f"{label}.path must start with <project>, <home>, or <vault>")
    remainder = path[len(placeholder):]
    if "<" in remainder or ">" in remainder:
        raise SetupError(f"{label}.path must not contain additional placeholders")
    segments = [segment for segment in remainder.split("/") if segment]
    if ".." in segments:
        raise SetupError(f"{label}.path must not contain '..'")
    return path


def validate_artifact(artifact: Any, label: str) -> dict[str, Any]:
    artifact = exact_keys(artifact, ARTIFACT_KEYS, label)
    if not isinstance(artifact["id"], str) or not re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", artifact["id"]):
        raise SetupError(f"{label}.id must be a kebab-case string")
    validate_artifact_path(artifact["path"], label)
    if artifact["kind"] not in ARTIFACT_KINDS:
        raise SetupError(f"{label}.kind must be one of {sorted(ARTIFACT_KINDS)}")
    for field in ("purpose", "viewer"):
        if not isinstance(artifact[field], str) or not artifact[field].strip():
            raise SetupError(f"{label}.{field} must be a non-empty string")
    if artifact["lifetime"] not in ARTIFACT_LIFETIMES:
        raise SetupError(f"{label}.lifetime must be one of {sorted(ARTIFACT_LIFETIMES)}")
    if artifact["confidentiality"] not in ARTIFACT_CONFIDENTIALITY_LEVELS:
        raise SetupError(f"{label}.confidentiality must be one of {sorted(ARTIFACT_CONFIDENTIALITY_LEVELS)}")
    if artifact["source"] not in ARTIFACT_SOURCES:
        raise SetupError(f"{label}.source must be one of {sorted(ARTIFACT_SOURCES)}")
    if artifact["tracked"] not in ARTIFACT_TRACKED_VALUES:
        raise SetupError(f"{label}.tracked must be one of {sorted(ARTIFACT_TRACKED_VALUES)}")
    if not isinstance(artifact["optional"], bool):
        raise SetupError(f"{label}.optional must be boolean")
    return artifact


def validate_artifacts(artifacts: Any, label: str) -> list[dict[str, Any]]:
    # An empty array is valid on its own (a plugin declaring "I write nothing
    # personal" — e.g. seo-aeo-geo, env vars only). validate_manifest enforces
    # non-empty separately, only when the manifest also declares a wizard.
    if not isinstance(artifacts, list):
        raise SetupError(f"{label} must be an array")
    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        validated_artifact = validate_artifact(artifact, f"{label}[{index}]")
        if validated_artifact["id"] in seen_ids:
            raise SetupError(f"{label} ids must be unique, duplicate: {validated_artifact['id']}")
        seen_ids.add(validated_artifact["id"])
        validated.append(validated_artifact)
    return validated


def validate_manifest(repo_root: Path, component_id: str) -> dict[str, Any]:
    """Strict validator: requires schema 2 or 3 with a valid evaluation binding.
    Schema 1 (inventory-only, no evaluation binding) is read separately by
    read_manifest_inventory() -- it never satisfies this function's coverage gate."""
    manifest_path = repo_root / component_id / "setup" / "manifest.json"
    manifest = load_json(manifest_path, f"{component_id} setup manifest")
    if not isinstance(manifest, dict) or manifest.get("plugin") != component_id:
        raise SetupError(f"{component_id} setup manifest plugin mismatch")
    schema = manifest.get("schema")
    if schema not in (2, 3):
        raise SetupError(f"{component_id} setup manifest has no evaluation catalog binding (schema 2 or 3 required)")
    keys = set(manifest)
    if schema == 2:
        exact_keys(manifest, MANIFEST_CORE_KEYS, f"{component_id} setup manifest")
    elif not MANIFEST_CORE_KEYS <= keys or keys - MANIFEST_CORE_KEYS - MANIFEST_V3_OPTIONAL_KEYS:
        raise SetupError(
            f"{component_id} setup manifest must contain {sorted(MANIFEST_CORE_KEYS)} "
            f"and only optionally {sorted(MANIFEST_V3_OPTIONAL_KEYS)}"
        )
    if not isinstance(manifest["items"], list) or not isinstance(manifest["dependencies"], list):
        raise SetupError(f"{component_id} setup manifest arrays are invalid")
    for index, dependency in enumerate(manifest["dependencies"]):
        if not isinstance(dependency, dict) or dependency.get("kind") not in DEPENDENCY_KINDS:
            raise SetupError(f"{component_id} dependency {index} has an unknown kind")
    evaluations = exact_keys(manifest["evaluations"], {"catalog", "component"}, f"{component_id}.evaluations")
    if evaluations != {"catalog": "rhize-evaluations-v1", "component": component_id}:
        raise SetupError(f"{component_id} evaluation binding is invalid")
    if schema == 3:
        if "wizard" in manifest:
            validate_wizard(repo_root, manifest["wizard"], f"{component_id}.wizard")
            if not manifest.get("artifacts"):
                raise SetupError(f"{component_id} declares a wizard but no artifacts")
        if "doctor" in manifest:
            validate_doctor(manifest["doctor"], f"{component_id}.doctor")
        if "artifacts" in manifest:
            validate_artifacts(manifest["artifacts"], f"{component_id}.artifacts")
    return manifest


def read_manifest_inventory(repo_root: Path, component_id: str) -> dict[str, Any]:
    """Lenient manifest read for hook/dependency inventory purposes (the
    setup_orchestrator.py `discover` subcommand). Accepts schema 1 -- reported
    with evaluation_status "missing" and never counted as coverage -- alongside
    schema 2 and 3, which are delegated to the strict validate_manifest() above."""
    manifest_path = repo_root / component_id / "setup" / "manifest.json"
    manifest = load_json(manifest_path, f"{component_id} setup manifest")
    if not isinstance(manifest, dict) or manifest.get("plugin") != component_id:
        raise SetupError(f"{component_id} setup manifest plugin mismatch")
    schema = manifest.get("schema")
    if schema == 1:
        exact_keys(manifest, MANIFEST_SCHEMA1_KEYS, f"{component_id} setup manifest")
        if not isinstance(manifest["items"], list) or not isinstance(manifest["dependencies"], list):
            raise SetupError(f"{component_id} setup manifest arrays are invalid")
        for index, dependency in enumerate(manifest["dependencies"]):
            if not isinstance(dependency, dict) or dependency.get("kind") not in DEPENDENCY_KINDS:
                raise SetupError(f"{component_id} dependency {index} has an unknown kind")
        return {
            "schema": 1,
            "plugin": component_id,
            "items": manifest["items"],
            "dependencies": manifest["dependencies"],
            "wizard": None,
            "doctor": None,
            "artifacts": [],
            "evaluation_status": "missing",
        }
    if schema in (2, 3):
        validated = validate_manifest(repo_root, component_id)
        return {
            "schema": schema,
            "plugin": component_id,
            "items": validated["items"],
            "dependencies": validated["dependencies"],
            "wizard": validated.get("wizard"),
            "doctor": validated.get("doctor"),
            "artifacts": validated.get("artifacts", []),
            "evaluation_status": "bound",
        }
    raise SetupError(f"{component_id} setup manifest has an unsupported schema: {schema!r}")


def catalog_relative_path(repo_root: Path) -> Path:
    """Resolve the central evaluation catalog's repo-relative path.

    Prefers rhize-core's catalog when a `rhize-core` plugin directory exists under
    `repo_root` -- the ordinary case, and the only location for a fresh install.
    Otherwise falls back to this very file's own plugin directory (derived from where
    this copy of the script lives on disk, never from `repo_root`), so a pre-rhize-core
    rhize-ops-only install -- or this byte-identical fallback copy running before
    rhize-core is installed alongside it -- still finds its own catalog instead of one
    that does not exist yet (repo-shape R-B, Codex F6/F8)."""
    if (repo_root / "rhize-core").is_dir():
        return Path("rhize-core") / "setup" / "evaluation-catalog.json"
    own_plugin = Path(__file__).resolve().parents[1].name
    return Path(own_plugin) / "setup" / "evaluation-catalog.json"


def validate_catalog(repo_root: Path, catalog_path: Path | None = None) -> dict[str, Any]:
    path = catalog_path or repo_root / catalog_relative_path(repo_root)
    catalog = exact_keys(
        load_json(path, "evaluation catalog"),
        {"schema_version", "policy", "domains", "components"},
        "evaluation catalog",
    )
    if catalog["schema_version"] != "rhize-evaluations-v1":
        raise SetupError("unsupported evaluation catalog schema")
    policy = exact_keys(
        catalog["policy"],
        {"deterministic_release_gate", "matched_controlled_claim_gate", "natural_evidence_class", "controlled_repetitions", "capture_modes"},
        "evaluation catalog policy",
    )
    if policy["deterministic_release_gate"] is not True or policy["matched_controlled_claim_gate"] is not True:
        raise SetupError("release and claim gates must stay enabled")
    if policy["natural_evidence_class"] != "observational" or policy["controlled_repetitions"] != 3:
        raise SetupError("natural evidence or controlled repetition policy drifted")
    if set(policy["capture_modes"]) != CAPTURE_MODES:
        raise SetupError("capture modes drifted")

    components = catalog["components"]
    domains = catalog["domains"]
    if not isinstance(components, list) or not isinstance(domains, list):
        raise SetupError("catalog components and domains must be arrays")
    component_ids = [item.get("id") for item in components if isinstance(item, dict)]
    if len(component_ids) != len(components) or len(set(component_ids)) != len(component_ids):
        raise SetupError("component ids must be present and unique")
    domain_components: list[str] = []
    domain_ids: set[str] = set()
    domain_by_component: dict[str, str] = {}
    for domain in domains:
        exact_keys(domain, {"id", "title", "components"}, "catalog domain")
        if domain["id"] in domain_ids or not isinstance(domain["components"], list):
            raise SetupError("domain ids must be unique and components must be an array")
        domain_ids.add(domain["id"])
        domain_components.extend(domain["components"])
        domain_by_component.update({component_id: domain["id"] for component_id in domain["components"]})
    if sorted(domain_components) != sorted(component_ids) or len(domain_components) != len(set(domain_components)):
        raise SetupError("every component must appear in exactly one domain")

    plugin_skill_count = 0
    for component in components:
        exact_keys(component, {"id", "kind", "domain", "skills", "suites", "benchmarks"}, f"component {component.get('id')}")
        component_id = component["id"]
        if component["domain"] not in domain_ids or component["kind"] not in {"plugin", "package"}:
            raise SetupError(f"{component_id} domain or kind is invalid")
        if domain_by_component.get(component_id) != component["domain"]:
            raise SetupError(f"{component_id} domain disagrees with the domain inventory")
        if not isinstance(component["skills"], list) or len(component["skills"]) != len(set(component["skills"])):
            raise SetupError(f"{component_id} skills must be a unique array")
        if component["kind"] == "plugin":
            skill_root = repo_root / component_id / "skills"
            discovered = sorted(path.parent.name for path in skill_root.glob("*/SKILL.md"))
            if sorted(component["skills"]) != discovered:
                raise SetupError(f"{component_id} catalog skills do not match the published skill inventory")
            plugin_skill_count += len(discovered)
            validate_manifest(repo_root, component_id)
        elif component["skills"]:
            raise SetupError(f"package component {component_id} cannot claim plugin skills")
        if not isinstance(component["suites"], list) or not component["suites"]:
            raise SetupError(f"{component_id} must declare at least one suite")
        suite_ids = set()
        for index, suite in enumerate(component["suites"]):
            suite = validate_suite(repo_root, suite, f"{component_id}.suites[{index}]")
            if suite["id"] in suite_ids:
                raise SetupError(f"{component_id} suite ids must be unique")
            suite_ids.add(suite["id"])
        if not isinstance(component["benchmarks"], list) or not component["benchmarks"]:
            raise SetupError(f"{component_id} must declare at least one benchmark")
        benchmark_ids = set()
        for index, benchmark in enumerate(component["benchmarks"]):
            exact_keys(benchmark, {"id", "protocol", "arm_a", "arm_b", "natural_capture_eligible"}, f"{component_id}.benchmarks[{index}]")
            if benchmark["id"] in benchmark_ids or not benchmark["arm_a"] or not benchmark["arm_b"]:
                raise SetupError(f"{component_id} benchmark ids and arms must be explicit")
            benchmark_ids.add(benchmark["id"])
            safe_repo_path(repo_root, benchmark["protocol"], f"{component_id}.benchmark.protocol")
            if not isinstance(benchmark["natural_capture_eligible"], bool):
                raise SetupError(f"{component_id} benchmark capture eligibility must be boolean")
    if plugin_skill_count != 56:
        raise SetupError(f"published plugin coverage must total 56 skills, found {plugin_skill_count}")
    return catalog


def component_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {component["id"]: component for component in catalog["components"]}


def parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise SetupError(f"{label} must be an ISO-8601 UTC timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SetupError(f"{label} must be an ISO-8601 UTC timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise SetupError(f"{label} must be an ISO-8601 UTC timestamp")
    return timestamp


def validate_config(raw: Any) -> dict[str, Any]:
    config = exact_keys(raw, {"schema_version", "capture_mode", "updated_at", "plugins"}, "evaluation config")
    if config["schema_version"] != CONFIG_VERSION or config["capture_mode"] not in CONFIG_CAPTURE_MODES:
        raise SetupError("evaluation config has an unsupported version or capture mode")
    parse_timestamp(config["updated_at"], "evaluation config updated_at")
    if not isinstance(config["plugins"], dict):
        raise SetupError("evaluation config plugins must be an object")
    for component_id, state in config["plugins"].items():
        state = exact_keys(
            state,
            {"domain", "skills", "baseline", "benchmarks", "suites", "capture_mode"},
            f"evaluation config plugin {component_id}",
        )
        if state["capture_mode"] not in CAPTURE_MODES:
            raise SetupError(f"evaluation config plugin {component_id} has an invalid capture mode")
        if not isinstance(state["skills"], int) or isinstance(state["skills"], bool) or state["skills"] < 0:
            raise SetupError(f"evaluation config plugin {component_id} has an invalid skill count")
        if not isinstance(state["benchmarks"], list) or not all(isinstance(item, str) for item in state["benchmarks"]):
            raise SetupError(f"evaluation config plugin {component_id} has invalid benchmarks")
        if not isinstance(state["suites"], list):
            raise SetupError(f"evaluation config plugin {component_id} has invalid suite state")
        baseline = exact_keys(
            state["baseline"],
            {"status", "baseline_id", "label", "version", "validation_method"},
            f"evaluation config plugin {component_id} baseline",
        )
        if baseline["status"] not in BASELINE_STATUSES | {"unconfirmed"}:
            raise SetupError(f"evaluation config plugin {component_id} has an invalid baseline status")
        identity = (baseline["label"], baseline["version"], baseline["validation_method"])
        if baseline["status"] == "confirmed":
            if not all(isinstance(item, str) and item.strip() for item in identity):
                raise SetupError(f"evaluation config plugin {component_id} confirmed baseline is incomplete")
        elif any(item is not None for item in identity):
            raise SetupError(f"evaluation config plugin {component_id} has invented baseline identity")
        if baseline["baseline_id"] is not None:
            try:
                uuid.UUID(baseline["baseline_id"])
            except (AttributeError, TypeError, ValueError) as exc:
                raise SetupError(f"evaluation config plugin {component_id} baseline_id is invalid") from exc
    return config


def load_decisions(path: Path | None, selected: set[str]) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    document = exact_keys(load_json(path, "baseline decisions"), {"plugins"}, "baseline decisions")
    if not isinstance(document["plugins"], dict):
        raise SetupError("baseline decisions.plugins must be an object")
    decisions = {}
    for plugin, raw in document["plugins"].items():
        if plugin not in selected:
            raise SetupError(f"baseline decision targets unselected component {plugin}")
        decision = exact_keys(raw, {"status", "label", "version", "validation_method"}, f"baseline decision {plugin}")
        if not all(isinstance(decision[field], str) for field in decision):
            raise SetupError(f"baseline decision {plugin} fields must be strings")
        if decision["status"] not in BASELINE_STATUSES:
            raise SetupError(f"baseline decision {plugin} has invalid status")
        if decision["status"] == "confirmed" and not all(
            isinstance(decision[field], str) and decision[field].strip()
            for field in ("label", "version", "validation_method")
        ):
            raise SetupError(f"confirmed baseline {plugin} requires label, version, and validation_method")
        if decision["status"] != "confirmed" and any(decision[field] for field in ("label", "version", "validation_method")):
            raise SetupError(f"{decision['status']} baseline {plugin} cannot contain invented identity fields")
        decisions[plugin] = decision
    return decisions


def isolated_environment(home: Path) -> dict[str, str]:
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if os.environ.get(key)}
    environment.update({"HOME": str(home), "TMPDIR": str(home), "NO_COLOR": "1"})
    user_site = Path(site.getusersitepackages())
    if user_site.is_dir():
        environment["PYTHONPATH"] = str(user_site)
    return environment


def run_suite(repo_root: Path, state_root: Path, suite: dict[str, Any]) -> dict[str, Any]:
    if not suite["automatic"]:
        return {"id": suite["id"], "status": "blocked", "reason": "explicit_input_required"}
    runner = safe_repo_path(repo_root, suite["path"], f"suite {suite['id']} path")
    cwd = safe_repo_path(repo_root, suite["cwd"], f"suite {suite['id']} cwd", directory=True)
    runtime_home = state_root / "runtime-home"
    private_directory(runtime_home)
    started = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            [sys.executable, str(runner), *suite["args"]],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=suite["timeout_seconds"],
            env=isolated_environment(runtime_home),
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
        return {"id": suite["id"], "status": "fail", "reason": "timeout", "latency_ms": elapsed_ms}
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    return {
        "id": suite["id"],
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "latency_ms": elapsed_ms,
    }


def baseline_state(existing: dict[str, Any] | None, decision: dict[str, str] | None) -> dict[str, Any]:
    if decision is None:
        return existing or {"status": "unconfirmed", "baseline_id": None, "label": None, "version": None, "validation_method": None}
    candidate = {
        "status": decision["status"],
        "label": decision["label"] or None,
        "version": decision["version"] or None,
        "validation_method": decision["validation_method"] or None,
    }
    if existing and all(existing.get(key) == value for key, value in candidate.items()):
        candidate["baseline_id"] = existing.get("baseline_id")
    else:
        candidate["baseline_id"] = str(uuid.uuid4())
    return candidate


def ensure_hmac_key(state_root: Path) -> Path:
    key_path = state_root / "hmac.key"
    if not key_path.exists():
        private_directory(state_root)
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(secrets.token_bytes(32))
            handle.flush()
            os.fsync(handle.fileno())
    key_path.chmod(0o600)
    return key_path


def setup(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve(strict=True)
    catalog = validate_catalog(repo_root, args.catalog)
    components = component_map(catalog)
    selected = set(args.plugin or components)
    unknown = selected - set(components)
    if unknown:
        raise SetupError(f"unknown components: {', '.join(sorted(unknown))}")
    decisions = load_decisions(args.baseline_decisions, selected)
    private_directory(args.state_root)
    config_path = args.state_root / "config.json"
    existing = validate_config(load_json(config_path, "existing evaluation config")) if config_path.exists() else None
    existing_plugins = existing["plugins"] if existing else {}
    plugin_states = dict(existing_plugins)
    for component_id in sorted(selected):
        component = components[component_id]
        previous = existing_plugins.get(component_id, {})
        suites = [run_suite(repo_root, args.state_root, suite) for suite in component["suites"]] if args.run_free_smoke else [
            {"id": suite["id"], "status": "blocked" if not suite["automatic"] else "not_run"}
            for suite in component["suites"]
        ]
        plugin_states[component_id] = {
            "domain": component["domain"],
            "skills": len(component["skills"]),
            "baseline": baseline_state(previous.get("baseline"), decisions.get(component_id)),
            "benchmarks": [benchmark["id"] for benchmark in component["benchmarks"]],
            "suites": suites,
            "capture_mode": args.capture_mode,
        }
    configured_modes = {state.get("capture_mode") for state in plugin_states.values()}
    effective_capture_mode = configured_modes.pop() if len(configured_modes) == 1 else "mixed"
    config = {
        "schema_version": CONFIG_VERSION,
        "capture_mode": effective_capture_mode,
        "updated_at": now(),
        "plugins": plugin_states,
    }
    private_write(config_path, json.dumps(config, indent=2, sort_keys=True) + "\n")
    if args.capture_mode == "aggressive_local":
        ensure_hmac_key(args.state_root)
    summary = {
        "status": "configured",
        "state_root": str(args.state_root),
        "capture_mode": effective_capture_mode,
        "components": {
            component_id: {
                "domain": plugin_states[component_id]["domain"],
                "skills": plugin_states[component_id]["skills"],
                "baseline_status": plugin_states[component_id]["baseline"]["status"],
                "suite_statuses": {suite["id"]: suite["status"] for suite in plugin_states[component_id]["suites"]},
            }
            for component_id in sorted(selected)
        },
    }
    print(json.dumps(summary, indent=2))
    return 0 if all(
        suite["status"] not in {"fail"}
        for component_id in selected
        for suite in plugin_states[component_id]["suites"]
    ) else 1


def receipt_path(state_root: Path, recorded_at: str) -> Path:
    return state_root / "receipts" / f"{recorded_at[:7]}.jsonl"


def receipt_rows(state_root: Path) -> list[dict[str, Any]]:
    rows = []
    receipt_root = state_root / "receipts"
    if not receipt_root.exists():
        return rows
    for path in sorted(receipt_root.glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SetupError(f"malformed receipt row {path.name}:{line_number}") from exc
            row = exact_keys(
                row,
                {"schema_version", "run_id", "plugin", "benchmark_id", "variant", "input_fingerprint", "status", "recorded_at", "metrics"},
                f"receipt row {path.name}:{line_number}",
            )
            if row["schema_version"] != RECEIPT_VERSION or row["variant"] not in {"A", "B"}:
                raise SetupError(f"receipt row {path.name}:{line_number} has an invalid version or variant")
            try:
                uuid.UUID(row["run_id"])
            except (AttributeError, TypeError, ValueError) as exc:
                raise SetupError(f"receipt row {path.name}:{line_number} has an invalid run_id") from exc
            if not isinstance(row["input_fingerprint"], str) or len(row["input_fingerprint"]) != 64:
                raise SetupError(f"receipt row {path.name}:{line_number} has an invalid input fingerprint")
            try:
                int(row["input_fingerprint"], 16)
            except ValueError as exc:
                raise SetupError(f"receipt row {path.name}:{line_number} has an invalid input fingerprint") from exc
            parse_timestamp(row["recorded_at"], f"receipt row {path.name}:{line_number} recorded_at")
            if row["status"] == "pending":
                if row["metrics"] is not None:
                    raise SetupError(f"pending receipt row {path.name}:{line_number} cannot contain metrics")
            elif row["status"] in TERMINAL_STATUSES:
                validate_metrics(row["metrics"])
            else:
                raise SetupError(f"receipt row {path.name}:{line_number} has an invalid status")
            rows.append(row)
    return rows


def reserve(args: argparse.Namespace) -> int:
    config = validate_config(load_json(args.state_root / "config.json", "evaluation config"))
    plugin = config.get("plugins", {}).get(args.plugin)
    if not isinstance(plugin, dict) or plugin.get("capture_mode") != "aggressive_local":
        raise SetupError("plugin capture is not enabled")
    if args.benchmark not in plugin.get("benchmarks", []):
        raise SetupError("benchmark is not configured for this plugin")
    key = ensure_hmac_key(args.state_root).read_bytes()
    fingerprint = hmac.new(key, args.input_file.read_bytes(), hashlib.sha256).hexdigest()
    recorded_at = now()
    row = {
        "schema_version": RECEIPT_VERSION,
        "run_id": str(uuid.uuid4()),
        "plugin": args.plugin,
        "benchmark_id": args.benchmark,
        "variant": args.variant,
        "input_fingerprint": fingerprint,
        "status": "pending",
        "recorded_at": recorded_at,
        "metrics": None,
    }
    append_private_json(receipt_path(args.state_root, recorded_at), row)
    print(json.dumps({"run_id": row["run_id"], "status": "pending", "input_fingerprint": fingerprint}, indent=2))
    return 0


def optional_nonnegative(value: Any, label: str, *, number: bool = False) -> None:
    expected = (int, float) if number else (int,)
    if value is not None and (not isinstance(value, expected) or isinstance(value, bool) or value < 0):
        raise SetupError(f"{label} must be null or nonnegative")


def validate_metrics(raw: Any) -> dict[str, Any]:
    metrics = exact_keys(raw, METRIC_KEYS, "metrics")
    if metrics["correctness_pass"] is not None and not isinstance(metrics["correctness_pass"], bool):
        raise SetupError("correctness_pass must be boolean or null")
    for key in METRIC_KEYS - {"correctness_pass", "tokens", "tokens_unavailable_reason", "tool_calls_unavailable_reason", "latency_ms"}:
        optional_nonnegative(metrics[key], key)
    optional_nonnegative(metrics["latency_ms"], "latency_ms", number=True)
    tokens = exact_keys(metrics["tokens"], TOKEN_KEYS, "metrics.tokens")
    for key, value in tokens.items():
        optional_nonnegative(value, f"tokens.{key}")
    tokens_missing = any(value is None for value in tokens.values())
    if metrics["tokens_unavailable_reason"] not in UNAVAILABLE_REASONS or tokens_missing != (metrics["tokens_unavailable_reason"] is not None):
        raise SetupError("tokens_unavailable_reason must exactly explain missing token counters")
    tool_missing = metrics["tool_calls"] is None
    if metrics["tool_calls_unavailable_reason"] not in UNAVAILABLE_REASONS or tool_missing != (metrics["tool_calls_unavailable_reason"] is not None):
        raise SetupError("tool_calls_unavailable_reason must exactly explain a missing counter")
    required = metrics["verification_required"]
    completed = metrics["verification_completed"]
    passed = metrics["verification_passed"]
    if any(value is not None for value in (required, completed, passed)) and not all(value is not None for value in (required, completed, passed)):
        raise SetupError("verification counters must be supplied together")
    if required is not None and not 0 <= passed <= completed <= required:
        raise SetupError("verification counters are inconsistent")
    return metrics


def finalize(args: argparse.Namespace) -> int:
    rows = receipt_rows(args.state_root)
    matches = [row for row in rows if row.get("run_id") == args.run_id]
    if not matches or matches[0].get("status") != "pending":
        raise SetupError("run_id has no pending reservation")
    if any(row.get("status") in TERMINAL_STATUSES for row in matches):
        raise SetupError("run_id is already terminal")
    pending = matches[0]
    metrics = validate_metrics(load_json(args.metrics, "metrics"))
    if args.status == "completed":
        if metrics["correctness_pass"] is not True:
            raise SetupError("completed receipts require a passing correctness result")
        required = metrics["verification_required"]
        completed = metrics["verification_completed"]
        passed = metrics["verification_passed"]
        if required is None or required < 1 or (passed, completed) != (required, required):
            raise SetupError("completed receipts require complete, passing verification")
    terminal = {**pending, "status": args.status, "recorded_at": now(), "metrics": metrics}
    append_private_json(receipt_path(args.state_root, terminal["recorded_at"]), terminal)
    print(json.dumps({"run_id": args.run_id, "status": args.status}, indent=2))
    return 0


def audit(args: argparse.Namespace) -> int:
    if args.stale_after_hours < 0:
        raise SetupError("stale_after_hours must be nonnegative")
    rows = receipt_rows(args.state_root)
    terminals = {row["run_id"] for row in rows if row.get("status") in TERMINAL_STATUSES}
    cutoff = datetime.now(timezone.utc).timestamp() - args.stale_after_hours * 3600
    stale = []
    pending = 0
    for row in rows:
        if row.get("status") != "pending" or row.get("run_id") in terminals:
            continue
        pending += 1
        timestamp = parse_timestamp(row["recorded_at"], "receipt recorded_at").timestamp()
        if timestamp < cutoff:
            stale.append(row["run_id"])
    result = {"status": "pass" if not stale else "fail", "pending": pending, "stale": len(stale), "stale_run_ids": stale}
    print(json.dumps(result, indent=2))
    return 0 if not stale else 1


def validate_command(args: argparse.Namespace) -> int:
    catalog = validate_catalog(args.repo_root.resolve(strict=True), args.catalog)
    result = {
        "status": "pass",
        "components": len(catalog["components"]),
        "plugin_skills": sum(len(component["skills"]) for component in catalog["components"] if component["kind"] == "plugin"),
        "domains": {domain["id"]: domain["components"] for domain in catalog["domains"]},
    }
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--repo-root", type=Path, required=True)
    validate.add_argument("--catalog", type=Path)

    initialize = sub.add_parser("setup")
    initialize.add_argument("--repo-root", type=Path, required=True)
    initialize.add_argument("--state-root", type=Path, default=Path.home() / ".rhize" / "evals")
    initialize.add_argument("--catalog", type=Path)
    initialize.add_argument("--plugin", action="append")
    initialize.add_argument("--capture-mode", choices=sorted(CAPTURE_MODES), required=True)
    initialize.add_argument("--baseline-decisions", type=Path)
    initialize.add_argument("--run-free-smoke", action="store_true")

    begin = sub.add_parser("reserve")
    begin.add_argument("--state-root", type=Path, default=Path.home() / ".rhize" / "evals")
    begin.add_argument("--plugin", required=True)
    begin.add_argument("--benchmark", required=True)
    begin.add_argument("--variant", choices=["A", "B"], required=True)
    begin.add_argument("--input-file", type=Path, required=True)

    finish = sub.add_parser("finalize")
    finish.add_argument("--state-root", type=Path, default=Path.home() / ".rhize" / "evals")
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--status", choices=sorted(TERMINAL_STATUSES), required=True)
    finish.add_argument("--metrics", type=Path, required=True)

    health = sub.add_parser("audit")
    health.add_argument("--state-root", type=Path, default=Path.home() / ".rhize" / "evals")
    health.add_argument("--stale-after-hours", type=float, default=24)

    args = parser.parse_args()
    try:
        if args.command == "validate":
            return validate_command(args)
        if args.command == "setup":
            return setup(args)
        if args.command == "reserve":
            return reserve(args)
        if args.command == "finalize":
            return finalize(args)
        return audit(args)
    except (SetupError, OSError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
