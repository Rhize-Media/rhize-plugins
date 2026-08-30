#!/usr/bin/env python3
"""Deterministic, local-only compiler for evidence-bound Obsidian knowledge pages."""

from __future__ import annotations

import argparse
import base64
import contextlib
import difflib
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, NoReturn


COMPILER_NAME = "rhize-compiled-knowledge"
COMPILER_VERSION = "1.0.0"
SCHEMA_VERSION = 1
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
OWNERSHIP_PREFIX = "<!-- rhize-compiled-knowledge:page-id="
INERT_INSTRUCTION_PATTERNS = {
    "fake-system-delimiter": re.compile(r"<\/?(?:system|assistant|developer)>", re.I),
    "instruction-override": re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I),
    "slash-command": re.compile(r"(?m)^\s*/[a-z][a-z0-9:_-]{1,63}(?:\s|$)", re.I),
    "tool-json": re.compile(r'"(?:tool|tool_name|arguments)"\s*:', re.I),
}


class CompilerError(Exception):
    """A fail-closed user-facing compiler error."""


class InjectedCrash(BaseException):
    """Simulates process death after a journaled write in tests."""


@dataclass(frozen=True)
class Settings:
    config_path: Path
    vault_root: Path
    state_root: Path
    source_roots: tuple[Path, ...]
    output_root: Path
    project: dict[str, str]
    operator_id: str
    allowed_acls: tuple[str, ...]
    allowed_egress: tuple[str, ...]
    retention_classes: tuple[str, ...]
    preview_ttl_seconds: int


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CompilerError(f"invalid RFC3339 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise CompilerError(f"timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def current_time(explicit: str | None = None) -> datetime:
    return parse_time(explicit) if explicit else datetime.now(timezone.utc).replace(microsecond=0)


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilerError(f"cannot read valid JSON from {path}: {exc}") from exc


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CompilerError(f"{label} must be an object")
    return value


def require_exact_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unknown:
            details.append(f"unknown={','.join(unknown)}")
        raise CompilerError(f"{label} has invalid fields ({'; '.join(details)})")


def require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise CompilerError(f"{label} must match {ID_PATTERN.pattern}")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompilerError(f"{label} must be a non-empty string")
    return value


def require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CompilerError(f"{label} must be a non-empty array")
    result = [require_id(item, f"{label}[]") for item in value]
    if len(result) != len(set(result)):
        raise CompilerError(f"{label} must not contain duplicates")
    return result


def is_relative_safe(path_text: str, label: str) -> Path:
    path = Path(require_string(path_text, label))
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise CompilerError(f"{label} must be a non-empty relative path without '..'")
    return path


def resolve_existing_under(root: Path, relative: str, label: str) -> Path:
    try:
        candidate = (root / is_relative_safe(relative, label)).resolve(strict=True)
    except FileNotFoundError as exc:
        raise CompilerError(f"{label} does not exist") from exc
    if not candidate.is_relative_to(root):
        raise CompilerError(f"{label} escapes the configured root")
    return candidate


def resolve_target_under(root: Path, relative: str, label: str) -> Path:
    rel = is_relative_safe(relative, label)
    parent = (root / rel).parent.resolve(strict=True)
    if not parent.is_relative_to(root):
        raise CompilerError(f"{label} escapes the configured root")
    candidate = parent / rel.name
    if candidate.is_symlink():
        raise CompilerError(f"{label} cannot be a symlink")
    return candidate


def resolve_directory_under(root: Path, relative: str, label: str, *, create: bool = False) -> Path:
    rel = is_relative_safe(relative, label)
    candidate = root
    for part in rel.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            try:
                candidate = candidate.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise CompilerError(f"{label} cannot be resolved safely") from exc
            if not candidate.is_relative_to(root):
                raise CompilerError(f"{label} escapes the configured root through a symlink")
        if candidate.exists():
            if not candidate.is_dir():
                raise CompilerError(f"{label} must be a directory")
        elif create:
            candidate.mkdir(mode=0o700)
        else:
            raise CompilerError(f"{label} does not exist")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CompilerError(f"{label} cannot be resolved safely") from exc
    if not resolved.is_relative_to(root):
        raise CompilerError(f"{label} escapes the configured root")
    return resolved


def authorized_absolute_path(
    raw_path: Any,
    root: Path,
    label: str,
    *,
    expected: Path | None = None,
) -> Path:
    path = Path(require_string(raw_path, label))
    if not path.is_absolute():
        raise CompilerError(f"{label} must be an absolute path")
    if expected is not None and path != expected:
        raise CompilerError(f"{label} does not match its canonical path")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CompilerError(f"{label} escapes the configured root") from exc
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise CompilerError(f"{label} cannot contain symlink components")
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise CompilerError(f"{label} cannot be resolved safely") from exc
    if not resolved.is_relative_to(root):
        raise CompilerError(f"{label} escapes the configured root")
    return path


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    ensure_private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def backup(data: bytes | None) -> dict[str, Any]:
    return {"exists": data is not None, "data": base64.b64encode(data or b"").decode("ascii")}


def restore(path: Path, saved: dict[str, Any], mode: int = 0o600) -> None:
    if saved["exists"]:
        atomic_write(path, base64.b64decode(saved["data"]), mode)
    else:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


def load_settings(config_path: Path) -> Settings:
    raw = require_object(load_json(config_path.resolve(strict=True)), "config")
    required = {
        "schema_version", "project", "operator_id", "vault_root", "allowed_vault_roots",
        "source_roots", "output_root", "state_root", "allowed_acls", "allowed_egress",
        "retention_classes", "qmd_enabled", "preview_ttl_seconds",
        "scheduled_enabled", "live_synthesis_enabled", "context_pack_enabled",
        "graphify_enabled", "neo4j_enabled",
    }
    require_exact_keys(raw, required, "config")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise CompilerError("config.schema_version must be 1")

    project = require_object(raw["project"], "config.project")
    require_exact_keys(project, {"id", "tenant_id", "scope_id"}, "config.project")
    normalized_project = {key: require_id(project[key], f"config.project.{key}") for key in project}
    operator_id = require_id(raw["operator_id"], "config.operator_id")

    allowed_roots_raw = raw["allowed_vault_roots"]
    if not isinstance(allowed_roots_raw, list) or not allowed_roots_raw:
        raise CompilerError("config.allowed_vault_roots must be a non-empty array")
    allowed_roots = tuple(Path(require_string(item, "allowed_vault_roots[]")).expanduser().resolve(strict=True) for item in allowed_roots_raw)
    vault_root = Path(require_string(raw["vault_root"], "config.vault_root")).expanduser().resolve(strict=True)
    if not vault_root.is_dir() or not any(vault_root == root or vault_root.is_relative_to(root) for root in allowed_roots):
        raise CompilerError("config.vault_root is outside allowed_vault_roots")

    source_roots_raw = raw["source_roots"]
    if not isinstance(source_roots_raw, list) or not source_roots_raw:
        raise CompilerError("config.source_roots must be a non-empty array")
    source_roots = tuple(resolve_existing_under(vault_root, item, "source_roots[]") for item in source_roots_raw)
    if not all(root.is_dir() for root in source_roots):
        raise CompilerError("every source root must be a directory")

    output_root = resolve_directory_under(vault_root, raw["output_root"], "config.output_root")
    state_root = resolve_directory_under(vault_root, raw["state_root"], "config.state_root", create=True)
    ensure_private_dir(state_root)
    if output_root.is_relative_to(state_root) or state_root.is_relative_to(output_root):
        raise CompilerError("output_root and state_root must not overlap")

    allowed_acls = tuple(require_string_list(raw["allowed_acls"], "config.allowed_acls"))
    allowed_egress = tuple(require_string_list(raw["allowed_egress"], "config.allowed_egress"))
    retention_classes = tuple(require_string_list(raw["retention_classes"], "config.retention_classes"))
    for gate in ("scheduled_enabled", "live_synthesis_enabled", "context_pack_enabled", "graphify_enabled", "neo4j_enabled"):
        if raw[gate] is not False:
            raise CompilerError(f"config.{gate} must remain false in the first release")
    if raw["qmd_enabled"] is not False:
        raise CompilerError("config.qmd_enabled must remain false until an ACL-aware qmd adapter is implemented")
    ttl = raw["preview_ttl_seconds"]
    if not isinstance(ttl, int) or not 60 <= ttl <= 604800:
        raise CompilerError("config.preview_ttl_seconds must be between 60 and 604800")
    return Settings(
        config_path=config_path.resolve(strict=True), vault_root=vault_root, state_root=state_root,
        source_roots=source_roots, output_root=output_root, project=normalized_project,
        operator_id=operator_id, allowed_acls=allowed_acls, allowed_egress=allowed_egress,
        retention_classes=retention_classes, preview_ttl_seconds=ttl,
    )


@contextlib.contextmanager
def vault_lock(settings: Settings) -> Iterator[None]:
    lock_path = settings.state_root / "compiler.lock"
    ensure_private_dir(lock_path.parent)
    with lock_path.open("a+b") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def registration_path(settings: Settings, source_id: str) -> Path:
    return settings.state_root / "registrations" / f"{require_id(source_id, 'source_id')}.json"


def snapshot_path(settings: Settings, source_id: str, revision_hash: str) -> Path:
    if not HASH_PATTERN.fullmatch(revision_hash):
        raise CompilerError("invalid revision hash")
    return settings.state_root / "sources" / source_id / f"{revision_hash.removeprefix('sha256:')}.bin"


def source_path(settings: Settings, source_relative: str) -> Path:
    candidate = resolve_existing_under(settings.vault_root, source_relative, "source")
    if (
        not candidate.is_file()
        or not any(candidate.is_relative_to(root) for root in settings.source_roots)
        or candidate.is_relative_to(settings.state_root)
        or candidate.is_relative_to(settings.output_root)
    ):
        raise CompilerError("source must be a regular file inside a configured source_root")
    return candidate


def load_registration(settings: Settings, source_id: str) -> dict[str, Any]:
    path = registration_path(settings, source_id)
    value = require_object(load_json(path), "source registration")
    expected = {
        "schema_version", "project", "source_id", "path", "current_revision_hash", "captured_at",
        "acl", "egress", "retention_class", "status", "expires_at", "revisions",
    }
    require_exact_keys(value, expected, "source registration")
    if value["schema_version"] != 1 or value["project"] != settings.project or value["source_id"] != source_id:
        raise CompilerError("source registration does not match the configured project/source")
    is_relative_safe(value["path"], "source registration path")
    if not HASH_PATTERN.fullmatch(value.get("current_revision_hash", "")):
        raise CompilerError("source registration has an invalid current revision hash")
    acl = value.get("acl")
    if not isinstance(acl, list) or not acl or len(acl) != len(set(acl)) or not set(acl).issubset(settings.allowed_acls):
        raise CompilerError("source registration ACL is invalid for the configured project")
    if value.get("egress") not in settings.allowed_egress or value.get("retention_class") not in settings.retention_classes:
        raise CompilerError("source registration egress/retention is invalid for the configured project")
    if value.get("status") not in {"active", "removed", "purged"}:
        raise CompilerError("source registration status is invalid")
    parse_time(require_string(value.get("captured_at"), "source registration captured_at"))
    if value.get("expires_at") is not None:
        parse_time(value["expires_at"])
    revisions = value.get("revisions")
    if not isinstance(revisions, list) or any(not isinstance(item, str) or not HASH_PATTERN.fullmatch(item) for item in revisions):
        raise CompilerError("source registration revisions are invalid")
    if value["status"] != "purged" and value["current_revision_hash"] not in revisions:
        raise CompilerError("source registration current revision is not retained")
    return value


def effective_source_status(registration: dict[str, Any], at: datetime) -> str:
    if registration["status"] == "purged":
        return "purged"
    expires_at = registration.get("expires_at")
    if expires_at and at >= parse_time(expires_at):
        return "expired"
    return registration["status"]


def register_source(
    settings: Settings, source_relative: str, source_id: str, acl: list[str], egress: str,
    retention_class: str, captured_at: datetime, expires_at: str | None,
) -> dict[str, Any]:
    require_id(source_id, "source_id")
    if not acl or len(acl) != len(set(acl)) or not set(acl).issubset(settings.allowed_acls):
        raise CompilerError("source ACL must be unique and within config.allowed_acls")
    if egress not in settings.allowed_egress:
        raise CompilerError("source egress is not allowed by the config")
    if retention_class not in settings.retention_classes:
        raise CompilerError("source retention class is not allowed by the config")
    if expires_at:
        parse_time(expires_at)
    canonical = source_path(settings, source_relative)
    content = canonical.read_bytes()
    revision_hash = digest(content)
    with vault_lock(settings):
        recover_incomplete(settings)
        path = registration_path(settings, source_id)
        previous = load_json(path) if path.exists() else None
        if previous:
            previous = require_object(previous, "source registration")
            if previous.get("project") != settings.project or previous.get("path") != source_relative:
                raise CompilerError("source_id is already registered to a different project or path")
            if previous.get("status") == "purged":
                raise CompilerError("a purged source_id cannot be reused")
            revisions = list(previous.get("revisions", []))
        else:
            revisions = []
        if revision_hash not in revisions:
            revisions.append(revision_hash)
        registration = {
            "schema_version": 1,
            "project": settings.project,
            "source_id": source_id,
            "path": source_relative,
            "current_revision_hash": revision_hash,
            "captured_at": format_time(captured_at),
            "acl": sorted(acl),
            "egress": egress,
            "retention_class": retention_class,
            "status": "active",
            "expires_at": format_time(parse_time(expires_at)) if expires_at else None,
            "revisions": revisions,
        }
        atomic_write(snapshot_path(settings, source_id, revision_hash), content)
        atomic_write(path, canonical_json(registration))
    return registration


def validate_proposal(raw: Any) -> dict[str, Any]:
    proposal = require_object(raw, "proposal")
    require_exact_keys(
        proposal,
        {"schema_version", "source_id", "page", "claims", "links", "contradiction_candidates"},
        "proposal",
    )
    if proposal["schema_version"] != 1:
        raise CompilerError("proposal.schema_version must be 1")
    require_id(proposal["source_id"], "proposal.source_id")
    page = require_object(proposal["page"], "proposal.page")
    require_exact_keys(page, {"page_id", "path", "title"}, "proposal.page")
    require_id(page["page_id"], "proposal.page.page_id")
    is_relative_safe(page["path"], "proposal.page.path")
    require_string(page["title"], "proposal.page.title")
    if not isinstance(proposal["claims"], list) or not proposal["claims"]:
        raise CompilerError("proposal.claims must be a non-empty array")
    claim_ids: list[str] = []
    for index, raw_claim in enumerate(proposal["claims"]):
        claim = require_object(raw_claim, f"proposal.claims[{index}]")
        require_exact_keys(claim, {"claim_id", "text", "citations"}, f"proposal.claims[{index}]")
        claim_ids.append(require_id(claim["claim_id"], f"proposal.claims[{index}].claim_id"))
        require_string(claim["text"], f"proposal.claims[{index}].text")
        if not isinstance(claim["citations"], list) or not claim["citations"]:
            raise CompilerError(f"proposal.claims[{index}].citations must be non-empty")
        for citation_index, raw_citation in enumerate(claim["citations"]):
            citation = require_object(raw_citation, "proposal citation")
            require_exact_keys(citation, {"start_line", "end_line"}, "proposal citation")
            start, end = citation["start_line"], citation["end_line"]
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                raise CompilerError(f"claim {claim_ids[-1]} has an invalid inclusive line range")
    if len(claim_ids) != len(set(claim_ids)):
        raise CompilerError("proposal claim ids must be unique")
    if not isinstance(proposal["links"], list) or any(not isinstance(item, str) or not item.strip() for item in proposal["links"]):
        raise CompilerError("proposal.links must be an array of non-empty strings")
    if len(proposal["links"]) != len(set(proposal["links"])):
        raise CompilerError("proposal.links must be unique")
    if not isinstance(proposal["contradiction_candidates"], list):
        raise CompilerError("proposal.contradiction_candidates must be an array")
    for pair in proposal["contradiction_candidates"]:
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1] or any(item not in claim_ids for item in pair):
            raise CompilerError("each contradiction candidate must name two different known claims")
    return proposal


def source_findings(content: str) -> list[str]:
    return sorted(name for name, pattern in INERT_INSTRUCTION_PATTERNS.items() if pattern.search(content))


def manifest_validation(manifest: Any) -> dict[str, Any]:
    value = require_object(manifest, "manifest")
    require_exact_keys(
        value,
        {"schema_version", "compiler", "project", "operator_id", "preview", "source_revisions", "pages", "policy", "provenance", "diff", "adapters"},
        "manifest",
    )
    if value["schema_version"] != 1:
        raise CompilerError("manifest.schema_version must be 1")
    compiler = require_object(value["compiler"], "manifest.compiler")
    require_exact_keys(compiler, {"name", "version"}, "manifest.compiler")
    if compiler != {"name": COMPILER_NAME, "version": COMPILER_VERSION}:
        raise CompilerError("manifest compiler identity/version is unsupported")
    project = require_object(value["project"], "manifest.project")
    require_exact_keys(project, {"id", "tenant_id", "scope_id"}, "manifest.project")
    for key, project_id in project.items():
        require_id(project_id, f"manifest.project.{key}")
    require_id(value["operator_id"], "manifest.operator_id")
    if not isinstance(value["source_revisions"], list) or not value["source_revisions"]:
        raise CompilerError("manifest.source_revisions must be non-empty")
    if not isinstance(value["pages"], list) or len(value["pages"]) != 1:
        raise CompilerError("manifest.pages must contain exactly one page")
    preview = require_object(value["preview"], "manifest.preview")
    require_exact_keys(preview, {"id", "created_at", "expires_at", "status"}, "manifest.preview")
    if not HASH_PATTERN.fullmatch(preview.get("id", "")) or preview.get("status") not in {"preview", "accepted"}:
        raise CompilerError("manifest preview identity/status is invalid")
    parse_time(preview["created_at"])
    parse_time(preview["expires_at"])
    policy = require_object(value["policy"], "manifest.policy")
    require_exact_keys(policy, {"vault_root", "state_root", "acl", "egress", "retention_class"}, "manifest.policy")
    provenance = require_object(value["provenance"], "manifest.provenance")
    require_exact_keys(
        provenance,
        {"proposal_hash", "source_metadata_hash", "source_to_derived", "inert_content_findings"},
        "manifest.provenance",
    )
    diff = require_object(value["diff"], "manifest.diff")
    require_exact_keys(diff, {"base_hash", "rendered_hash", "unified_diff_hash", "change_brief_hash"}, "manifest.diff")
    if diff["base_hash"] is not None and not HASH_PATTERN.fullmatch(diff["base_hash"]):
        raise CompilerError("manifest contains an invalid base hash")
    adapters = require_object(value["adapters"], "manifest.adapters")
    require_exact_keys(adapters, {"qmd", "context_pack", "graphify", "neo4j"}, "manifest.adapters")
    for name, raw_adapter in adapters.items():
        adapter = require_object(raw_adapter, f"manifest.adapters.{name}")
        require_exact_keys(adapter, {"eligible", "reason"}, f"manifest.adapters.{name}")
        if not isinstance(adapter["eligible"], bool):
            raise CompilerError(f"manifest.adapters.{name}.eligible must be boolean")
        require_string(adapter["reason"], f"manifest.adapters.{name}.reason")
    if adapters["qmd"]["eligible"]:
        raise CompilerError("manifest.adapters.qmd.eligible must remain false until an ACL-aware adapter is implemented")
    if adapters["qmd"]["reason"] not in {"preview-not-accepted", "acl-aware-qmd-adapter-not-configured"}:
        raise CompilerError("manifest.adapters.qmd.reason is unsupported while qmd remains disabled")
    for hash_value in (diff["rendered_hash"], diff["unified_diff_hash"], diff["change_brief_hash"], provenance["proposal_hash"], provenance["source_metadata_hash"]):
        if not isinstance(hash_value, str) or not HASH_PATTERN.fullmatch(hash_value):
            raise CompilerError("manifest contains an invalid required hash")
    return value


def validate_preview_identity(manifest: dict[str, Any]) -> None:
    payload = json.loads(json.dumps(manifest))
    claimed = payload["preview"].pop("id")
    if payload["preview"]["status"] != "preview" or digest(canonical_json(payload)) != claimed:
        raise CompilerError("preview manifest identity no longer matches its contents")


def render_page(proposal: dict[str, Any], registration: dict[str, Any], citations: list[dict[str, Any]]) -> bytes:
    page = proposal["page"]
    lines = [
        f"{OWNERSHIP_PREFIX}{page['page_id']} -->",
        "---",
        "type: compiled-knowledge",
        f"rhize-page-id: {json.dumps(page['page_id'])}",
        f"rhize-source-id: {json.dumps(registration['source_id'])}",
        f"rhize-source-revision: {json.dumps(registration['current_revision_hash'])}",
        f"acl: {json.dumps(registration['acl'], ensure_ascii=False)}",
        f"egress: {json.dumps(registration['egress'])}",
        "---",
        "",
        f"# {page['title']}",
        "",
    ]
    citation_by_claim = {item["claim_id"]: item["citations"] for item in citations}
    for claim in proposal["claims"]:
        refs = " ".join(f"[^{claim['claim_id']}-{index + 1}]" for index in range(len(citation_by_claim[claim["claim_id"]])))
        lines.extend([f"{claim['text']} {refs}", ""])
    if proposal["links"]:
        lines.extend(["## Related", ""])
        lines.extend(f"- [[{link}]]" for link in sorted(proposal["links"]))
        lines.append("")
    if proposal["contradiction_candidates"]:
        lines.extend(["## Contradiction candidates", ""])
        lines.extend(f"- `{left}` competes with `{right}`; human review required." for left, right in proposal["contradiction_candidates"])
        lines.append("")
    lines.extend(["## Evidence", ""])
    for claim in proposal["claims"]:
        for index, citation in enumerate(citation_by_claim[claim["claim_id"]], start=1):
            anchor = citation["anchor"]
            lines.append(
                f"[^{claim['claim_id']}-{index}]: `{citation['source_id']}@{citation['revision_hash']}"
                f"#L{anchor['start_line']}-L{anchor['end_line']}` (`{anchor['content_hash']}`)"
            )
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def preview_source(settings: Settings, proposal_path: Path, at: datetime) -> dict[str, Any]:
    proposal_bytes = proposal_path.resolve(strict=True).read_bytes()
    return preview_payload(settings, proposal_bytes, at)


def preview_payload(settings: Settings, proposal_bytes: bytes, at: datetime) -> dict[str, Any]:
    try:
        proposal = validate_proposal(json.loads(proposal_bytes))
    except json.JSONDecodeError as exc:
        raise CompilerError(f"proposal is not valid JSON: {exc}") from exc
    registration = load_registration(settings, proposal["source_id"])
    if effective_source_status(registration, at) != "active":
        raise CompilerError("source is not active under its retention/purge policy")
    canonical = source_path(settings, registration["path"])
    source_bytes = canonical.read_bytes()
    if digest(source_bytes) != registration["current_revision_hash"]:
        raise CompilerError("source changed after registration; register the new revision first")
    snapshot = snapshot_path(settings, registration["source_id"], registration["current_revision_hash"])
    if read_optional(snapshot) != source_bytes:
        raise CompilerError("retained source snapshot is missing or does not match")
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompilerError("compiled sources must be UTF-8") from exc
    source_lines = source_text.splitlines(keepends=True)
    materialized_claims = []
    for claim in proposal["claims"]:
        citations = []
        for reference in claim["citations"]:
            start, end = reference["start_line"], reference["end_line"]
            if end > len(source_lines):
                raise CompilerError(f"claim {claim['claim_id']} cites beyond the source")
            excerpt = "".join(source_lines[start - 1:end]).encode("utf-8")
            citations.append({
                "source_id": registration["source_id"],
                "revision_hash": registration["current_revision_hash"],
                "anchor": {"start_line": start, "end_line": end, "content_hash": digest(excerpt)},
            })
        materialized_claims.append({"claim_id": claim["claim_id"], "text": claim["text"], "citations": citations})

    page_relative = proposal["page"]["path"]
    target = resolve_target_under(settings.output_root, page_relative, "proposal.page.path")
    base = read_optional(target)
    marker = f"{OWNERSHIP_PREFIX}{proposal['page']['page_id']} -->".encode()
    if base is not None and not base.startswith(marker):
        raise CompilerError("target exists without the matching compiler ownership marker")
    rendered = render_page(proposal, registration, materialized_claims)
    diff_text = "".join(difflib.unified_diff(
        (base or b"").decode("utf-8").splitlines(keepends=True),
        rendered.decode("utf-8").splitlines(keepends=True),
        fromfile=f"a/{page_relative}", tofile=f"b/{page_relative}",
    )).encode()
    change = (
        f"# Compiled knowledge change brief\n\n"
        f"- Page: `{page_relative}`\n"
        f"- Source: `{registration['source_id']}@{registration['current_revision_hash']}`\n"
        f"- Claims: {len(materialized_claims)}\n"
        f"- Contradiction candidates: {len(proposal['contradiction_candidates'])}\n"
        f"- Operation: {'create' if base is None else 'replace compiler-owned page'}\n"
        f"- Apply requires explicit approval of this preview id.\n"
    ).encode()
    created_at = format_time(at)
    expires_at = format_time(at + timedelta(seconds=settings.preview_ttl_seconds))
    acl = sorted(registration["acl"])
    manifest = {
        "schema_version": 1,
        "compiler": {"name": COMPILER_NAME, "version": COMPILER_VERSION},
        "project": settings.project,
        "operator_id": settings.operator_id,
        "preview": {"id": "sha256:" + "0" * 64, "created_at": created_at, "expires_at": expires_at, "status": "preview"},
        "source_revisions": [{
            "source_id": registration["source_id"], "path": registration["path"],
            "revision_hash": registration["current_revision_hash"], "content_bytes": len(source_bytes),
            "captured_at": registration["captured_at"], "acl": acl, "egress": registration["egress"],
            "retention_class": registration["retention_class"], "status": "active",
        }],
        "pages": [{
            "page_id": proposal["page"]["page_id"], "path": page_relative,
            "title": proposal["page"]["title"], "ownership_marker": marker.decode(),
            "claims": materialized_claims, "links": sorted(proposal["links"]),
            "contradiction_candidates": proposal["contradiction_candidates"],
        }],
        "policy": {
            "vault_root": ".", "state_root": settings.state_root.relative_to(settings.vault_root).as_posix(),
            "acl": acl, "egress": registration["egress"], "retention_class": registration["retention_class"],
        },
        "provenance": {
            "proposal_hash": digest(proposal_bytes),
            "source_metadata_hash": digest(canonical_json(registration)),
            "source_to_derived": {registration["source_id"]: [proposal["page"]["page_id"]]},
            "inert_content_findings": source_findings(source_text),
        },
        "diff": {
            "base_hash": digest(base) if base is not None else None, "rendered_hash": digest(rendered),
            "unified_diff_hash": digest(diff_text), "change_brief_hash": digest(change),
        },
        "adapters": {
            "qmd": {"eligible": False, "reason": "preview-not-accepted"},
            "context_pack": {"eligible": False, "reason": "adapter-gate-disabled"},
            "graphify": {"eligible": False, "reason": "ontology-and-hygiene-gates-disabled"},
            "neo4j": {"eligible": False, "reason": "direct-export-disabled"},
        },
    }
    identity_payload = json.loads(json.dumps(manifest))
    identity_payload["preview"].pop("id")
    preview_id = digest(canonical_json(identity_payload))
    manifest["preview"]["id"] = preview_id
    manifest_validation(manifest)
    preview_dir = settings.state_root / "previews" / preview_id.removeprefix("sha256:")
    with vault_lock(settings):
        recover_incomplete(settings)
        ensure_private_dir(preview_dir)
        atomic_write(preview_dir / "manifest.json", canonical_json(manifest))
        atomic_write(preview_dir / "page.md", rendered)
        atomic_write(preview_dir / "diff.patch", diff_text)
        atomic_write(preview_dir / "change-brief.md", change)
    return {"preview_id": preview_id, "preview_dir": str(preview_dir), "expires_at": expires_at, "findings": manifest["provenance"]["inert_content_findings"]}


def preview_dir(settings: Settings, preview_id: str) -> Path:
    if not HASH_PATTERN.fullmatch(preview_id):
        raise CompilerError("preview id must be a sha256 digest")
    return settings.state_root / "previews" / preview_id.removeprefix("sha256:")


def index_path(settings: Settings) -> Path:
    return settings.state_root / "index.json"


def accepted_log_path(settings: Settings) -> Path:
    return settings.state_root / "accepted.log.jsonl"


def accepted_manifest_path(settings: Settings, page_id: str) -> Path:
    return settings.state_root / "accepted" / f"{require_id(page_id, 'page_id')}.json"


def accepted_manifest_path_from_entry(settings: Settings, page_id: str, entry: dict[str, Any]) -> Path:
    expected = accepted_manifest_path(settings, page_id)
    return authorized_absolute_path(
        entry.get("manifest_path"),
        settings.state_root,
        f"index.pages.{page_id}.manifest_path",
        expected=expected,
    )


def validate_index_entry(settings: Settings, page_id: str, raw_entry: Any) -> dict[str, Any]:
    entry = require_object(raw_entry, f"index.pages.{page_id}")
    require_exact_keys(
        entry,
        {
            "preview_id", "manifest_path", "path", "rendered_hash", "source_ids",
            "status", "qmd_eligible", "manifest_hash",
        },
        f"index.pages.{page_id}",
    )
    if not isinstance(entry.get("preview_id"), str) or not HASH_PATTERN.fullmatch(entry["preview_id"]):
        raise CompilerError(f"index.pages.{page_id}.preview_id is invalid")
    hashes = (entry.get("rendered_hash"), entry.get("manifest_hash"))
    if any(not isinstance(value, str) or not HASH_PATTERN.fullmatch(value) for value in hashes):
        raise CompilerError(f"index.pages.{page_id} contains an invalid hash")
    require_string_list(entry.get("source_ids"), f"index.pages.{page_id}.source_ids")
    if entry.get("status") not in {"accepted", "purged"}:
        raise CompilerError(f"index.pages.{page_id}.status is invalid")
    if entry.get("qmd_eligible") is not False:
        raise CompilerError(f"index.pages.{page_id}.qmd_eligible must remain false")
    resolve_target_under(settings.output_root, entry.get("path"), f"index.pages.{page_id}.path")
    accepted_manifest_path_from_entry(settings, page_id, entry)
    return entry


def load_index(settings: Settings) -> dict[str, Any]:
    path = authorized_absolute_path(
        str(index_path(settings)),
        settings.state_root,
        "index path",
        expected=index_path(settings),
    )
    if not path.exists():
        return {"schema_version": 1, "project": settings.project, "pages": {}}
    index = require_object(load_json(path), "index")
    require_exact_keys(index, {"schema_version", "project", "pages"}, "index")
    if index["schema_version"] != 1 or index["project"] != settings.project or not isinstance(index["pages"], dict):
        raise CompilerError("index does not match the configured project")
    for raw_page_id, entry in index["pages"].items():
        page_id = require_id(raw_page_id, "index page id")
        validate_index_entry(settings, page_id, entry)
    return index


def load_accepted_manifest(
    settings: Settings,
    page_id: str,
    entry: dict[str, Any],
    accepted_bytes: bytes | None = None,
) -> dict[str, Any]:
    path = accepted_manifest_path_from_entry(settings, page_id, entry)
    accepted_bytes = read_optional(path) if accepted_bytes is None else accepted_bytes
    if accepted_bytes is None:
        raise CompilerError("accepted manifest is missing")
    if digest(accepted_bytes) != entry["manifest_hash"]:
        raise CompilerError("accepted manifest hash does not match the index")
    try:
        manifest = manifest_validation(json.loads(accepted_bytes))
    except json.JSONDecodeError as exc:
        raise CompilerError("accepted manifest is not valid JSON") from exc
    page = require_object(manifest["pages"][0], "accepted manifest page")
    source_revisions = manifest["source_revisions"]
    if not all(isinstance(item, dict) for item in source_revisions):
        raise CompilerError("accepted manifest source revisions are invalid")
    source_ids = [require_id(item.get("source_id"), "accepted manifest source_id") for item in source_revisions]
    revision_hashes = [item.get("revision_hash") for item in source_revisions]
    if len(source_ids) != len(set(source_ids)) or any(
        not isinstance(value, str) or not HASH_PATTERN.fullmatch(value) for value in revision_hashes
    ):
        raise CompilerError("accepted manifest source revisions are invalid")
    expected_state_root = settings.state_root.relative_to(settings.vault_root).as_posix()
    preview = manifest["preview"]
    if (
        manifest["project"] != settings.project
        or manifest["operator_id"] != settings.operator_id
        or preview["id"] != entry["preview_id"]
        or preview["status"] != "accepted"
        or page.get("page_id") != page_id
        or page.get("path") != entry["path"]
        or manifest["diff"]["rendered_hash"] != entry["rendered_hash"]
        or source_ids != entry["source_ids"]
        or manifest["policy"].get("vault_root") != "."
        or manifest["policy"].get("state_root") != expected_state_root
        or manifest["adapters"]["qmd"]["eligible"] is not False
    ):
        raise CompilerError("accepted manifest does not match the configured index/project authority")
    return manifest


def write_journal(path: Path, journal: dict[str, Any]) -> None:
    atomic_write(path, canonical_json(journal))


def validate_backup(value: Any, label: str) -> None:
    saved = require_object(value, label)
    require_exact_keys(saved, {"exists", "data"}, label)
    if not isinstance(saved["exists"], bool) or not isinstance(saved["data"], str):
        raise CompilerError(f"{label} is invalid")
    try:
        base64.b64decode(saved["data"], validate=True)
    except ValueError as exc:
        raise CompilerError(f"{label} contains invalid base64") from exc


def validate_journal(settings: Settings, path: Path, raw_journal: Any) -> tuple[dict[str, Any], dict[str, Path]]:
    authorized_absolute_path(str(path), settings.state_root, "transaction journal path")
    journal = require_object(raw_journal, "transaction journal")
    required = {"schema_version", "preview_id", "state", "paths", "backups"}
    unknown = set(journal) - (required | {"recovery"})
    missing = required - set(journal)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing={','.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown={','.join(sorted(unknown))}")
        raise CompilerError(f"transaction journal has invalid fields ({'; '.join(details)})")
    preview_id = journal.get("preview_id")
    if (
        journal.get("schema_version") != 1
        or not isinstance(preview_id, str)
        or not HASH_PATTERN.fullmatch(preview_id)
        or path.name != f"{preview_id.removeprefix('sha256:')}.json"
        or journal.get("state") not in {"prepared", "target-written", "manifest-written", "index-written", "accepted", "rolled-back"}
    ):
        raise CompilerError(f"transaction journal {path.name} has invalid identity/state")
    paths = require_object(journal["paths"], "transaction journal paths")
    backups = require_object(journal["backups"], "transaction journal backups")
    path_keys = {"target", "index", "log", "accepted_manifest"}
    require_exact_keys(paths, path_keys, "transaction journal paths")
    require_exact_keys(backups, path_keys, "transaction journal backups")
    validated = {
        "target": authorized_absolute_path(paths["target"], settings.output_root, "transaction target"),
        "index": authorized_absolute_path(
            paths["index"], settings.state_root, "transaction index", expected=index_path(settings)
        ),
        "log": authorized_absolute_path(
            paths["log"], settings.state_root, "transaction log", expected=accepted_log_path(settings)
        ),
    }
    accepted = authorized_absolute_path(
        paths["accepted_manifest"], settings.state_root, "transaction accepted manifest"
    )
    if accepted.suffix != ".json" or not ID_PATTERN.fullmatch(accepted.stem):
        raise CompilerError("transaction accepted manifest has an invalid page id")
    expected_accepted = accepted_manifest_path(settings, accepted.stem)
    if accepted != expected_accepted:
        raise CompilerError("transaction accepted manifest does not match its canonical path")
    validated["accepted_manifest"] = accepted
    if journal["state"] not in {"accepted", "rolled-back"}:
        directory = preview_dir(settings, preview_id)
        preview_manifest = manifest_validation(load_json(directory / "manifest.json"))
        validate_preview_identity(preview_manifest)
        page = require_object(preview_manifest["pages"][0], "transaction preview page")
        page_id = require_id(page.get("page_id"), "transaction preview page id")
        expected_target = resolve_target_under(
            settings.output_root,
            page.get("path"),
            "transaction preview page path",
        )
        if (
            preview_manifest["project"] != settings.project
            or preview_manifest["operator_id"] != settings.operator_id
            or preview_manifest["preview"]["id"] != preview_id
            or validated["target"] != expected_target
            or accepted != accepted_manifest_path(settings, page_id)
        ):
            raise CompilerError(f"transaction journal {path.name} does not match its preview authority")
    for key in path_keys:
        validate_backup(backups[key], f"transaction journal backups.{key}")
    return journal, validated


def recover_incomplete(settings: Settings) -> list[str]:
    journal_root = settings.state_root / "transactions"
    authorized_absolute_path(str(journal_root), settings.state_root, "transaction journal root")
    if not journal_root.exists():
        return []
    recovered = []
    for path in sorted(journal_root.glob("*.json")):
        journal, paths = validate_journal(settings, path, load_json(path))
        if journal.get("state") in {"accepted", "rolled-back"}:
            continue
        backups = journal["backups"]
        restore(paths["target"], backups["target"], 0o644)
        restore(paths["index"], backups["index"])
        restore(paths["log"], backups["log"])
        restore(paths["accepted_manifest"], backups["accepted_manifest"])
        journal["state"] = "rolled-back"
        journal["recovery"] = "restored-pre-transaction-bytes"
        write_journal(path, journal)
        recovered.append(path.stem)
    return recovered


def maybe_crash(point: str, fault_after: str | None) -> None:
    if fault_after == point:
        raise InjectedCrash(point)


def apply_preview(settings: Settings, preview_id: str, at: datetime, fault_after: str | None = None) -> dict[str, Any]:
    with vault_lock(settings):
        recovered = recover_incomplete(settings)
        directory = preview_dir(settings, preview_id)
        manifest = manifest_validation(load_json(directory / "manifest.json"))
        validate_preview_identity(manifest)
        if manifest["project"] != settings.project or manifest["operator_id"] != settings.operator_id:
            raise CompilerError("preview project/operator does not match the current config")
        if manifest["preview"]["id"] != preview_id:
            raise CompilerError("preview directory and manifest id do not match")
        page = manifest["pages"][0]
        target = resolve_target_under(settings.output_root, page["path"], "manifest page path")
        current = read_optional(target)
        index = load_index(settings)
        existing = index["pages"].get(page["page_id"])
        if existing and existing.get("preview_id") == preview_id and current is not None and digest(current) == manifest["diff"]["rendered_hash"]:
            return {"status": "noop", "preview_id": preview_id, "recovered": recovered}
        if at > parse_time(manifest["preview"]["expires_at"]):
            raise CompilerError("preview expired; rebuild a new preview")
        registration = load_registration(settings, manifest["source_revisions"][0]["source_id"])
        source_revision = manifest["source_revisions"][0]
        registration_contract = {
            "source_id": registration["source_id"], "path": registration["path"],
            "revision_hash": registration["current_revision_hash"], "captured_at": registration["captured_at"],
            "acl": sorted(registration["acl"]), "egress": registration["egress"],
            "retention_class": registration["retention_class"],
        }
        manifest_contract = {key: source_revision[key] for key in registration_contract}
        if (
            effective_source_status(registration, at) != "active"
            or registration_contract != manifest_contract
            or manifest["policy"]["acl"] != registration_contract["acl"]
            or manifest["policy"]["egress"] != registration_contract["egress"]
            or manifest["policy"]["retention_class"] != registration_contract["retention_class"]
        ):
            raise CompilerError("source state changed after preview")
        source = source_path(settings, registration["path"])
        if digest(source.read_bytes()) != registration["current_revision_hash"]:
            raise CompilerError("canonical source changed after preview")
        expected_base = manifest["diff"]["base_hash"]
        if (digest(current) if current is not None else None) != expected_base:
            raise CompilerError("target changed after preview; refusing to overwrite human edits")
        rendered = (directory / "page.md").read_bytes()
        diff_bytes = (directory / "diff.patch").read_bytes()
        brief = (directory / "change-brief.md").read_bytes()
        if digest(rendered) != manifest["diff"]["rendered_hash"] or digest(diff_bytes) != manifest["diff"]["unified_diff_hash"] or digest(brief) != manifest["diff"]["change_brief_hash"]:
            raise CompilerError("preview artifacts no longer match the manifest")
        accepted = json.loads(json.dumps(manifest))
        accepted["preview"]["status"] = "accepted"
        accepted["adapters"]["qmd"] = {
            "eligible": False,
            "reason": "acl-aware-qmd-adapter-not-configured",
        }
        accepted_path = accepted_manifest_path(settings, page["page_id"])
        accepted_bytes = canonical_json(accepted)
        manifest_hash = digest(accepted_bytes)
        index["pages"][page["page_id"]] = {
            "preview_id": preview_id, "manifest_path": str(accepted_path), "path": page["path"],
            "rendered_hash": accepted["diff"]["rendered_hash"], "source_ids": [item["source_id"] for item in accepted["source_revisions"]],
            "status": "accepted", "qmd_eligible": accepted["adapters"]["qmd"]["eligible"],
            "manifest_hash": manifest_hash,
        }
        log_entry = canonical_json({
            "schema_version": 1, "event": "accepted", "at": format_time(at), "preview_id": preview_id,
            "page_id": page["page_id"], "operator_id": settings.operator_id,
            "manifest_hash": manifest_hash,
        })
        log_path = accepted_log_path(settings)
        journal_path = settings.state_root / "transactions" / f"{preview_id.removeprefix('sha256:')}.json"
        paths = {"target": str(target), "index": str(index_path(settings)), "log": str(log_path), "accepted_manifest": str(accepted_path)}
        backups = {key: backup(read_optional(Path(path))) for key, path in paths.items()}
        journal = {"schema_version": 1, "preview_id": preview_id, "state": "prepared", "paths": paths, "backups": backups}
        write_journal(journal_path, journal)
        maybe_crash("prepared", fault_after)
        try:
            atomic_write(target, rendered, 0o644)
            journal["state"] = "target-written"
            write_journal(journal_path, journal)
            maybe_crash("target-written", fault_after)
            atomic_write(accepted_path, accepted_bytes)
            journal["state"] = "manifest-written"
            write_journal(journal_path, journal)
            maybe_crash("manifest-written", fault_after)
            atomic_write(index_path(settings), canonical_json(index))
            journal["state"] = "index-written"
            write_journal(journal_path, journal)
            maybe_crash("index-written", fault_after)
            atomic_write(log_path, (read_optional(log_path) or b"") + log_entry)
            journal["state"] = "accepted"
            write_journal(journal_path, journal)
            maybe_crash("accepted", fault_after)
        except Exception:
            restore(target, backups["target"], 0o644)
            restore(index_path(settings), backups["index"])
            restore(log_path, backups["log"])
            restore(accepted_path, backups["accepted_manifest"])
            journal["state"] = "rolled-back"
            journal["recovery"] = "compensated-after-error"
            write_journal(journal_path, journal)
            raise
        return {"status": "applied", "preview_id": preview_id, "page": str(target), "recovered": recovered}


def status_report(settings: Settings, at: datetime) -> dict[str, Any]:
    with vault_lock(settings):
        recovered = recover_incomplete(settings)
        index = load_index(settings)
        pages = []
        for page_id, entry in sorted(index["pages"].items()):
            state = entry.get("status", "conflicting")
            reasons = []
            target = resolve_target_under(settings.output_root, entry["path"], "indexed page path")
            current = read_optional(target)
            if state == "purged":
                reasons.append("source-purged")
            elif current is None:
                state, reasons = "conflicting", ["compiled-page-missing"]
            elif digest(current) != entry["rendered_hash"]:
                state, reasons = "conflicting", ["compiled-page-changed"]
            else:
                accepted_bytes = read_optional(accepted_manifest_path_from_entry(settings, page_id, entry))
                if accepted_bytes is None:
                    state, reasons = "conflicting", ["accepted-manifest-missing"]
                    pages.append({"page_id": page_id, "path": entry["path"], "status": state, "reasons": reasons, "qmd_eligible": False})
                    continue
                if digest(accepted_bytes) != entry.get("manifest_hash"):
                    state, reasons = "conflicting", ["accepted-manifest-changed"]
                    pages.append({"page_id": page_id, "path": entry["path"], "status": state, "reasons": reasons, "qmd_eligible": False})
                    continue
                try:
                    accepted_manifest = load_accepted_manifest(settings, page_id, entry, accepted_bytes)
                except CompilerError:
                    state, reasons = "conflicting", ["accepted-manifest-invalid"]
                    pages.append({"page_id": page_id, "path": entry["path"], "status": state, "reasons": reasons, "qmd_eligible": False})
                    continue
                for source_id in entry["source_ids"]:
                    registration = load_registration(settings, source_id)
                    source_state = effective_source_status(registration, at)
                    if source_state != "active":
                        state, reasons = "stale", [f"source-{source_state}"]
                        break
                    try:
                        current_source = source_path(settings, registration["path"])
                    except CompilerError:
                        state, reasons = "stale", ["source-removed"]
                        break
                    expected = next(item["revision_hash"] for item in accepted_manifest["source_revisions"] if item["source_id"] == source_id)
                    if digest(current_source.read_bytes()) != expected:
                        state, reasons = "stale", ["source-changed"]
                        break
                else:
                    state, reasons = "clean", []
            pages.append({"page_id": page_id, "path": entry["path"], "status": state, "reasons": reasons, "qmd_eligible": False})
        preview_root = settings.state_root / "previews"
        previews = []
        if preview_root.exists():
            for path in sorted(preview_root.glob("*/manifest.json")):
                manifest = manifest_validation(load_json(path))
                previews.append({
                    "preview_id": manifest["preview"]["id"],
                    "status": "expired" if at > parse_time(manifest["preview"]["expires_at"]) else manifest["preview"]["status"],
                })
        return {"project": settings.project, "recovered_transactions": recovered, "pages": pages, "previews": previews}


def rebuild_page(settings: Settings, page_id: str, proposal_path: Path | None, at: datetime) -> dict[str, Any]:
    if proposal_path:
        return preview_source(settings, proposal_path, at)
    entry = load_index(settings)["pages"].get(require_id(page_id, "page_id"))
    if not entry or entry.get("status") == "purged":
        raise CompilerError("page has no reproducible accepted manifest")
    manifest = load_accepted_manifest(settings, page_id, entry)
    page = manifest["pages"][0]
    proposal = {
        "schema_version": 1,
        "source_id": manifest["source_revisions"][0]["source_id"],
        "page": {"page_id": page["page_id"], "path": page["path"], "title": page["title"]},
        "claims": [{
            "claim_id": claim["claim_id"], "text": claim["text"],
            "citations": [{"start_line": citation["anchor"]["start_line"], "end_line": citation["anchor"]["end_line"]} for citation in claim["citations"]],
        } for claim in page["claims"]],
        "links": page["links"],
        "contradiction_candidates": page["contradiction_candidates"],
    }
    return preview_payload(settings, canonical_json(proposal), at)


def purge_source(settings: Settings, source_id: str, confirmation: str, at: datetime) -> dict[str, Any]:
    with vault_lock(settings):
        recover_incomplete(settings)
        registration = load_registration(settings, source_id)
        expected = f"{source_id}:{registration['current_revision_hash']}"
        if confirmation != expected:
            raise CompilerError("purge confirmation must equal source_id:current_revision_hash")
        index = load_index(settings)
        affected = []
        for page_id, entry in index["pages"].items():
            if source_id not in entry["source_ids"]:
                continue
            target = resolve_target_under(settings.output_root, entry["path"], "indexed page path")
            manifest_path = accepted_manifest_path_from_entry(settings, page_id, entry)
            affected.append((page_id, entry, target, read_optional(target), manifest_path))
        source_store = authorized_absolute_path(
            str(settings.state_root / "sources" / source_id),
            settings.state_root,
            "source payload store",
        )
        tombstone_path = settings.state_root / "tombstones" / f"{source_id}.json"
        tombstone = {
            "schema_version": 1, "source_id": source_id, "project": settings.project,
            "purged_at": format_time(at), "operator_id": settings.operator_id,
            "last_revision_hash": registration["current_revision_hash"],
            "reason": "payload-and-derived-projections-not-reproducible",
        }
        atomic_write(tombstone_path, canonical_json(tombstone))
        registration["status"] = "purged"
        registration["revisions"] = []
        atomic_write(registration_path(settings, source_id), canonical_json(registration))
        suppressed, conflicts = [], []
        for page_id, entry, target, content, manifest_path in affected:
            if content is not None and digest(content) == entry["rendered_hash"] and content.startswith(f"{OWNERSHIP_PREFIX}{page_id} -->".encode()):
                target.unlink()
                suppressed.append(page_id)
            elif content is not None:
                conflicts.append(page_id)
            with contextlib.suppress(FileNotFoundError):
                manifest_path.unlink()
            entry.update({"status": "purged", "qmd_eligible": False})
        atomic_write(index_path(settings), canonical_json(index))
        if source_store.exists():
            shutil.rmtree(source_store)
        preview_root = settings.state_root / "previews"
        if preview_root.exists():
            for manifest_path in list(preview_root.glob("*/manifest.json")):
                manifest = manifest_validation(load_json(manifest_path))
                if source_id in {item["source_id"] for item in manifest["source_revisions"]}:
                    shutil.rmtree(manifest_path.parent)
        return {"status": "purged", "source_id": source_id, "suppressed_pages": suppressed, "human_edit_conflicts": conflicts, "tombstone": str(tombstone_path)}


def config_template(vault_root: str) -> dict[str, Any]:
    root = str(Path(vault_root).expanduser().resolve())
    return {
        "schema_version": 1,
        "project": {"id": "replace-project", "tenant_id": "replace-tenant", "scope_id": "replace-scope"},
        "operator_id": "replace-operator",
        "vault_root": root,
        "allowed_vault_roots": [root],
        "source_roots": ["Sources"],
        "output_root": "Compiled",
        "state_root": ".rhize/compiled-knowledge",
        "allowed_acls": ["internal", "private"],
        "allowed_egress": ["local-only"],
        "retention_classes": ["standard", "legal-hold"],
        "qmd_enabled": False,
        "preview_ttl_seconds": 3600,
        "scheduled_enabled": False,
        "live_synthesis_enabled": False,
        "context_pack_enabled": False,
        "graphify_enabled": False,
        "neo4j_enabled": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init-config", help="print a strict disabled-by-default config template")
    init.add_argument("--vault-root", required=True)
    for name in ("register", "preview", "apply", "status", "rebuild", "purge"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--now", help="fixed RFC3339 time for deterministic tests")
    register = subparsers.choices["register"]
    register.add_argument("--source", required=True)
    register.add_argument("--source-id", required=True)
    register.add_argument("--acl", action="append", required=True)
    register.add_argument("--egress", required=True)
    register.add_argument("--retention-class", required=True)
    register.add_argument("--expires-at")
    preview = subparsers.choices["preview"]
    preview.add_argument("--proposal", type=Path, required=True)
    apply = subparsers.choices["apply"]
    apply.add_argument("--preview-id", required=True)
    rebuild = subparsers.choices["rebuild"]
    rebuild.add_argument("--page-id", required=True)
    rebuild.add_argument("--proposal", type=Path)
    purge = subparsers.choices["purge"]
    purge.add_argument("--source-id", required=True)
    purge.add_argument("--confirm", required=True, help="exact source_id:current_revision_hash")
    return parser


def fail(message: str) -> NoReturn:
    print(json.dumps({"error": message}, sort_keys=True), file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init-config":
            result = config_template(args.vault_root)
        else:
            settings = load_settings(args.config)
            at = current_time(args.now)
            if args.command == "register":
                result = register_source(settings, args.source, args.source_id, args.acl, args.egress, args.retention_class, at, args.expires_at)
            elif args.command == "preview":
                result = preview_source(settings, args.proposal, at)
            elif args.command == "apply":
                result = apply_preview(settings, args.preview_id, at)
            elif args.command == "status":
                result = status_report(settings, at)
            elif args.command == "rebuild":
                result = rebuild_page(settings, args.page_id, args.proposal, at)
            elif args.command == "purge":
                result = purge_source(settings, args.source_id, args.confirm, at)
            else:  # pragma: no cover
                raise CompilerError("unsupported command")
        print(canonical_json(result).decode(), end="")
        return 0
    except (CompilerError, FileNotFoundError, PermissionError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
