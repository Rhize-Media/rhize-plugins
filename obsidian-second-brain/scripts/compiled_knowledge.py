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
from urllib.parse import quote


COMPILER_NAME = "rhize-compiled-knowledge"
COMPILER_VERSION = "1.1.0"
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
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
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


def load_settings(config_path: Path, *, initialize: bool = True) -> Settings:
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
    if initialize:
        state_root = resolve_directory_under(vault_root, raw["state_root"], "config.state_root", create=True)
        ensure_private_dir(state_root)
    else:
        relative_state = is_relative_safe(raw["state_root"], "config.state_root")
        state_root = authorized_absolute_path(str(vault_root / relative_state), vault_root, "config.state_root")
    if output_root.is_relative_to(state_root) or state_root.is_relative_to(output_root):
        raise CompilerError("output_root and state_root must not overlap")

    allowed_acls = tuple(require_string_list(raw["allowed_acls"], "config.allowed_acls"))
    allowed_egress = tuple(require_string_list(raw["allowed_egress"], "config.allowed_egress"))
    retention_classes = tuple(require_string_list(raw["retention_classes"], "config.retention_classes"))
    for gate in ("scheduled_enabled", "live_synthesis_enabled", "context_pack_enabled", "graphify_enabled", "neo4j_enabled"):
        if raw[gate] is not False:
            raise CompilerError(f"config.{gate} must remain false until implementation is available")
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
        ({"schema_version", "source_id", "page", "claims", "links", "contradiction_candidates"}
         if proposal.get("schema_version") == 1 else
         {"schema_version", "page", "claims", "links", "contradiction_candidates"}),
        "proposal",
    )
    if type(proposal["schema_version"]) is not int or proposal["schema_version"] not in {1, 2}:
        raise CompilerError("proposal.schema_version must be 1 or 2")
    if proposal["schema_version"] == 1:
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
            require_exact_keys(citation, {"start_line", "end_line"} | ({"source_id"} if proposal["schema_version"] == 2 else set()), "proposal citation")
            if proposal["schema_version"] == 2:
                require_id(citation["source_id"], "proposal citation.source_id")
            start, end = citation["start_line"], citation["end_line"]
            if type(start) is not int or type(end) is not int or start < 1 or end < start:
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
    if compiler["name"] != COMPILER_NAME or compiler["version"] not in {"1.0.0", COMPILER_VERSION}:
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


def owns_page(content: bytes, page_id: str) -> bool:
    marker = f"{OWNERSHIP_PREFIX}{page_id} -->".encode()
    # Accept legacy marker-first files only when also bound to the accepted hash.
    return content.startswith(marker + b"\n") or (
        content.startswith(b"---\n") and b"\n---\n" + marker + b"\n" in content
    )


def render_page(settings: Settings, proposal: dict[str, Any], registrations: dict[str, dict[str, Any]], citations: list[dict[str, Any]]) -> bytes:
    page = proposal["page"]
    first = next(iter(registrations.values()))
    lines = [
        "---", "type: compiled-knowledge",
        f"rhize-page-id: {json.dumps(page['page_id'])}",
        f"rhize-source-ids: {json.dumps(sorted(registrations))}",
        f"acl: {json.dumps(sorted(first['acl']), ensure_ascii=False)}",
        f"egress: {json.dumps(first['egress'])}", "status: compiled",
        "---", f"{OWNERSHIP_PREFIX}{page['page_id']} -->", "",
        f"# {page['title']}", "",
        "> [!info] Evidence-bound projection",
        "> Review the evidence before acting. Edit a separate linked note to preserve personal commentary.", "",
    ]
    for claim in citations:
        refs = " ".join(f"[^{claim['claim_id']}-{i + 1}]" for i in range(len(claim["citations"])))
        lines.extend([f"{claim['text']} {refs}", ""])
    if proposal["links"]:
        lines.extend(["## Related", ""] + [f"- [[{link}]]" for link in sorted(proposal["links"])] + [""])
    if proposal["contradiction_candidates"]:
        lines.extend(["> [!warning] Contradiction candidates", "> Human review required."])
        lines.extend(f"> - `{left}` competes with `{right}`." for left, right in proposal["contradiction_candidates"])
        lines.append("")
    lines.extend(["## Evidence", ""])
    for claim in citations:
        for i, citation in enumerate(claim["citations"], start=1):
            anchor = citation["anchor"]
            source = os.path.relpath(settings.vault_root / registrations[citation["source_id"]]["path"],
                                     (settings.output_root / page["path"]).parent)
            # Percent-encoded Markdown links avoid interpreting a source filename as wiki markup.
            lines.append(
                f"[^{claim['claim_id']}-{i}]: [Source]({quote(source, safe='/')}) "
                f"`{citation['source_id']}@{citation['revision_hash']}#L{anchor['start_line']}-L{anchor['end_line']}` "
                f"(`{anchor['content_hash']}`)"
            )
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def guard_target(settings: Settings, page: dict[str, Any], base: bytes | None) -> None:
    index = load_index(settings)
    entry = index["pages"].get(page["page_id"])
    target = resolve_target_under(settings.output_root, page["path"], "page path")
    for other_id, other in index["pages"].items():
        if other_id != page["page_id"] and (other_id.casefold() == page["page_id"].casefold() or str(resolve_target_under(settings.output_root, other["path"], "indexed path")).casefold() == str(target).casefold()):
            raise CompilerError("target path belongs to another page id")
    if entry and entry["path"] != page["path"]:
        raise CompilerError("page path changed; explicit migration required")
    if base is not None:
        if not entry or entry["status"] != "accepted" or not owns_page(base, page["page_id"]):
            raise CompilerError("target exists without matching ownership marker and accepted compiler identity")
        if digest(base) != entry["rendered_hash"]:
            raise CompilerError("target changed; refusing to overwrite human edits (including before preview)")
        load_accepted_manifest(settings, page["page_id"], entry)
    elif entry and entry["status"] == "accepted":
        raise CompilerError("accepted target missing; explicit recovery required")



def preview_source(settings: Settings, proposal_path: Path, at: datetime) -> dict[str, Any]:
    proposal_bytes = proposal_path.resolve(strict=True).read_bytes()
    try:
        raw = json.loads(proposal_bytes)
    except json.JSONDecodeError as exc:
        raise CompilerError(f"proposal is not valid JSON: {exc}") from exc
    if isinstance(raw, dict) and raw.get("schema_version") == 2 and "pages" in raw:
        return preview_batch(settings, raw, at)
    return preview_payload(settings, proposal_bytes, at)


def preview_payload(settings: Settings, proposal_bytes: bytes, at: datetime) -> dict[str, Any]:
    try:
        proposal = validate_proposal(json.loads(proposal_bytes))
    except json.JSONDecodeError as exc:
        raise CompilerError(f"proposal is not valid JSON: {exc}") from exc
    source_ids = sorted({reference.get("source_id", proposal.get("source_id"))
                         for claim in proposal["claims"] for reference in claim["citations"]})
    registrations = {source_id: load_registration(settings, source_id) for source_id in source_ids}
    source_contents = {}
    for source_id, item in registrations.items():
        if effective_source_status(item, at) != "active":
            raise CompilerError("source is not active under its retention/purge policy")
        content = source_path(settings, item["path"]).read_bytes()
        if digest(content) != item["current_revision_hash"]:
            raise CompilerError("source changed after registration; register the new revision first")
        if read_optional(snapshot_path(settings, source_id, item["current_revision_hash"])) != content:
            raise CompilerError("retained source snapshot is missing or does not match")
        try:
            source_contents[source_id] = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CompilerError("compiled sources must be UTF-8") from exc
    registration = registrations[source_ids[0]]
    policies = {canonical_json({"acl": sorted(item["acl"]), "egress": item["egress"],
                               "retention_class": item["retention_class"]}) for item in registrations.values()}
    if len(policies) != 1:
        raise CompilerError("mixed source policies require separate pages and review bundles")
    materialized_claims = []
    evidence = []
    for claim in proposal["claims"]:
        citations = []
        evidence.extend([f"\n## Claim {claim['claim_id']}\n", claim["text"] + "\n"])
        for reference in claim["citations"]:
            source_id = reference.get("source_id", proposal.get("source_id"))
            item = registrations[source_id]
            source_lines = source_contents[source_id].splitlines(keepends=True)
            start, end = reference["start_line"], reference["end_line"]
            if end > len(source_lines):
                raise CompilerError(f"claim {claim['claim_id']} cites beyond the source")
            excerpt = "".join(source_lines[start - 1:end]).encode("utf-8")
            citations.append({"source_id": source_id, "revision_hash": item["current_revision_hash"],
                              "anchor": {"start_line": start, "end_line": end, "content_hash": digest(excerpt)}})
            evidence.append(f"\nEvidence {source_id} lines {start}-{end} (untrusted quoted content):\n")
            evidence.extend("> " + line + "\n" for line in excerpt.decode().splitlines())
        materialized_claims.append({"claim_id": claim["claim_id"], "text": claim["text"], "citations": citations})

    page_relative = proposal["page"]["path"]
    target = resolve_target_under(settings.output_root, page_relative, "proposal.page.path")
    base = read_optional(target)
    marker = f"{OWNERSHIP_PREFIX}{proposal['page']['page_id']} -->".encode()
    guard_target(settings, proposal["page"], base)
    rendered = render_page(settings, proposal, registrations, materialized_claims)
    diff_text = "".join(difflib.unified_diff(
        (base or b"").decode("utf-8").splitlines(keepends=True),
        rendered.decode("utf-8").splitlines(keepends=True),
        fromfile=f"a/{page_relative}", tofile=f"b/{page_relative}",
    )).encode()
    change = (
        f"# Compiled knowledge change brief\n\n"
        f"- Page: `{page_relative}`\n"
        f"- Sources: {', '.join(source_ids)}\n"
        f"- Claims: {len(materialized_claims)}\n"
        f"- Contradiction candidates: {len(proposal['contradiction_candidates'])}\n"
        f"- Operation: {'create' if base is None else 'replace compiler-owned page'}\n"
        f"- Apply requires explicit approval of this preview id.\n"
    ).encode() + "".join(evidence).encode()
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
            "source_id": item["source_id"], "path": item["path"],
            "revision_hash": item["current_revision_hash"], "content_bytes": len(source_contents[item["source_id"]].encode()),
            "captured_at": item["captured_at"], "acl": sorted(item["acl"]), "egress": item["egress"],
            "retention_class": item["retention_class"], "status": "active",
        } for item in registrations.values()],
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
            "source_metadata_hash": digest(canonical_json(registrations)),
            "source_to_derived": {source_id: [proposal["page"]["page_id"]] for source_id in source_ids},
            "inert_content_findings": sorted({finding for content in source_contents.values() for finding in source_findings(content)}),
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
    preview_dir = authorized_absolute_path(str(settings.state_root / "previews" / preview_id.removeprefix("sha256:")), settings.state_root, "preview directory")
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
    return authorized_absolute_path(str(settings.state_root / "previews" / preview_id.removeprefix("sha256:")), settings.state_root, "preview directory")


def index_path(settings: Settings) -> Path:
    return settings.state_root / "index.json"


def accepted_log_path(settings: Settings) -> Path:
    return settings.state_root / "accepted.log.jsonl"


def accepted_manifest_path(settings: Settings, page_id: str) -> Path:
    return settings.state_root / "accepted" / f"{require_id(page_id, 'page_id')}.json"


def purge_journal_path(settings: Settings, source_id: str) -> Path:
    return settings.state_root / "purges" / f"{require_id(source_id, 'source_id')}.json"


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
    unknown = set(journal) - (required | {"recovery", "after_hashes"})
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
    if "after_hashes" in journal:
        require_exact_keys(require_object(journal["after_hashes"], "transaction after hashes"), path_keys, "transaction after hashes")
        if any(not isinstance(value, str) or not HASH_PATTERN.fullmatch(value) for value in journal["after_hashes"].values()):
            raise CompilerError("transaction after hashes are invalid")
    for key in path_keys:
        validate_backup(backups[key], f"transaction journal backups.{key}")
    return journal, validated


def check_legacy_rollback(journal: dict[str, Any], paths: dict[str, Path]) -> None:
    for key, path in paths.items():
        saved = journal["backups"][key]
        before = base64.b64decode(saved["data"]) if saved["exists"] else None
        current = read_optional(path)
        after_hash = journal.get("after_hashes", {}).get(key)
        if current != before and (current is None or digest(current) != after_hash):
            raise CompilerError(f"recovery conflict; human edits preserved at {path}; transaction remains pending")


def recover_incomplete(settings: Settings) -> list[str]:
    journal_root = settings.state_root / "transactions"
    authorized_absolute_path(str(journal_root), settings.state_root, "transaction journal root")
    recovered = []
    for path in sorted(journal_root.glob("*.json")):
        journal, paths = validate_journal(settings, path, load_json(path))
        if journal.get("state") in {"accepted", "rolled-back"}:
            continue
        backups = journal["backups"]
        check_legacy_rollback(journal, paths)
        restore(paths["target"], backups["target"], 0o644)
        restore(paths["index"], backups["index"])
        restore(paths["log"], backups["log"])
        restore(paths["accepted_manifest"], backups["accepted_manifest"])
        journal["state"] = "rolled-back"
        journal["recovery"] = "restored-pre-transaction-bytes"
        journal["backups"] = {key: backup(None) for key in journal["backups"]}
        write_journal(path, journal)
        recovered.append(path.stem)
    recovered.extend(recover_batches(settings))
    recovered.extend(recover_incomplete_purges(settings))
    return recovered


def maybe_crash(point: str, fault_after: str | None) -> None:
    if fault_after == point:
        raise InjectedCrash(point)


def apply_preview(settings: Settings, preview_id: str, at: datetime, fault_after: str | None = None) -> dict[str, Any]:
    if batch_dir(settings, preview_id).exists():
        return apply_batch(settings, preview_id, at, fault_after)
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
        validate_current_sources(settings, manifest, at)
        guard_target(settings, page, current)
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
        journal = {"schema_version": 1, "preview_id": preview_id, "state": "prepared", "paths": paths, "backups": backups,
                   "after_hashes": {"target": digest(rendered), "accepted_manifest": digest(accepted_bytes),
                                    "index": digest(canonical_json(index)),
                                    "log": digest((read_optional(log_path) or b"") + log_entry)}}
        write_journal(journal_path, journal)
        maybe_crash("prepared", fault_after)
        try:
            if read_optional(target) != current:
                raise CompilerError("target changed during apply")
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
            journal["backups"] = {key: backup(None) for key in journal["backups"]}
            write_journal(journal_path, journal)
            maybe_crash("accepted", fault_after)
        except Exception:
            check_legacy_rollback(journal, {key: Path(value) for key, value in paths.items()})
            restore(target, backups["target"], 0o644)
            restore(index_path(settings), backups["index"])
            restore(log_path, backups["log"])
            restore(accepted_path, backups["accepted_manifest"])
            journal["state"] = "rolled-back"
            journal["recovery"] = "compensated-after-error"
            journal["backups"] = {key: backup(None) for key in journal["backups"]}
            write_journal(journal_path, journal)
            raise
        return {"status": "applied", "preview_id": preview_id, "page": str(target), "recovered": recovered}


def status_report(settings: Settings, at: datetime) -> dict[str, Any]:
    with vault_lock(settings):
        return page_report(settings, at, recover_incomplete(settings))


def inspect_report(settings: Settings, at: datetime) -> dict[str, Any]:
    """Observe existing state without mkdir, chmod, journal recovery or new lock files."""
    lock = authorized_absolute_path(str(settings.state_root / "compiler.lock"), settings.state_root, "inspection lock")
    if not lock.exists():
        return {"project": settings.project, "inspection": "uninitialized", "pages": [], "pending_transactions": []}
    with lock.open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"project": settings.project, "inspection": "busy", "pages": []}
        try:
            pending = []
            for folder, terminal in (("transactions", {"accepted", "rolled-back"}),
                                     ("batch-transactions", {"accepted", "rolled-back"}), ("purges", {"purged"})):
                root = authorized_absolute_path(str(settings.state_root / folder), settings.state_root, "inspection journals")
                for path in sorted(root.glob("*.json")):
                    authorized_absolute_path(str(path), settings.state_root, "inspection journal")
                    if load_json(path).get("state") not in terminal:
                        pending.append(f"{folder}/{path.name}")
            if pending:
                return {"project": settings.project, "inspection": "recovery-required", "pages": [], "pending_transactions": pending}
            result = page_report(settings, at, [])
            result["inspection"] = "observed"
            return result
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def page_report(settings: Settings, at: datetime, recovered: list[str]) -> dict[str, Any]:
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
            try:
                validate_current_sources(settings, accepted_manifest, at)
            except (CompilerError, OSError):
                # Preserve the specific missing/expired/changed reason in the existing loop below.
                source_metadata_changed = True
            else:
                source_metadata_changed = False
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
                state, reasons = ("stale", ["source-policy-or-snapshot-changed"]) if source_metadata_changed else ("clean", [])
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
    batches = []
    for path in sorted((settings.state_root / "batches").glob("*/batch.json")):
        batch, children = load_batch(settings, load_json(path)["batch_id"])
        accepted = sum(index["pages"].get(child["pages"][0]["page_id"], {}).get("preview_id") == child["preview"]["id"] for child in children)
        batches.append({"batch_id": batch["batch_id"], "pages": len(children), "accepted_pages": accepted,
                        "status": "accepted" if accepted == len(children) else
                        ("expired" if at > parse_time(batch["expires_at"]) else "preview")})
    return {"project": settings.project, "recovered_transactions": recovered, "pages": pages, "previews": previews, "batches": batches}


def rebuild_page(settings: Settings, page_id: str, proposal_path: Path | None, at: datetime) -> dict[str, Any]:
    if proposal_path:
        return preview_source(settings, proposal_path, at)
    entry = load_index(settings)["pages"].get(require_id(page_id, "page_id"))
    if not entry or entry.get("status") == "purged":
        raise CompilerError("page has no reproducible accepted manifest")
    manifest = load_accepted_manifest(settings, page_id, entry)
    page = manifest["pages"][0]
    validate_current_sources(settings, manifest, at)
    proposal = {
        "schema_version": 2,
        "page": {"page_id": page["page_id"], "path": page["path"], "title": page["title"]},
        "claims": [{
            "claim_id": claim["claim_id"], "text": claim["text"],
            "citations": [{"source_id": citation["source_id"], "start_line": citation["anchor"]["start_line"], "end_line": citation["anchor"]["end_line"]} for citation in claim["citations"]],
        } for claim in page["claims"]],
        "links": page["links"],
        "contradiction_candidates": page["contradiction_candidates"],
    }
    return preview_payload(settings, canonical_json(proposal), at)


def validate_current_sources(settings: Settings, manifest: dict[str, Any], at: datetime) -> None:
    registrations = {}
    for source_revision in manifest["source_revisions"]:
        registration = load_registration(settings, source_revision["source_id"])
        registrations[registration["source_id"]] = registration
        contract = {"source_id": registration["source_id"], "path": registration["path"],
                    "revision_hash": registration["current_revision_hash"], "captured_at": registration["captured_at"],
                    "acl": sorted(registration["acl"]), "egress": registration["egress"],
                    "retention_class": registration["retention_class"]}
        if (effective_source_status(registration, at) != "active"
                or contract != {key: source_revision[key] for key in contract}
                or any(manifest["policy"][key] != contract[key] for key in ("acl", "egress", "retention_class"))):
            raise CompilerError("source state changed after preview")
        content = source_path(settings, registration["path"]).read_bytes()
        if digest(content) != source_revision["revision_hash"]:
            raise CompilerError("canonical source changed after preview")
        if read_optional(snapshot_path(settings, registration["source_id"], source_revision["revision_hash"])) != content:
            raise CompilerError("retained source snapshot is missing or does not match")
    metadata = registrations
    if manifest["compiler"]["version"] == "1.0.0":
        if len(registrations) != 1:
            raise CompilerError("legacy compiler manifest must have one source")
        metadata = next(iter(registrations.values()))
    if digest(canonical_json(metadata)) != manifest["provenance"]["source_metadata_hash"]:
        raise CompilerError("source metadata changed after preview")


def batch_dir(settings: Settings, batch_id: str) -> Path:
    if not isinstance(batch_id, str) or not HASH_PATTERN.fullmatch(batch_id):
        raise CompilerError("batch id must be a sha256 digest")
    return authorized_absolute_path(str(settings.state_root / "batches" / batch_id.removeprefix("sha256:")),
                                    settings.state_root, "batch directory")


def preview_batch(settings: Settings, raw: Any, at: datetime) -> dict[str, Any]:
    require_exact_keys(raw, {"schema_version", "pages"}, "batch proposal")
    pages = raw["pages"]
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 2 or not isinstance(pages, list) or not 1 <= len(pages) <= 100:
        raise CompilerError("v2 proposal requires 1 to 100 pages")
    proposals, ids, targets = [], set(), set()
    for page in pages:
        page = require_object(page, "batch page")
        require_exact_keys(page, {"page_id", "path", "title", "claims", "links", "contradiction_candidates"}, "batch page")
        proposal = validate_proposal({"schema_version": 2,
                    "page": {key: page[key] for key in ("page_id", "path", "title")},
                    **{key: page[key] for key in ("claims", "links", "contradiction_candidates")}})
        target = resolve_target_under(settings.output_root, page["path"], "batch page path")
        # Portable vaults must also be safe on case-insensitive macOS filesystems.
        if page["page_id"].casefold() in ids or str(target).casefold() in targets:
            raise CompilerError("duplicate batch page id or target path")
        ids.add(page["page_id"].casefold())
        targets.add(str(target).casefold())
        proposals.append(proposal)
    results = [preview_payload(settings, canonical_json(proposal), at) for proposal in proposals]
    manifests = [manifest_validation(load_json(Path(result["preview_dir"]) / "manifest.json")) for result in results]
    if len({canonical_json(manifest["policy"]) for manifest in manifests}) != 1:
        raise CompilerError("mixed source policies require separate review bundles")
    review = ["# Batch review\n\nReview every page and its cited evidence. Hashes prove byte provenance, not semantic truth.\n"]
    for result, manifest in zip(results, manifests):
        directory = Path(result["preview_dir"])
        review.append(f"\n## {manifest['pages'][0]['path']}\nPreview: `{result['preview_id']}`\n\n")
        review.append((directory / "change-brief.md").read_text())
        review.append("\n### Proposed diff (quoted, inert)\n")
        review.extend("> " + line + "\n" for line in (directory / "diff.patch").read_text().splitlines())
    review_bytes = "".join(review).encode()
    batch = {"schema_version": 2, "project": settings.project, "operator_id": settings.operator_id,
             "created_at": format_time(at), "expires_at": min(result["expires_at"] for result in results),
             "preview_ids": [result["preview_id"] for result in results], "review_hash": digest(review_bytes)}
    batch_id = digest(canonical_json(batch))
    batch["batch_id"] = batch_id
    directory = batch_dir(settings, batch_id)
    with vault_lock(settings):
        recover_incomplete(settings)
        # Recheck all dependencies under one lock after producing the per-page previews.
        for manifest in manifests:
            validate_current_sources(settings, manifest, at)
            page = manifest["pages"][0]
            current = read_optional(resolve_target_under(settings.output_root, page["path"], "batch target"))
            guard_target(settings, page, current)
            if (digest(current) if current is not None else None) != manifest["diff"]["base_hash"]:
                raise CompilerError("target changed while building batch review")
        atomic_write(directory / "batch.json", canonical_json(batch))
        atomic_write(directory / "review.md", review_bytes)
    return {"preview_id": batch_id, "batch_id": batch_id, "preview_dir": str(directory),
            "review": str(directory / "review.md"), "pages": len(results),
            "sources": len({item["source_id"] for manifest in manifests for item in manifest["source_revisions"]}),
            "expires_at": batch["expires_at"], "child_previews": batch["preview_ids"]}


def load_batch(settings: Settings, batch_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    directory = batch_dir(settings, batch_id)
    batch = require_object(load_json(directory / "batch.json"), "batch")
    require_exact_keys(batch, {"schema_version", "project", "operator_id", "created_at", "expires_at", "preview_ids", "review_hash", "batch_id"}, "batch")
    payload = {key: value for key, value in batch.items() if key != "batch_id"}
    if (batch["schema_version"] != 2 or batch["batch_id"] != batch_id or digest(canonical_json(payload)) != batch_id
            or batch["project"] != settings.project or batch["operator_id"] != settings.operator_id):
        raise CompilerError("batch identity/project/operator mismatch")
    parse_time(batch["created_at"])
    parse_time(batch["expires_at"])
    ids = batch["preview_ids"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(item, str) or not HASH_PATTERN.fullmatch(item) for item in ids) or len(set(ids)) != len(ids):
        raise CompilerError("invalid batch preview ids")
    if digest((directory / "review.md").read_bytes()) != batch["review_hash"]:
        raise CompilerError("batch review artifact changed")
    manifests, targets, page_ids, policies = [], set(), set(), set()
    for preview_id in ids:
        manifest = manifest_validation(load_json(preview_dir(settings, preview_id) / "manifest.json"))
        validate_preview_identity(manifest)
        if (manifest["preview"]["id"] != preview_id or manifest["project"] != settings.project
                or manifest["operator_id"] != settings.operator_id):
            raise CompilerError("batch child authority mismatch")
        page = manifest["pages"][0]
        target = str(resolve_target_under(settings.output_root, page["path"], "batch target")).casefold()
        if target in targets or page["page_id"].casefold() in page_ids:
            raise CompilerError("duplicate batch page identity/path")
        targets.add(target)
        page_ids.add(page["page_id"].casefold())
        policies.add(canonical_json(manifest["policy"]))
        manifests.append(manifest)
    if len(policies) != 1:
        raise CompilerError("mixed source policies in batch")
    return batch, manifests


def accepted_projection(manifest: dict[str, Any]) -> bytes:
    accepted = json.loads(json.dumps(manifest))
    accepted["preview"]["status"] = "accepted"
    accepted["adapters"]["qmd"] = {"eligible": False, "reason": "acl-aware-qmd-adapter-not-configured"}
    return canonical_json(accepted)


def batch_operations(settings: Settings, manifests: list[dict[str, Any]], index: dict[str, Any], log: bytes,
                     at: datetime) -> list[tuple[Path, bytes, int]]:
    operations = []
    for manifest in manifests:
        page = manifest["pages"][0]
        preview_id = manifest["preview"]["id"]
        directory = preview_dir(settings, preview_id)
        rendered = (directory / "page.md").read_bytes()
        accepted = accepted_projection(manifest)
        accepted_path = accepted_manifest_path(settings, page["page_id"])
        operations.extend([(resolve_target_under(settings.output_root, page["path"], "batch target"), rendered, 0o644),
                           (accepted_path, accepted, 0o600)])
        index["pages"][page["page_id"]] = {
            "preview_id": preview_id, "manifest_path": str(accepted_path), "path": page["path"],
            "rendered_hash": manifest["diff"]["rendered_hash"],
            "source_ids": [item["source_id"] for item in manifest["source_revisions"]],
            "status": "accepted", "qmd_eligible": False, "manifest_hash": digest(accepted)}
        log += canonical_json({"schema_version": 1, "event": "accepted", "at": format_time(at),
                               "preview_id": preview_id, "page_id": page["page_id"],
                               "operator_id": settings.operator_id, "manifest_hash": digest(accepted)})
    operations.extend([(index_path(settings), canonical_json(index), 0o600), (accepted_log_path(settings), log, 0o600)])
    return operations


def write_batch_journal(path: Path, journal: dict[str, Any]) -> None:
    journal.pop("integrity", None)
    journal["integrity"] = digest(canonical_json(journal))
    write_journal(path, journal)


def validate_batch_journal(settings: Settings, path: Path) -> dict[str, Any]:
    journal = require_object(load_json(path), "batch journal")
    require_exact_keys(journal, {"schema_version", "batch_id", "project", "operator_id", "at", "state", "operations", "integrity"}, "batch journal")
    batch_dir(settings, journal["batch_id"])
    payload = {key: value for key, value in journal.items() if key != "integrity"}
    if (journal["schema_version"] != 2 or digest(canonical_json(payload)) != journal["integrity"]
            or journal["project"] != settings.project or journal["operator_id"] != settings.operator_id
            or journal["state"] not in {"prepared", "accepted", "rolled-back"}
            or path.name != f"{journal['batch_id'].removeprefix('sha256:')}.json"):
        raise CompilerError("batch journal identity/integrity mismatch")
    batch_dir(settings, journal["batch_id"])
    authorized_absolute_path(str(path), settings.state_root, "batch journal path",
                             expected=settings.state_root / "batch-transactions" / path.name)
    if journal["state"] in {"accepted", "rolled-back"}:
        if journal["operations"] != []:
            raise CompilerError("terminal batch journal must not retain payload backups")
        return journal
    _, manifests = load_batch(settings, journal["batch_id"])
    operations = journal["operations"]
    if not isinstance(operations, list) or len(operations) != len(manifests) * 2 + 2:
        raise CompilerError("batch journal operations mismatch")
    for operation in operations:
        require_exact_keys(require_object(operation, "operation"), {"path", "mode", "before", "after_hash"}, "operation")
        validate_backup(operation["before"], "operation backup")
    def saved_bytes(operation: dict[str, Any]) -> bytes | None:
        saved = operation["before"]
        return base64.b64decode(saved["data"]) if saved["exists"] else None
    index_bytes = saved_bytes(operations[-2])
    index = json.loads(index_bytes) if index_bytes is not None else {"schema_version": 1, "project": settings.project, "pages": {}}
    if index.get("schema_version") != 1 or index.get("project") != settings.project or not isinstance(index.get("pages"), dict):
        raise CompilerError("invalid batch index backup")
    for page_id, entry in index["pages"].items():
        validate_index_entry(settings, page_id, entry)
    expected = batch_operations(settings, manifests, index, saved_bytes(operations[-1]) or b"", parse_time(journal["at"]))
    for operation, (target, content, mode) in zip(operations, expected):
        authorized_absolute_path(operation["path"], settings.vault_root, "batch operation", expected=target)
        if operation["mode"] != mode or operation["after_hash"] != digest(content):
            raise CompilerError("batch operation does not match preview authority")
    return journal


def rollback_batch(settings: Settings, path: Path, journal: dict[str, Any]) -> None:
    # Check every operation first. No recovery write is allowed to overwrite an external edit.
    for operation in journal["operations"]:
        current = read_optional(Path(operation["path"]))
        before = operation["before"]
        before_bytes = base64.b64decode(before["data"]) if before["exists"] else None
        if current != before_bytes and (current is None or digest(current) != operation["after_hash"]):
            raise CompilerError(f"recovery conflict; human edits preserved at {operation['path']}; transaction remains pending")
    for operation in reversed(journal["operations"]):
        restore(Path(operation["path"]), operation["before"], operation["mode"])
    journal["state"], journal["operations"] = "rolled-back", []
    write_batch_journal(path, journal)


def recover_batches(settings: Settings) -> list[str]:
    root = authorized_absolute_path(str(settings.state_root / "batch-transactions"), settings.state_root, "batch journal root")
    recovered = []
    for path in sorted(root.glob("*.json")):
        journal = validate_batch_journal(settings, path)
        if journal["state"] == "prepared":
            rollback_batch(settings, path, journal)
            recovered.append(f"batch:{journal['batch_id']}")
    return recovered


def apply_batch(settings: Settings, batch_id: str, at: datetime, fault_after: str | None = None) -> dict[str, Any]:
    with vault_lock(settings):
        recovered = recover_incomplete(settings)
        batch, manifests = load_batch(settings, batch_id)
        index = load_index(settings)
        noops = []
        for manifest in manifests:
            page = manifest["pages"][0]
            directory = preview_dir(settings, manifest["preview"]["id"])
            for name, key in (("page.md", "rendered_hash"), ("diff.patch", "unified_diff_hash"), ("change-brief.md", "change_brief_hash")):
                if digest((directory / name).read_bytes()) != manifest["diff"][key]:
                    raise CompilerError("preview artifacts no longer match the manifest")
            current = read_optional(resolve_target_under(settings.output_root, page["path"], "batch target"))
            entry = index["pages"].get(page["page_id"])
            is_noop = bool(entry and entry["status"] == "accepted" and entry["preview_id"] == manifest["preview"]["id"]
                           and current is not None and digest(current) == manifest["diff"]["rendered_hash"])
            noops.append(is_noop)
            if is_noop:
                load_accepted_manifest(settings, page["page_id"], entry)
                continue
            if at > parse_time(manifest["preview"]["expires_at"]):
                raise CompilerError("preview expired; rebuild a new preview")
            validate_current_sources(settings, manifest, at)
            guard_target(settings, page, current)
            if (digest(current) if current is not None else None) != manifest["diff"]["base_hash"]:
                raise CompilerError("target changed after preview; refusing to overwrite human edits")
        if all(noops):
            return {"status": "noop", "preview_id": batch_id, "pages": len(manifests), "recovered": recovered}
        if any(noops):
            raise CompilerError("batch partly applied individually; create a fresh batch review")
        if at > parse_time(batch["expires_at"]):
            raise CompilerError("batch preview expired")
        operations = batch_operations(settings, manifests, index, read_optional(accepted_log_path(settings)) or b"", at)
        journal_path = settings.state_root / "batch-transactions" / f"{batch_id.removeprefix('sha256:')}.json"
        journal = {"schema_version": 2, "batch_id": batch_id, "project": settings.project,
                   "operator_id": settings.operator_id, "at": format_time(at), "state": "prepared",
                   "operations": [{"path": str(path), "mode": mode, "before": backup(read_optional(path)),
                                   "after_hash": digest(content)} for path, content, mode in operations]}
        write_batch_journal(journal_path, journal)
        maybe_crash("batch-prepared", fault_after)
        try:
            for i, ((path, content, mode), operation) in enumerate(zip(operations, journal["operations"])):
                # Detect changes after preflight too, including Obsidian writes that ignore our lock.
                if backup(read_optional(path)) != operation["before"]:
                    raise CompilerError("target changed during batch apply")
                atomic_write(path, content, mode)
                maybe_crash(f"batch-write-{i + 1}", fault_after)
            journal["state"], journal["operations"] = "accepted", []
            write_batch_journal(journal_path, journal)
            maybe_crash("batch-accepted", fault_after)
        except Exception:
            rollback_batch(settings, journal_path, validate_batch_journal(settings, journal_path))
            raise
        return {"status": "applied", "preview_id": batch_id, "pages": len(manifests), "recovered": recovered}


def purge_batch_artifacts(settings: Settings, source_id: str, preview_ids: set[str], page_paths: set[str]) -> None:
    root = authorized_absolute_path(str(settings.state_root / "batches"), settings.state_root, "batch root")
    for path in sorted(root.glob("*/batch.json")):
        raw = load_json(path)
        batch_id = raw.get("batch_id")
        batch, _ = load_batch(settings, batch_id)
        if path.parent != batch_dir(settings, batch_id):
            raise CompilerError("batch purge path mismatch")
        if preview_ids.intersection(batch["preview_ids"]):
            shutil.rmtree(path.parent)
    # Legacy transactions retain rollback payloads after commit. Remove completed affected journals.
    for path in sorted((settings.state_root / "transactions").glob("*.json")):
        journal, paths = validate_journal(settings, path, load_json(path))
        if journal["state"] not in {"accepted", "rolled-back"}:
            raise CompilerError("cannot purge with pending transaction")
        saved_manifest = journal["backups"]["accepted_manifest"]
        old_dependencies = set()
        if saved_manifest["exists"]:
            try:
                prior = json.loads(base64.b64decode(saved_manifest["data"]))
                old_dependencies = {item["source_id"] for item in prior["source_revisions"]}
            except (ValueError, KeyError, TypeError) as exc:
                raise CompilerError("cannot establish source dependencies of legacy backup") from exc
        if (journal["preview_id"] in preview_ids or source_id in old_dependencies
                or paths["target"].relative_to(settings.output_root).as_posix() in page_paths):
            path.unlink()


PURGE_STATES = (
    "prepared",
    "targets-deleted",
    "accepted-manifests-deleted",
    "previews-deleted",
    "source-store-deleted",
    "tombstone-written",
    "index-written",
    "purged",
)


def matching_preview_ids(settings: Settings, source_id: str) -> list[str]:
    preview_root = settings.state_root / "previews"
    matching = []
    for manifest_path in sorted(preview_root.glob("*/manifest.json")):
        manifest = manifest_validation(load_json(manifest_path))
        validate_preview_identity(manifest)
        preview_id = manifest["preview"]["id"]
        if (
            manifest["project"] != settings.project
            or manifest["operator_id"] != settings.operator_id
            or manifest_path.parent != preview_dir(settings, preview_id)
        ):
            raise CompilerError("preview does not match purge project/operator authority")
        if source_id in {item["source_id"] for item in manifest["source_revisions"]}:
            matching.append(preview_id)
    return matching


def validate_purge_journal(
    settings: Settings,
    path: Path,
    raw_journal: Any,
) -> tuple[dict[str, Any], dict[str, Path]]:
    authorized_absolute_path(
        str(path),
        settings.state_root,
        "purge journal path",
        expected=purge_journal_path(settings, path.stem),
    )
    journal = require_object(raw_journal, "purge journal")
    require_exact_keys(
        journal,
        {
            "schema_version", "source_id", "project", "operator_id", "confirmation_revision_hash",
            "purged_at", "state", "paths", "pages", "preview_ids", "raw_source_retained",
        },
        "purge journal",
    )
    source_id = require_id(journal.get("source_id"), "purge journal source_id")
    revision_hash = journal.get("confirmation_revision_hash")
    if (
        journal.get("schema_version") != 1
        or source_id != path.stem
        or journal.get("project") != settings.project
        or journal.get("operator_id") != settings.operator_id
        or not isinstance(revision_hash, str)
        or not HASH_PATTERN.fullmatch(revision_hash)
        or journal.get("state") not in PURGE_STATES
    ):
        raise CompilerError(f"purge journal {path.name} has invalid identity/state")
    raw_source_retained = journal.get("raw_source_retained")
    if raw_source_retained is not None and not isinstance(raw_source_retained, bool):
        raise CompilerError("purge journal raw_source_retained must be boolean or null")
    if (
        PURGE_STATES.index(journal["state"]) >= PURGE_STATES.index("tombstone-written")
        and not isinstance(raw_source_retained, bool)
    ):
        raise CompilerError("terminal purge journal requires source-retention evidence")
    parse_time(require_string(journal.get("purged_at"), "purge journal purged_at"))

    paths = require_object(journal["paths"], "purge journal paths")
    require_exact_keys(paths, {"registration", "index", "tombstone", "source_store"}, "purge journal paths")
    validated_paths = {
        "registration": authorized_absolute_path(
            paths["registration"], settings.state_root, "purge registration path",
            expected=registration_path(settings, source_id),
        ),
        "index": authorized_absolute_path(
            paths["index"], settings.state_root, "purge index path", expected=index_path(settings),
        ),
        "tombstone": authorized_absolute_path(
            paths["tombstone"], settings.state_root, "purge tombstone path",
            expected=settings.state_root / "tombstones" / f"{source_id}.json",
        ),
        "source_store": authorized_absolute_path(
            paths["source_store"], settings.state_root, "purge source payload store",
            expected=settings.state_root / "sources" / source_id,
        ),
    }

    pages = journal.get("pages")
    if not isinstance(pages, list):
        raise CompilerError("purge journal pages must be an array")
    page_ids = []
    allowed_dispositions = {"owned", "suppressed", "conflict", "absent"}
    for index, raw_page in enumerate(pages):
        page = require_object(raw_page, f"purge journal pages[{index}]")
        require_exact_keys(
            page,
            {"page_id", "path", "target", "accepted_manifest", "rendered_hash", "disposition"},
            f"purge journal pages[{index}]",
        )
        page_id = require_id(page.get("page_id"), f"purge journal pages[{index}].page_id")
        page_ids.append(page_id)
        expected_target = resolve_target_under(
            settings.output_root, page.get("path"), f"purge journal pages[{index}].path"
        )
        authorized_absolute_path(
            page.get("target"), settings.output_root, f"purge journal pages[{index}].target",
            expected=expected_target,
        )
        authorized_absolute_path(
            page.get("accepted_manifest"), settings.state_root,
            f"purge journal pages[{index}].accepted_manifest",
            expected=accepted_manifest_path(settings, page_id),
        )
        if not isinstance(page.get("rendered_hash"), str) or not HASH_PATTERN.fullmatch(page["rendered_hash"]):
            raise CompilerError(f"purge journal pages[{index}].rendered_hash is invalid")
        if page.get("disposition") not in allowed_dispositions:
            raise CompilerError(f"purge journal pages[{index}].disposition is invalid")
    if len(page_ids) != len(set(page_ids)):
        raise CompilerError("purge journal page ids must be unique")

    preview_ids = journal.get("preview_ids")
    if (
        not isinstance(preview_ids, list)
        or len(preview_ids) != len(set(preview_ids))
        or any(not isinstance(value, str) or not HASH_PATTERN.fullmatch(value) for value in preview_ids)
    ):
        raise CompilerError("purge journal preview_ids are invalid")
    return journal, validated_paths


def purge_result(journal: dict[str, Any], tombstone_path: Path) -> dict[str, Any]:
    return {
        "status": "purged",
        "source_id": journal["source_id"],
        "suppressed_pages": sorted(
            page["page_id"] for page in journal["pages"] if page["disposition"] == "suppressed"
        ),
        "human_edit_conflicts": sorted(
            page["page_id"] for page in journal["pages"] if page["disposition"] == "conflict"
        ),
        "tombstone": str(tombstone_path),
        # Historical observation at the terminal purge boundary; the compiler never deletes this source.
        "rawSourceRetained": journal["raw_source_retained"],
    }


def advance_purge(
    journal_path: Path,
    journal: dict[str, Any],
    state: str,
    fault_after: str | None,
    fault_point: str | None = None,
) -> None:
    journal["state"] = state
    write_journal(journal_path, journal)
    maybe_crash(fault_point or f"purge-{state}", fault_after)


def complete_purge(
    settings: Settings,
    journal_path: Path,
    journal: dict[str, Any],
    paths: dict[str, Path],
    fault_after: str | None = None,
) -> dict[str, Any]:
    def reached(state: str) -> bool:
        return PURGE_STATES.index(journal["state"]) >= PURGE_STATES.index(state)

    if not reached("targets-deleted"):
        for page in journal["pages"]:
            target = Path(page["target"])
            if page["disposition"] == "owned":
                content = read_optional(target)
                if content is None:
                    page["disposition"] = "suppressed"
                elif (
                    digest(content) == page["rendered_hash"]
                    and owns_page(content, page["page_id"])
                ):
                    target.unlink()
                    page["disposition"] = "suppressed"
                else:
                    page["disposition"] = "conflict"
                write_journal(journal_path, journal)
        advance_purge(journal_path, journal, "targets-deleted", fault_after)

    if not reached("accepted-manifests-deleted"):
        for page in journal["pages"]:
            with contextlib.suppress(FileNotFoundError):
                Path(page["accepted_manifest"]).unlink()
        advance_purge(journal_path, journal, "accepted-manifests-deleted", fault_after)

    if not reached("previews-deleted"):
        for preview_id in matching_preview_ids(settings, journal["source_id"]):
            if preview_id not in journal["preview_ids"]:
                journal["preview_ids"].append(preview_id)
                journal["preview_ids"].sort()
                write_journal(journal_path, journal)
        purge_batch_artifacts(settings, journal["source_id"], set(journal["preview_ids"]), {page["path"] for page in journal["pages"]})
        for preview_id in journal["preview_ids"]:
            directory = preview_dir(settings, preview_id)
            if directory.exists():
                shutil.rmtree(directory)
        advance_purge(journal_path, journal, "previews-deleted", fault_after)

    if not reached("source-store-deleted"):
        if paths["source_store"].exists():
            shutil.rmtree(paths["source_store"])
        if paths["source_store"].exists():
            raise CompilerError("source payload store still exists after authorized deletion")
        advance_purge(journal_path, journal, "source-store-deleted", fault_after)

    if not reached("tombstone-written"):
        if paths["source_store"].exists() or any(
            Path(page["accepted_manifest"]).exists() for page in journal["pages"]
        ) or any(preview_dir(settings, preview_id).exists() for preview_id in journal["preview_ids"]):
            raise CompilerError("purge cannot commit terminal state while compiler payloads remain")
        registration = load_registration(settings, journal["source_id"])
        try:
            canonical_source = source_path(settings, registration["path"])
        except CompilerError:
            raw_source_retained = False
        else:
            raw_source_retained = canonical_source.is_file()
        journal["raw_source_retained"] = raw_source_retained
        write_journal(journal_path, journal)
        tombstone = {
            "schema_version": 1,
            "source_id": journal["source_id"],
            "project": settings.project,
            "purged_at": journal["purged_at"],
            "operator_id": settings.operator_id,
            "last_revision_hash": journal["confirmation_revision_hash"],
            "reason": "payload-and-derived-projections-not-reproducible",
            "rawSourceRetained": raw_source_retained,
        }
        atomic_write(paths["tombstone"], canonical_json(tombstone))
        advance_purge(journal_path, journal, "tombstone-written", fault_after)

    if not reached("index-written"):
        index = load_index(settings)
        for page in journal["pages"]:
            page_id = page["page_id"]
            entry = index["pages"].get(page_id)
            if (
                entry is None
                or journal["source_id"] not in entry["source_ids"]
                or entry["path"] != page["path"]
                or entry["rendered_hash"] != page["rendered_hash"]
                or accepted_manifest_path_from_entry(settings, page_id, entry) != Path(page["accepted_manifest"])
            ):
                raise CompilerError("purge index changed after authorization")
            entry.update({"status": "purged", "qmd_eligible": False})
        atomic_write(paths["index"], canonical_json(index))
        advance_purge(journal_path, journal, "index-written", fault_after)

    if not reached("purged"):
        registration = load_registration(settings, journal["source_id"])
        if registration["current_revision_hash"] != journal["confirmation_revision_hash"]:
            raise CompilerError("source revision changed after purge authorization")
        registration["status"] = "purged"
        registration["revisions"] = []
        atomic_write(paths["registration"], canonical_json(registration))
        advance_purge(journal_path, journal, "purged", fault_after, "purge-registration-written")
    return purge_result(journal, paths["tombstone"])


def recover_incomplete_purges(settings: Settings) -> list[str]:
    journal_root = settings.state_root / "purges"
    authorized_absolute_path(str(journal_root), settings.state_root, "purge journal root")
    recovered = []
    for path in sorted(journal_root.glob("*.json")):
        journal, paths = validate_purge_journal(settings, path, load_json(path))
        if journal["state"] == "purged":
            continue
        complete_purge(settings, path, journal, paths)
        recovered.append(f"purge:{journal['source_id']}")
    return recovered


def purge_source(
    settings: Settings,
    source_id: str,
    confirmation: str,
    at: datetime,
    fault_after: str | None = None,
) -> dict[str, Any]:
    with vault_lock(settings):
        recover_incomplete(settings)
        journal_path = purge_journal_path(settings, source_id)
        if journal_path.exists():
            journal, paths = validate_purge_journal(settings, journal_path, load_json(journal_path))
            expected = f"{source_id}:{journal['confirmation_revision_hash']}"
            if confirmation != expected:
                raise CompilerError("purge confirmation must equal source_id:current_revision_hash")
            if journal["state"] != "purged":
                result = complete_purge(settings, journal_path, journal, paths, fault_after)
            else:
                result = purge_result(journal, paths["tombstone"])
            return result

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
            content = read_optional(target)
            owned = content is not None and digest(content) == entry["rendered_hash"] and owns_page(content, page_id)
            affected.append({
                "page_id": page_id,
                "path": entry["path"],
                "target": str(target),
                "accepted_manifest": str(manifest_path),
                "rendered_hash": entry["rendered_hash"],
                "disposition": "owned" if owned else ("conflict" if content is not None else "absent"),
            })
        source_store = authorized_absolute_path(
            str(settings.state_root / "sources" / source_id),
            settings.state_root,
            "source payload store",
        )
        tombstone_path = settings.state_root / "tombstones" / f"{source_id}.json"
        journal = {
            "schema_version": 1,
            "source_id": source_id,
            "project": settings.project,
            "operator_id": settings.operator_id,
            "confirmation_revision_hash": registration["current_revision_hash"],
            "purged_at": format_time(at),
            "state": "prepared",
            "paths": {
                "registration": str(registration_path(settings, source_id)),
                "index": str(index_path(settings)),
                "tombstone": str(tombstone_path),
                "source_store": str(source_store),
            },
            "pages": affected,
            "preview_ids": matching_preview_ids(settings, source_id),
            "raw_source_retained": None,
        }
        advance_purge(journal_path, journal, "prepared", fault_after)
        validated_journal, paths = validate_purge_journal(settings, journal_path, journal)
        return complete_purge(settings, journal_path, validated_journal, paths, fault_after)


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
    for name in ("register", "preview", "apply", "status", "inspect", "rebuild", "purge"):
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
            settings = load_settings(args.config, initialize=args.command != "inspect")
            at = current_time(args.now)
            if args.command == "register":
                result = register_source(settings, args.source, args.source_id, args.acl, args.egress, args.retention_class, at, args.expires_at)
            elif args.command == "preview":
                result = preview_source(settings, args.proposal, at)
            elif args.command == "apply":
                result = apply_preview(settings, args.preview_id, at)
            elif args.command == "inspect":
                result = inspect_report(settings, at)
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
