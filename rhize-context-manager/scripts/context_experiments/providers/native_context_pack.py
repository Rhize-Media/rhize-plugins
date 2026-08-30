"""Deterministic, local-only context packs for mixed-language repositories."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import tokenize
import tomllib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

from .context_compiler import CompiledPack, ProviderHealth, stable_pack_id


PROVIDER_REVISION = "rhize-native-context-pack-v2"
SOURCE_SUFFIXES = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
CONFIG_NAMES = {
    "package.json",
    "pyproject.toml",
    "tsconfig.json",
    "jsconfig.json",
    "vite.config.js",
    "vite.config.ts",
}
MAX_SOURCE_BYTES = 512_000
MAX_SOURCE_FILES = 2_500
MAX_SCAN_BYTES = 25_000_000
MIN_PROJECTED_REDUCTION_PERCENT = 10.0
MAX_PRIVATE_ISSUES = 20
MAX_IMPACT_HINT_BYTES = 256_000
PROMPT_BUDGET_RESERVE_WARNINGS = {
    "insufficient_compilation_benefit",
    "optional_entries_truncated_by_budget",
    "required_dependency_exceeds_token_budget",
    "required_target_exceeds_token_budget",
}
_QUERY_STOP_WORDS = {
    "acceptance", "behavior", "change", "current", "evidence", "explicitly",
    "implementation", "impact", "intended", "must", "planned", "repository",
    "tests", "that", "the", "this", "with", "from", "into", "and", "for",
}


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    snapshot_current: bool
    prompt_current: bool
    changed_entries: tuple[str, ...]
    missing_entries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "snapshotCurrent": self.snapshot_current,
            "promptCurrent": self.prompt_current,
            "changedEntries": list(self.changed_entries),
            "missingEntries": list(self.missing_entries),
        }


@dataclass(frozen=True)
class SourceInventory:
    paths: tuple[Path, ...]
    scan_budget_exceeded: bool


@dataclass(frozen=True)
class DependencyIssue:
    code: str
    source_path: str
    line: int
    specifier: str

    def private_message(self) -> str:
        return f"{self.code}: {self.source_path}:{self.line} ({self.specifier})"


@dataclass(frozen=True)
class ImpactHint:
    content_hash: str
    terms: tuple[str, ...]
    seeds: tuple[Path, ...]

    def provenance(self) -> dict[str, Any]:
        term_hash = _sha256("\n".join(self.terms).encode())
        return {
            "contentHash": self.content_hash,
            "present": True,
            "seedCount": len(self.seeds),
            "termSetHash": term_hash,
        }


class NativeContextPackProvider:
    """Build inspectable FULL/INTERFACE packs without a network dependency."""

    name = "rhize-native"

    def doctor(self) -> ProviderHealth:
        if shutil.which("git") is None:
            return ProviderHealth(False, "git is required for source-bound native packs")
        return ProviderHealth(
            True,
            "local mixed-language context-pack provider is available",
            PROVIDER_REVISION,
        )

    def compile(
        self,
        repo_root: Path,
        *,
        snapshot: str,
        task_hash: str,
        targets: Iterable[Path] = (),
        query: str | None = None,
        impact_hint: Path | None = None,
        max_hops: int = 2,
        max_tokens: int = 40_000,
    ) -> CompiledPack:
        repo = repo_root.expanduser().resolve(strict=True)
        if not repo.is_dir():
            raise ValueError("repository root must be a directory")
        if not 1 <= max_hops <= 5:
            raise ValueError("max_hops must be between 1 and 5")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        inventory = _source_inventory(repo)
        source_paths = inventory.paths
        if not source_paths:
            raise ValueError("repository contains no supported source files")
        hint = _load_impact_hint(repo, source_paths, impact_hint)
        target_paths, strategy, discovery_warnings = _discover_targets(
            repo, source_paths, targets, query, hint
        )
        if not target_paths:
            raise ValueError("native context-pack discovery found no target")

        edge_warnings: set[str] = set(discovery_warnings)
        private_issues: list[DependencyIssue] = []
        if inventory.scan_budget_exceeded:
            edge_warnings.add("repository_scan_budget_exceeded")
        selected_distance: dict[Path, int] = {path: 0 for path in target_paths}
        frontier = list(target_paths)
        for hop in range(max_hops):
            next_frontier: list[Path] = []
            for path in frontier:
                dependencies, issues = _dependencies(repo, path)
                private_issues.extend(issues)
                edge_warnings.update(issue.code for issue in issues)
                codegraph_dependencies, codegraph_warning = _codegraph_dependencies(
                    repo, path, source_paths
                )
                dependencies = tuple(sorted(set((*dependencies, *codegraph_dependencies))))
                if codegraph_warning:
                    edge_warnings.add(codegraph_warning)
                for dependency in dependencies:
                    if dependency not in selected_distance:
                        selected_distance[dependency] = hop + 1
                        next_frontier.append(dependency)
            frontier = next_frontier
            if not frontier:
                break

        # The last included dependency tier is usable only when it closes the graph.
        # Inspect it once without expanding the pack so max_hops cannot silently hide
        # another required local edge.
        for path in frontier:
            dependencies, issues = _dependencies(repo, path)
            private_issues.extend(issues)
            edge_warnings.update(issue.code for issue in issues)
            if dependencies:
                edge_warnings.add("dependency_traversal_truncated")

        for path in selected_distance:
            edge_warnings.update(_dynamic_warnings(path))
        if len({path.stem for path in target_paths}) != len(target_paths):
            edge_warnings.add("ambiguous_dependency_name_collision")

        related = _related_support_files(repo, source_paths, target_paths)
        candidates: list[tuple[Path, str, str, int]] = []
        for path, distance in selected_distance.items():
            role = "FULL" if distance == 0 else "INTERFACE"
            reason = "explicit_or_discovered_target" if distance == 0 else "static_dependency"
            candidates.append((path, role, reason, distance))
        candidates.extend(
            (path, "FULL", reason, max_hops + 1) for path, reason in related
        )
        candidates.sort(
            key=lambda item: (
                (
                    0
                    if item[2] in {"explicit_or_discovered_target", "static_dependency"}
                    else 1
                ),
                item[3],
                _role_order(item[1]),
                item[0].relative_to(repo).as_posix(),
            )
        )

        entries: list[dict[str, Any]] = []
        rendered: list[tuple[dict[str, Any], str]] = []
        budget_truncated = False
        seen: set[Path] = set()
        for path, role, reason, _distance in candidates:
            if path in seen:
                continue
            seen.add(path)
            content = path.read_text(encoding="utf-8", errors="replace")
            if role == "FULL":
                selected_content = content
            else:
                selected_content, interface_complete = _interface_content(path, content)
                if not interface_complete:
                    role = "FULL"
                    reason = "interface_widened_to_full"
                    selected_content = content
                    edge_warnings.add("interface_widened_to_full")
            token_count = _estimate_tokens(selected_content)
            relative = path.relative_to(repo).as_posix()
            entry = {
                "path": relative,
                "role": role,
                "reason": reason,
                "sourceHash": _sha256(path.read_bytes()),
                "renderedHash": _sha256(selected_content.encode()),
                "estimatedTokens": token_count,
            }
            budget_manifest = {
                "snapshot": snapshot,
                "warnings": sorted(edge_warnings | PROMPT_BUDGET_RESERVE_WARNINGS),
            }
            prospective_prompt = _render_prompt(
                budget_manifest,
                [*rendered, (entry, selected_content)],
                private_issues[:MAX_PRIVATE_ISSUES],
            )
            if _estimate_tokens(prospective_prompt) > max_tokens:
                if role == "FULL" and path in target_paths:
                    edge_warnings.add("required_target_exceeds_token_budget")
                elif reason == "static_dependency":
                    edge_warnings.add("required_dependency_exceeds_token_budget")
                else:
                    budget_truncated = True
                continue
            entries.append(entry)
            rendered.append((entry, selected_content))
        if not entries or not all(
            any(
                entry["path"] == target.relative_to(repo).as_posix()
                for entry in entries
            )
            for target in target_paths
        ):
            raise ValueError("token budget cannot contain every required target")
        if budget_truncated:
            edge_warnings.add("optional_entries_truncated_by_budget")

        naive_rendered = [
            (
                {
                    "path": path.relative_to(repo).as_posix(),
                    "role": "FULL",
                    "reason": "naive_source_dump",
                },
                path.read_text(encoding="utf-8", errors="replace"),
            )
            for path in source_paths
        ]
        naive_tokens = _estimate_tokens(
            _render_prompt(
                {"snapshot": snapshot, "warnings": []},
                naive_rendered,
                [],
            )
        )
        all_warnings = sorted(edge_warnings)
        rejection_reasons = sorted(
            warning
            for warning in all_warnings
            if warning
            in {
                "ambiguous_dependency_name_collision",
                "dynamic_dependency_edge",
                "dependency_traversal_truncated",
                "required_dependency_exceeds_token_budget",
                "required_target_exceeds_token_budget",
                "repository_scan_budget_exceeded",
                "insufficient_compilation_benefit",
                "unresolved_local_dependency",
                "unsupported_source_syntax",
            }
        )
        excluded_count = max(0, len(source_paths) - len({entry["path"] for entry in entries}))
        exclusion_counts: dict[str, int] = {}
        if excluded_count:
            exclusion_counts["not_reachable"] = excluded_count
        if budget_truncated:
            exclusion_counts["optional_budget_truncation"] = 1
        for issue in private_issues:
            exclusion_counts[issue.code] = exclusion_counts.get(issue.code, 0) + 1
        source_manifest_hash = _sha256(
            json.dumps(
                [
                    {
                        key: entry[key]
                        for key in ("path", "sourceHash", "renderedHash")
                    }
                    for entry in entries
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        manifest: dict[str, Any] = {
            "schemaVersion": 2,
            "packId": "pending",
            "repoId": _sha256(f"{repo.name}:{snapshot}".encode())[:16],
            "snapshot": snapshot,
            "taskHash": task_hash,
            "provider": {"name": self.name, "revision": PROVIDER_REVISION},
            "discovery": {
                "strategy": strategy,
                "queryHash": _sha256(query.strip().encode()) if query and query.strip() else None,
                "targetPaths": [path.relative_to(repo).as_posix() for path in target_paths],
            },
            "impactHint": (
                hint.provenance()
                if hint is not None
                else {
                    "contentHash": None,
                    "present": False,
                    "seedCount": 0,
                    "termSetHash": None,
                }
            ),
            "entries": entries,
            "excludedCount": excluded_count,
            "exclusionLedger": {
                "reasonCounts": dict(sorted(exclusion_counts.items())[:8]),
                "reasonKindsTruncated": max(0, len(exclusion_counts) - 8),
                "privateIssueCount": len(private_issues),
                "privateIssuesTruncated": max(0, len(private_issues) - MAX_PRIVATE_ISSUES),
            },
            "totalSourceFiles": len(source_paths),
            "naiveDumpTokens": naive_tokens,
            "compiledTokens": 0,
            "reductionPercent": 0.0,
            # Provider v2 manifests are byte-stable across hosts. Runtime latency is
            # measured by the caller/eval receipt, not embedded in pack identity.
            "buildMilliseconds": 0.0,
            "sourceManifestHash": source_manifest_hash,
            "policy": {
                "acceptedForUse": not rejection_reasons,
                "maximumTokens": max_tokens,
                "eligibilityPolicy": {
                    "version": "native-context-eligibility-v2",
                    "maximumSourceFiles": MAX_SOURCE_FILES,
                    "maximumScanBytes": MAX_SCAN_BYTES,
                    "minimumProjectedReductionPercent": MIN_PROJECTED_REDUCTION_PERCENT,
                },
                "rejectionReasons": rejection_reasons,
            },
            "warnings": all_warnings,
        }
        prompt = _render_prompt(manifest, rendered, private_issues[:MAX_PRIVATE_ISSUES])
        compiled_tokens = _estimate_tokens(prompt)
        reduction_percent = (
            round((1 - compiled_tokens / naive_tokens) * 100, 3)
            if naive_tokens
            else 0.0
        )
        if (
            len(source_paths) <= 1
            or reduction_percent < MIN_PROJECTED_REDUCTION_PERCENT
        ) and "insufficient_compilation_benefit" not in edge_warnings:
            edge_warnings.add("insufficient_compilation_benefit")
            all_warnings = sorted(edge_warnings)
            rejection_reasons = sorted(
                set(rejection_reasons) | {"insufficient_compilation_benefit"}
            )
            manifest["warnings"] = all_warnings
            manifest["policy"]["acceptedForUse"] = False
            manifest["policy"]["rejectionReasons"] = rejection_reasons
            prompt = _render_prompt(manifest, rendered, private_issues[:MAX_PRIVATE_ISSUES])
            compiled_tokens = _estimate_tokens(prompt)
            reduction_percent = (
                round((1 - compiled_tokens / naive_tokens) * 100, 3)
                if naive_tokens
                else 0.0
            )
        if compiled_tokens > max_tokens:
            raise ValueError("token budget cannot contain required prompt framing and targets")
        manifest["compiledTokens"] = compiled_tokens
        manifest["reductionPercent"] = reduction_percent
        manifest["promptHash"] = _sha256(prompt.encode())
        manifest["packId"] = stable_pack_id(manifest)
        return CompiledPack(manifest=manifest, prompt=prompt)

    def write_pack(self, pack: CompiledPack, directory: Path) -> tuple[Path, Path]:
        validate_native_context_pack_manifest(pack.manifest)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        pack_id = pack.manifest["packId"]
        manifest_path = directory / f"{pack_id}.json"
        prompt_path = directory / f"{pack_id}.md"
        manifest_payload = json.dumps(pack.manifest, indent=2, sort_keys=True) + "\n"
        if manifest_path.exists() or prompt_path.exists():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing_manifest = None
            if (
                manifest_path.is_file()
                and prompt_path.is_file()
                and isinstance(existing_manifest, dict)
                and _pack_identity(existing_manifest) == _pack_identity(pack.manifest)
                and prompt_path.read_text(encoding="utf-8") == pack.prompt
            ):
                return manifest_path, prompt_path
            raise FileExistsError(f"native pack id collides with different content: {pack_id}")
        _write_private(manifest_path, manifest_payload)
        try:
            _write_private(prompt_path, pack.prompt)
        except Exception:
            manifest_path.unlink(missing_ok=True)
            raise
        return manifest_path, prompt_path

    def verify_pack(
        self,
        manifest: dict[str, Any],
        repo_root: Path,
        current_snapshot: str,
        prompt_path: Path,
    ) -> VerificationResult:
        validate_native_context_pack_manifest(manifest)
        repo = repo_root.expanduser().resolve(strict=True)
        changed: list[str] = []
        missing: list[str] = []
        for entry in manifest["entries"]:
            path = repo / entry["path"]
            if not path.is_file() or path.is_symlink():
                missing.append(entry["path"])
                continue
            if _sha256(path.read_bytes()) != entry["sourceHash"]:
                changed.append(entry["path"])
        snapshot_current = current_snapshot == manifest["snapshot"]
        raw_prompt = prompt_path.expanduser()
        if raw_prompt.is_symlink():
            raise ValueError("native context prompt cannot be a symlink")
        prompt = raw_prompt.resolve(strict=True)
        prompt_text = prompt.read_text(encoding="utf-8") if prompt.is_file() else ""
        if manifest["provider"]["revision"] == PROVIDER_REVISION:
            prompt_current = (
                prompt.is_file()
                and _sha256(prompt_text.encode()) == manifest["promptHash"]
                and _estimate_tokens(prompt_text) == manifest["compiledTokens"]
            )
        else:
            prompt_current = prompt.is_file()
        return VerificationResult(
            valid=snapshot_current and prompt_current and not changed and not missing,
            snapshot_current=snapshot_current,
            prompt_current=prompt_current,
            changed_entries=tuple(sorted(changed)),
            missing_entries=tuple(sorted(missing)),
        )


def _source_inventory(repo: Path) -> SourceInventory:
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo), "ls-files", "--cached", "--others",
                "--exclude-standard", "-z",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode == 0:
        relative_paths = [
            Path(value.decode(errors="replace"))
            for value in result.stdout.split(b"\0")
            if value
        ]
    else:
        relative_paths = [path.relative_to(repo) for path in repo.rglob("*") if path.is_file()]
    paths: list[Path] = []
    supported_count = 0
    supported_bytes = 0
    for relative in relative_paths:
        path = repo / relative
        if (
            path.is_file()
            and not path.is_symlink()
            and (path.suffix in SOURCE_SUFFIXES or path.name in CONFIG_NAMES)
            and not any(
                part in {"node_modules", ".git", "dist", "build"}
                for part in relative.parts
            )
        ):
            size = path.stat().st_size
            supported_count += 1
            supported_bytes += size
            if size <= MAX_SOURCE_BYTES:
                paths.append(path.resolve())
    ordered = tuple(sorted(set(paths), key=lambda path: path.relative_to(repo).as_posix()))
    return SourceInventory(
        paths=ordered,
        scan_budget_exceeded=(
            supported_count > MAX_SOURCE_FILES or supported_bytes > MAX_SCAN_BYTES
        ),
    )


def _discover_targets(
    repo: Path,
    source_paths: tuple[Path, ...],
    targets: Iterable[Path],
    query: str | None,
    impact_hint: ImpactHint | None,
) -> tuple[tuple[Path, ...], str, tuple[str, ...]]:
    explicit = tuple(_safe_target(repo, target) for target in targets)
    if explicit:
        return tuple(sorted(set(explicit))), "explicit", ()
    if not query or not query.strip():
        raise ValueError("native context-pack requires --target or --query")
    warnings: list[str] = []
    expanded_query = _expanded_query(query, impact_hint)
    seeds = impact_hint.seeds if impact_hint is not None else ()
    if (repo / ".codegraph").is_dir():
        if _codegraph_healthy(repo):
            discovered = _codegraph_targets(repo, source_paths, expanded_query)
            combined = _ordered_targets(repo, (*discovered, *seeds), limit=5)
            if combined:
                return combined, (
                    "impact_codegraph" if impact_hint is not None else "codegraph"
                ), ()
        warnings.append("codegraph_discovery_unavailable_fell_back")
    discovered = _rg_targets(repo, source_paths, expanded_query)
    if discovered is None:
        warnings.append("rg_discovery_unavailable_internal_fallback")
        discovered = _baseline_targets(repo, source_paths, expanded_query)
    combined = _ordered_targets(repo, (*seeds, *discovered), limit=5)
    return combined, ("impact_rg" if impact_hint is not None else "rg"), tuple(warnings)


def _load_impact_hint(
    repo: Path,
    source_paths: tuple[Path, ...],
    hint_path: Path | None,
) -> ImpactHint | None:
    if hint_path is None:
        return None
    candidate = hint_path.expanduser()
    if not candidate.is_absolute():
        candidate = repo / candidate
    if candidate.is_symlink():
        raise ValueError("impact hint must be a regular repository-local markdown file")
    candidate = candidate.resolve(strict=True)
    try:
        candidate.relative_to(repo)
    except ValueError as error:
        raise ValueError("impact hint must be inside the repository") from error
    if not candidate.is_file() or candidate.suffix != ".md":
        raise ValueError("impact hint must be a regular repository-local markdown file")
    payload = candidate.read_bytes()
    if len(payload) > MAX_IMPACT_HINT_BYTES:
        raise ValueError("impact hint exceeds the local size limit")
    text = payload.decode("utf-8", errors="strict")
    terms = tuple(
        sorted(
            {
                term.lower()
                for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
                if term.lower() not in _QUERY_STOP_WORDS
            }
        )[:64]
    )
    by_relative = {path.relative_to(repo).as_posix(): path for path in source_paths}
    seeds = tuple(
        by_relative[value]
        for value in sorted(
            {
                token.strip("`'\".,:;()[]")
                for token in re.findall(r"`([^`]+)`", text)
            }
            & set(by_relative)
        )
    )
    return ImpactHint(_sha256(payload), terms, seeds)


def _expanded_query(query: str, impact_hint: ImpactHint | None) -> str:
    if impact_hint is None or not impact_hint.terms:
        return query.strip()
    return " ".join((query.strip(), *impact_hint.terms))


def _ordered_targets(
    repo: Path, paths: Iterable[Path], *, limit: int
) -> tuple[Path, ...]:
    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        resolved.relative_to(repo)
        if resolved not in seen:
            ordered.append(resolved)
            seen.add(resolved)
        if len(ordered) == limit:
            break
    return tuple(ordered)


def _safe_target(repo: Path, target: Path) -> Path:
    path = target.expanduser()
    if not path.is_absolute():
        path = repo / path
    path = path.resolve(strict=True)
    if not path.is_file() or path.is_symlink() or path.suffix not in SOURCE_SUFFIXES:
        raise ValueError("native context-pack target must be a supported regular source file")
    try:
        path.relative_to(repo)
    except ValueError as error:
        raise ValueError("target must be inside the repository root") from error
    return path


def _codegraph_targets(
    repo: Path, source_paths: tuple[Path, ...], query: str
) -> tuple[Path, ...]:
    try:
        result = subprocess.run(
            ["codegraph", "explore", query],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if result.returncode != 0:
        return ()
    by_relative = {path.relative_to(repo).as_posix(): path for path in source_paths}
    matches = [path for relative, path in by_relative.items() if relative in result.stdout]
    ordered = sorted(set(matches), key=lambda path: path.relative_to(repo).as_posix())
    return tuple(ordered[:5])


def _codegraph_healthy(repo: Path) -> bool:
    if not (repo / ".codegraph").is_dir() or shutil.which("codegraph") is None:
        return False
    try:
        result = subprocess.run(
            ["codegraph", "status"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    status = f"{result.stdout}\n{result.stderr}".lower()
    return (
        result.returncode == 0
        and not any(word in status for word in ("stale", "corrupt", "unhealthy"))
        and any(word in status for word in ("healthy", "current", "ready", "indexed"))
    )


def _rg_targets(
    repo: Path, source_paths: tuple[Path, ...], query: str
) -> tuple[Path, ...] | None:
    if shutil.which("rg") is None:
        return None
    terms = sorted(
        {
            term.lower()
            for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", query)
            if term.lower() not in _QUERY_STOP_WORDS
        }
    )
    if not terms:
        return ()
    command = ["rg", "--files-with-matches", "--ignore-case", "--no-messages"]
    for term in terms:
        command.extend(("-e", re.escape(term)))
    command.append(".")
    try:
        result = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode not in {0, 1}:
        return None
    allowed = {path.relative_to(repo).as_posix(): path for path in source_paths}
    candidates = {
        value.removeprefix("./")
        for value in result.stdout.splitlines()
        if value.removeprefix("./") in allowed
    }
    return _baseline_targets(
        repo, tuple(allowed[value] for value in sorted(candidates)), query
    )


def _baseline_targets(
    repo: Path, source_paths: tuple[Path, ...], query: str
) -> tuple[Path, ...]:
    terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", query)
        if term.lower() not in {"the", "and", "for", "with", "from", "into", "this", "that"}
    }
    scored: list[tuple[int, str, Path]] = []
    for path in source_paths:
        relative = path.relative_to(repo).as_posix().lower()
        content = path.read_text(encoding="utf-8", errors="replace").lower()
        score = sum(5 for term in terms if term in relative) + sum(
            min(content.count(term), 3) for term in terms
        )
        if score:
            scored.append((-score, relative, path))
    scored.sort()
    return tuple(item[2] for item in scored[:3])


def _dependencies(repo: Path, path: Path) -> tuple[tuple[Path, ...], tuple[DependencyIssue, ...]]:
    content = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return _python_dependencies(repo, path, content)
    return _javascript_dependencies(repo, path, content)


def _python_dependencies(
    repo: Path, path: Path, content: str
) -> tuple[tuple[Path, ...], tuple[DependencyIssue, ...]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return (), (
            DependencyIssue(
                "unsupported_source_syntax", path.relative_to(repo).as_posix(), 1, "python"
            ),
        )
    dependencies: set[Path] = set()
    issues: list[DependencyIssue] = []
    roots = _python_source_roots(repo, path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            base = path.parent
            for _ in range(max(0, node.level - 1)):
                base = base.parent
            modules = [module] if module else [alias.name for alias in node.names]
            for imported_module in modules:
                search_roots = (base,) if node.level else roots
                resolved = _resolve_python_module(repo, search_roots, imported_module)
                if resolved:
                    dependencies.add(resolved)
                elif node.level or _python_module_is_internal(roots, imported_module):
                    issues.append(_dependency_issue(repo, path, node.lineno, imported_module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_python_module(repo, roots, alias.name)
                if resolved:
                    dependencies.add(resolved)
                elif _python_module_is_internal(roots, alias.name):
                    issues.append(_dependency_issue(repo, path, node.lineno, alias.name))
    return tuple(sorted(dependencies)), tuple(sorted(issues, key=_issue_key))


def _resolve_python_module(repo: Path, roots: Iterable[Path], module: str) -> Path | None:
    relative = Path(*module.split(".")) if module else Path()
    for base in roots:
        candidates = (base / relative).with_suffix(".py"), base / relative / "__init__.py"
        for candidate in candidates:
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(repo)
            except ValueError:
                continue
            if resolved.is_file() and not resolved.is_symlink():
                return resolved
    return None


def _python_module_is_internal(roots: Iterable[Path], module: str) -> bool:
    first = module.split(".", 1)[0]
    return any((root / first).exists() for root in roots)


def _python_source_roots(repo: Path, path: Path) -> tuple[Path, ...]:
    roots = [repo]
    if (repo / "src").is_dir():
        roots.append(repo / "src")
    config = _nearest_file(path.parent, repo, "pyproject.toml")
    if config:
        try:
            document = tomllib.loads(config.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            document = {}
        package_dir = (
            document.get("tool", {}).get("setuptools", {}).get("package-dir", {})
            if isinstance(document, dict)
            else {}
        )
        if isinstance(package_dir, dict):
            for value in package_dir.values():
                if isinstance(value, str):
                    roots.append(config.parent / value)
        pythonpath = (
            document.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("pythonpath", [])
            if isinstance(document, dict)
            else []
        )
        if isinstance(pythonpath, str):
            pythonpath = [pythonpath]
        if isinstance(pythonpath, list):
            roots.extend(config.parent / value for value in pythonpath if isinstance(value, str))
    return tuple(dict.fromkeys(root.resolve(strict=False) for root in roots))


def _javascript_dependencies(
    repo: Path, path: Path, content: str
) -> tuple[tuple[Path, ...], tuple[DependencyIssue, ...]]:
    specs = re.finditer(
        r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']"
        r"|require\(\s*[\"']([^\"']+)[\"']\s*\)",
        content,
    )
    dependencies: set[Path] = set()
    issues: list[DependencyIssue] = []
    for match in specs:
        spec = match.group(1) or match.group(2) or ""
        resolved, internal = _resolve_javascript_import(repo, path, spec)
        if resolved:
            dependencies.add(resolved)
        elif internal:
            line = content.count("\n", 0, match.start()) + 1
            issues.append(_dependency_issue(repo, path, line, spec))
    return tuple(sorted(dependencies)), tuple(sorted(issues, key=_issue_key))


def _resolve_javascript_import(repo: Path, path: Path, spec: str) -> tuple[Path | None, bool]:
    if spec.startswith("."):
        return _resolve_javascript_spec(repo, path.parent, spec), True

    package_root = _nearest_package_root(path.parent, repo)
    if spec.startswith("#") and package_root:
        package = _read_json_document(package_root / "package.json")
        mapped = _map_package_field(package.get("imports"), spec)
        if mapped:
            return _resolve_javascript_spec(repo, package_root, mapped), True
        return None, True

    config = _nearest_js_config(path.parent, repo)
    if config:
        compiler = _compiler_options(config, repo)
        base_url = compiler.get("baseUrl", ".") if isinstance(compiler, dict) else "."
        paths = compiler.get("paths", {}) if isinstance(compiler, dict) else {}
        if isinstance(paths, dict):
            for pattern, replacements in paths.items():
                capture = _match_alias(pattern, spec)
                if capture is None:
                    continue
                candidates = replacements if isinstance(replacements, list) else [replacements]
                for replacement in candidates:
                    if isinstance(replacement, str):
                        mapped = replacement.replace("*", capture)
                        resolved = _resolve_javascript_spec(
                            repo, config.parent / str(base_url), mapped
                        )
                        if resolved:
                            return resolved, True
                return None, True

    workspace = _workspace_package(repo, spec)
    if workspace:
        package_root, subpath = workspace
        package = _read_json_document(package_root / "package.json")
        export_key = "." if not subpath else f"./{subpath}"
        mapped = _map_package_field(package.get("exports"), export_key)
        if not mapped and subpath:
            mapped = subpath
        if not mapped:
            mapped = package.get("types") or package.get("module") or package.get("main") or "src/index"
        if isinstance(mapped, str):
            return _resolve_javascript_spec(repo, package_root, mapped), True
        return None, True
    return None, False


def _resolve_javascript_spec(repo: Path, base: Path, spec: str) -> Path | None:
    root = (base / spec).resolve(strict=False)
    candidates = [root]
    candidates.extend(root.with_suffix(suffix) for suffix in SOURCE_SUFFIXES)
    candidates.extend(root / f"index{suffix}" for suffix in SOURCE_SUFFIXES)
    for candidate in candidates:
        try:
            candidate.relative_to(repo)
        except ValueError:
            continue
        if (
            candidate.is_file()
            and not candidate.is_symlink()
            and candidate.suffix in SOURCE_SUFFIXES
        ):
            return candidate.resolve()
    return None


def _nearest_file(start: Path, repo: Path, name: str) -> Path | None:
    current = start.resolve(strict=False)
    while True:
        candidate = current / name
        if candidate.is_file():
            return candidate
        if current == repo or repo not in current.parents:
            return None
        current = current.parent


def _nearest_package_root(start: Path, repo: Path) -> Path | None:
    package = _nearest_file(start, repo, "package.json")
    return package.parent if package else None


def _nearest_js_config(start: Path, repo: Path) -> Path | None:
    for name in ("tsconfig.json", "jsconfig.json"):
        config = _nearest_file(start, repo, name)
        if config:
            return config
    return None


def _compiler_options(config: Path, repo: Path, seen: set[Path] | None = None) -> dict[str, Any]:
    visited = seen or set()
    resolved = config.resolve(strict=False)
    if resolved in visited:
        return {}
    visited.add(resolved)
    document = _read_json_document(config)
    merged: dict[str, Any] = {}
    extends = document.get("extends")
    if isinstance(extends, str) and extends.startswith("."):
        parent = (config.parent / extends).resolve(strict=False)
        if not parent.suffix:
            parent = parent.with_suffix(".json")
        try:
            in_repo = parent == repo or repo in parent.parents
        except OSError:
            in_repo = False
        if in_repo and parent.is_file():
            merged.update(_compiler_options(parent, repo, visited))
    own = document.get("compilerOptions", {})
    if isinstance(own, dict):
        for key, value in own.items():
            if key == "paths" and isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    return merged


def _read_json_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
        raw = re.sub(r"(^|\s)//.*$", r"\1", raw, flags=re.MULTILINE)
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _match_alias(pattern: str, spec: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == spec else None
    prefix, suffix = pattern.split("*", 1)
    if spec.startswith(prefix) and spec.endswith(suffix):
        return spec[len(prefix): len(spec) - len(suffix) if suffix else None]
    return None


def _map_package_field(field: Any, key: str) -> str | None:
    if isinstance(field, str):
        return field
    if not isinstance(field, dict):
        return None
    for pattern, value in field.items():
        capture = _match_alias(pattern, key)
        if capture is None:
            continue
        while isinstance(value, dict):
            value = next((value[name] for name in ("types", "import", "default") if name in value), None)
            if value is None:
                break
        if isinstance(value, str):
            return value.replace("*", capture)
    return None


def _workspace_package(repo: Path, spec: str) -> tuple[Path, str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard", "*package.json"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    relative_paths = result.stdout.splitlines() if result and result.returncode == 0 else []
    for relative in relative_paths[:MAX_SOURCE_FILES]:
        package_file = repo / relative
        if not package_file.is_file() or package_file.is_symlink():
            continue
        document = _read_json_document(package_file)
        name = document.get("name")
        if not isinstance(name, str):
            continue
        if spec == name:
            return package_file.parent, ""
        if spec.startswith(f"{name}/"):
            return package_file.parent, spec[len(name) + 1:]
    return None


def _dependency_issue(repo: Path, path: Path, line: int, spec: str) -> DependencyIssue:
    return DependencyIssue(
        "unresolved_local_dependency",
        path.relative_to(repo).as_posix(),
        line,
        spec[:160],
    )


def _issue_key(issue: DependencyIssue) -> tuple[str, int, str]:
    return issue.source_path, issue.line, issue.specifier


def _codegraph_dependencies(
    repo: Path, path: Path, source_paths: tuple[Path, ...]
) -> tuple[tuple[Path, ...], str | None]:
    if not (repo / ".codegraph").is_dir():
        return (), None
    if shutil.which("codegraph") is None:
        return (), "codegraph_dependency_expansion_unavailable_fell_back"
    relative = path.relative_to(repo).as_posix()
    try:
        result = subprocess.run(
            ["codegraph", "explore", f"dependencies and callers for {relative}"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return (), "codegraph_dependency_expansion_unavailable_fell_back"
    if result.returncode != 0:
        return (), "codegraph_dependency_expansion_unavailable_fell_back"
    matches = tuple(
        candidate
        for candidate in source_paths
        if candidate != path and candidate.relative_to(repo).as_posix() in result.stdout
    )
    return tuple(sorted(set(matches))), None


def _dynamic_warnings(path: Path) -> set[str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return {"unsupported_source_syntax"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                return {"dynamic_dependency_edge"}
            if isinstance(node.func, ast.Subscript):
                return {"dynamic_dependency_edge"}
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "on", "once", "addEventListener", "register"
            }:
                return {"dynamic_dependency_edge"}
        return set()
    patterns = (
        r"\bimport\s*\(",
        r"\brequire\s*\(\s*[^\"']",
        r"\.(?:on|once|addEventListener|register)\s*\(",
        r"\[[^\]\"']+\]\s*\(",
    )
    if any(re.search(pattern, content) for pattern in patterns):
        return {"dynamic_dependency_edge"}
    return set()


def _related_support_files(
    repo: Path, source_paths: tuple[Path, ...], targets: tuple[Path, ...]
) -> tuple[tuple[Path, str], ...]:
    target_stems = {target.stem.lower() for target in targets}
    target_dirs = {target.parent for target in targets}
    related: list[tuple[Path, str]] = []
    for path in source_paths:
        lower_name = path.name.lower()
        if path in targets:
            continue
        if (
            (lower_name.startswith("test_") or ".test." in lower_name or ".spec." in lower_name)
            and any(
                stem in path.read_text(encoding="utf-8", errors="replace").lower()
                for stem in target_stems
            )
        ):
            related.append((path, "related_test"))
        elif path.name in CONFIG_NAMES and (path.parent in target_dirs or path.parent == repo):
            related.append((path, "nearby_configuration"))
    return tuple(sorted(related, key=lambda item: item[0].relative_to(repo).as_posix()))


def _interface_content(path: Path, content: str) -> tuple[str, bool]:
    if path.suffix == ".py":
        return _python_interface_content(content)
    return _javascript_interface_content(content)


def _python_interface_content(content: str) -> tuple[str, bool]:
    try:
        tree = ast.parse(content)
        token_stream = tuple(tokenize.generate_tokens(StringIO(content).readline))
    except (SyntaxError, tokenize.TokenError, IndentationError):
        return "", False
    lines = content.splitlines()
    rendered: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            segment = ast.get_source_segment(content, node)
            if segment:
                rendered.append(segment.rstrip())
            continue
        if isinstance(node, ast.ClassDef):
            # Public method extraction needs type-aware class semantics. Whole-file
            # widening is safer than emitting a class name without its callable contract.
            return "", False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min(
                [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
            )
            header = _python_header(lines, token_stream, start, node.lineno)
            if not header:
                return "", False
            rendered.append(header + " ...")
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            segment = ast.get_source_segment(content, node)
            if segment and not segment.lstrip().startswith("_"):
                rendered.append(segment.rstrip())
    return ("\n\n".join(rendered) + ("\n" if rendered else ""), bool(rendered))


def _python_header(
    lines: list[str], tokens: tuple[tokenize.TokenInfo, ...], start_line: int, definition_line: int
) -> str | None:
    started = False
    depth = 0
    colon: tokenize.TokenInfo | None = None
    for token in tokens:
        if token.start[0] < definition_line:
            continue
        if token.type == tokenize.NAME and token.string in {"def", "class"}:
            started = True
        if not started:
            continue
        if token.string in "([{":
            depth += 1
        elif token.string in ")]}" and depth:
            depth -= 1
        elif token.string == ":" and depth == 0:
            colon = token
            break
    if colon is None:
        return None
    selected = lines[start_line - 1: colon.end[0]]
    if not selected:
        return None
    selected[-1] = selected[-1][: colon.end[1]]
    return "\n".join(selected).rstrip()


def _javascript_interface_content(content: str) -> tuple[str, bool]:
    """Parse top-level imports/exports with balanced delimiters; widen on ambiguity."""

    masked = _mask_javascript(content)
    if masked is None:
        return "", False
    starts = [
        match.start()
        for match in re.finditer(r"(?m)^(?:\s*)(?:@|import\b|export\b)", masked)
    ]
    if not starts:
        return "", False
    rendered: list[str] = []
    while starts:
        start = starts[0]
        end, kind = _javascript_declaration_end(masked, start)
        if end is None:
            return "", False
        declaration = content[start:end].strip()
        if kind == "callable":
            masked_declaration = _mask_javascript(declaration)
            brace = (
                _javascript_callable_body_start(masked_declaration)
                if masked_declaration is not None
                else None
            )
            if brace is None:
                return "", False
            declaration = declaration[:brace].rstrip() + ";"
        elif kind == "unsupported":
            return "", False
        rendered.append(declaration)
        starts = [value for value in starts if value >= end]
    return ("\n\n".join(rendered) + "\n", True)


def _mask_javascript(content: str) -> str | None:
    chars = list(content)
    index = 0
    quote: str | None = None
    while index < len(chars):
        char = chars[index]
        if quote:
            if char == "\\":
                chars[index] = " "
                if index + 1 < len(chars):
                    chars[index + 1] = " "
                    index += 2
                    continue
            if char == quote:
                quote = None
            if char != "\n":
                chars[index] = " "
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            chars[index] = " "
            index += 1
            continue
        if content.startswith("//", index):
            end = content.find("\n", index)
            end = len(content) if end < 0 else end
            chars[index:end] = " " * (end - index)
            index = end
            continue
        if content.startswith("/*", index):
            end = content.find("*/", index + 2)
            if end < 0:
                return None
            end += 2
            for offset in range(index, end):
                if chars[offset] != "\n":
                    chars[offset] = " "
            index = end
            continue
        index += 1
    return None if quote else "".join(chars)


def _javascript_declaration_end(masked: str, start: int) -> tuple[int | None, str]:
    segment = masked[start:]
    prefix = segment.lstrip()
    if prefix.startswith("@"):
        next_export = re.search(r"(?m)^\s*export\b", segment)
        if not next_export:
            return None, "unsupported"
    if re.match(r"(?:@[^\n]+\n\s*)*export\s+(?:default\s+)?class\b", prefix):
        return None, "unsupported"
    callable_match = re.match(
        r"(?:@[^\n]+\n\s*)*export\s+(?:default\s+)?(?:async\s+)?function\b", prefix
    )
    import_or_export_clause = prefix.startswith("import") or bool(
        re.match(r"export\s+(?:type\s+)?{", prefix)
    )
    depth = 0
    saw_brace = False
    for offset, char in enumerate(segment):
        if char in "([{":
            depth += 1
            saw_brace = saw_brace or char == "{"
        elif char in ")]}" and depth:
            depth -= 1
            if char == "}" and depth == 0 and saw_brace and not import_or_export_clause:
                kind = "callable" if callable_match else "contract"
                return start + offset + 1, kind
        elif char == ";" and depth == 0:
            return start + offset + 1, "statement"
        elif char == "\n" and depth == 0 and prefix.startswith("import"):
            return start + offset, "statement"
    return None, "unsupported"


def _javascript_callable_body_start(masked: str) -> int | None:
    """Return the last top-level brace, which is the callable body after any object return type."""

    round_depth = 0
    square_depth = 0
    brace_depth = 0
    top_level_braces: list[int] = []
    for index, char in enumerate(masked):
        if char == "(":
            round_depth += 1
        elif char == ")" and round_depth:
            round_depth -= 1
        elif char == "[":
            square_depth += 1
        elif char == "]" and square_depth:
            square_depth -= 1
        elif char == "{":
            if round_depth == square_depth == brace_depth == 0:
                top_level_braces.append(index)
            brace_depth += 1
        elif char == "}" and brace_depth:
            brace_depth -= 1
    return top_level_braces[-1] if top_level_braces else None


def _render_prompt(
    manifest: dict[str, Any],
    rendered: list[tuple[dict[str, Any], str]],
    private_issues: list[DependencyIssue],
) -> str:
    lines = [
        "# Rhize native context pack",
        "",
        f"Snapshot: {manifest['snapshot']}",
        "",
    ]
    for entry, content in rendered:
        lines.extend(
            [
                f"## {entry['path']}",
                f"Role: {entry['role']} | Reason: {entry['reason']}",
                "```",
                content.rstrip(),
                "```",
                "",
            ]
        )
    if manifest["warnings"]:
        lines.extend(["## Warnings", *[f"- {warning}" for warning in manifest["warnings"]], ""])
    if private_issues:
        lines.extend(
            [
                "## Private dependency inspection",
                *[f"- {issue.private_message()}" for issue in private_issues],
                "",
            ]
        )
    return "\n".join(lines)


def _role_order(role: str) -> int:
    return 0 if role == "FULL" else 1


def _estimate_tokens(content: str) -> int:
    return max(1, (len(content.encode()) + 3) // 4) if content else 0


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _pack_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"packId", "buildMilliseconds"}
    }


def _write_private(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, content.encode())
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _matches(value: Any, pattern: str) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _require_integer(value: Any, label: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"native context pack {label} is invalid")
    return value


def _require_number(value: Any, label: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"native context pack {label} is invalid")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"native context pack {label} is invalid")
    return number


def _require_safe_ids(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not _matches(item, r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
        for item in value
    ):
        raise ValueError(f"native context pack {label} is invalid")
    return value


def validate_native_context_pack_manifest(manifest: dict[str, Any]) -> None:
    legacy_required = {
        "schemaVersion", "packId", "repoId", "snapshot", "taskHash", "provider",
        "discovery", "entries", "excludedCount", "exclusionLedger", "totalSourceFiles", "naiveDumpTokens",
        "compiledTokens", "reductionPercent", "buildMilliseconds", "sourceManifestHash",
        "policy", "warnings",
    }
    if not isinstance(manifest, dict):
        raise ValueError("native context pack manifest must be an object")
    manifest_fields = set(manifest)
    v2_required = legacy_required | {"impactHint", "promptHash"}
    if (
        manifest_fields not in (legacy_required, legacy_required | {"impactHint"}, v2_required)
        or manifest.get("schemaVersion") != 2
    ):
        raise ValueError("native context pack manifest has an invalid top-level shape")
    if not _matches(manifest["packId"], r"pack-[a-f0-9]{32}"):
        raise ValueError("native context pack has an invalid packId")
    if not _matches(manifest["repoId"], r"[a-f0-9]{16}"):
        raise ValueError("native context pack has an invalid repoId")
    if not _matches(manifest["taskHash"], r"[a-f0-9]{64}"):
        raise ValueError("native context pack has an invalid taskHash")
    if not _matches(manifest["snapshot"], r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"):
        raise ValueError("native context pack has an invalid snapshot")
    if not _matches(manifest["sourceManifestHash"], r"[a-f0-9]{64}"):
        raise ValueError("native context pack has an invalid source manifest hash")
    provider = manifest.get("provider")
    if (
        not isinstance(provider, dict)
        or set(provider) != {"name", "revision"}
        or provider.get("name") != "rhize-native"
        or provider.get("revision") not in {"rhize-native-context-pack-v1", PROVIDER_REVISION}
    ):
        raise ValueError("native context pack provider provenance is invalid")
    if provider["revision"] == PROVIDER_REVISION and "impactHint" not in manifest:
        raise ValueError("native context pack v2 provider requires impact hint provenance")
    if provider["revision"] == PROVIDER_REVISION:
        if not _matches(manifest.get("promptHash"), r"[a-f0-9]{64}"):
            raise ValueError("native context pack v2 provider requires prompt integrity")
    elif "promptHash" in manifest:
        raise ValueError("legacy native context packs cannot declare v2 prompt integrity")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("native context pack must have at least one entry")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "path", "role", "reason", "sourceHash", "renderedHash", "estimatedTokens"
        }:
            raise ValueError("native context pack entry has an invalid shape")
        _require_relative_path(entry["path"])
        if entry["role"] not in {"FULL", "INTERFACE"}:
            raise ValueError("native context pack entry has an invalid role")
        if entry["reason"] not in {
            "explicit_or_discovered_target", "static_dependency", "related_test",
            "nearby_configuration", "interface_widened_to_full",
        }:
            raise ValueError("native context pack entry has an invalid reason")
        for key in ("sourceHash", "renderedHash"):
            if not _matches(entry[key], r"[a-f0-9]{64}"):
                raise ValueError("native context pack entry has an invalid hash")
        _require_integer(entry["estimatedTokens"], "entry token estimate", 0)
    entry_paths = [entry["path"] for entry in entries]
    if len(set(entry_paths)) != len(entry_paths):
        raise ValueError("native context pack entry paths must be unique")
    discovery = manifest.get("discovery")
    if not isinstance(discovery, dict) or set(discovery) != {
        "strategy", "queryHash", "targetPaths"
    }:
        raise ValueError("native context pack discovery is invalid")
    if discovery["strategy"] not in {
        "explicit", "baseline", "rg", "codegraph", "impact_rg", "impact_codegraph"
    }:
        raise ValueError("native context pack discovery strategy is invalid")
    target_paths = discovery["targetPaths"]
    if not isinstance(target_paths, list) or not target_paths:
        raise ValueError("native context pack discovery targets are invalid")
    for path in target_paths:
        _require_relative_path(path)
    if len(set(target_paths)) != len(target_paths) or not set(target_paths) <= set(entry_paths):
        raise ValueError("native context pack discovery targets are inconsistent")
    query_hash = discovery["queryHash"]
    if query_hash is not None and not _matches(query_hash, r"[a-f0-9]{64}"):
        raise ValueError("native context pack query hash is invalid")
    impact_hint = manifest.get("impactHint")
    if impact_hint is None and provider["revision"] == "rhize-native-context-pack-v1":
        impact_hint = {
            "contentHash": None,
            "present": False,
            "seedCount": 0,
            "termSetHash": None,
        }
    if not isinstance(impact_hint, dict) or set(impact_hint) != {
        "contentHash", "present", "seedCount", "termSetHash"
    }:
        raise ValueError("native context pack impact hint provenance is invalid")
    if not isinstance(impact_hint["present"], bool):
        raise ValueError("native context pack impact hint presence is invalid")
    if isinstance(impact_hint["seedCount"], bool) or not isinstance(
        impact_hint["seedCount"], int
    ) or impact_hint["seedCount"] < 0:
        raise ValueError("native context pack impact hint seed count is invalid")
    for key in ("contentHash", "termSetHash"):
        value = impact_hint[key]
        if value is not None and not _matches(value, r"[a-f0-9]{64}"):
            raise ValueError("native context pack impact hint hash is invalid")
    if impact_hint["present"] != (impact_hint["contentHash"] is not None):
        raise ValueError("native context pack impact hint presence/hash mismatch")
    if impact_hint["present"] != (impact_hint["termSetHash"] is not None):
        raise ValueError("native context pack impact hint presence/term mismatch")
    policy = manifest.get("policy")
    if not isinstance(policy, dict) or set(policy) != {
        "acceptedForUse", "maximumTokens", "eligibilityPolicy", "rejectionReasons"
    }:
        raise ValueError("native context pack policy is invalid")
    if not isinstance(policy["acceptedForUse"], bool):
        raise ValueError("native context pack policy verdict is invalid")
    maximum_tokens = _require_integer(policy["maximumTokens"], "maximum token policy", 1)
    eligibility = policy["eligibilityPolicy"]
    if (
        not isinstance(eligibility, dict)
        or set(eligibility) != {
            "version", "maximumSourceFiles", "maximumScanBytes",
            "minimumProjectedReductionPercent",
        }
        or eligibility.get("version") != "native-context-eligibility-v2"
    ):
        raise ValueError("native context pack eligibility policy is invalid")
    _require_integer(eligibility["maximumSourceFiles"], "maximum source-file policy", 1)
    _require_integer(eligibility["maximumScanBytes"], "maximum scan-byte policy", 1)
    minimum_reduction = _require_number(
        eligibility["minimumProjectedReductionPercent"], "minimum reduction policy", 0
    )
    if minimum_reduction > 100:
        raise ValueError("native context pack minimum reduction policy is invalid")
    rejection_reasons = _require_safe_ids(policy["rejectionReasons"], "rejection reasons")
    if policy["acceptedForUse"] != (not rejection_reasons):
        raise ValueError("native context pack policy verdict and rejection reasons disagree")
    ledger = manifest.get("exclusionLedger")
    if not isinstance(ledger, dict) or set(ledger) != {
        "reasonCounts", "reasonKindsTruncated", "privateIssueCount", "privateIssuesTruncated"
    }:
        raise ValueError("native context pack exclusion ledger is invalid")
    reason_counts = ledger["reasonCounts"]
    if not isinstance(reason_counts, dict) or len(reason_counts) > 8:
        raise ValueError("native context pack exclusion reason counts are invalid")
    for key, value in reason_counts.items():
        if not isinstance(key, str) or not key:
            raise ValueError("native context pack exclusion reason counts are invalid")
        _require_integer(value, "exclusion reason count", 1)
    _require_integer(ledger["reasonKindsTruncated"], "truncated reason count", 0)
    private_issue_count = _require_integer(ledger["privateIssueCount"], "private issue count", 0)
    private_issues_truncated = _require_integer(
        ledger["privateIssuesTruncated"], "truncated private issue count", 0
    )
    if private_issues_truncated > private_issue_count:
        raise ValueError("native context pack private issue ledger is inconsistent")

    excluded_count = _require_integer(manifest["excludedCount"], "excluded count", 0)
    total_source_files = _require_integer(manifest["totalSourceFiles"], "source-file count", 1)
    naive_tokens = _require_integer(manifest["naiveDumpTokens"], "naive token count", 0)
    compiled_tokens = _require_integer(manifest["compiledTokens"], "compiled token count", 0)
    reduction_percent = _require_number(manifest["reductionPercent"], "reduction percent")
    _require_number(manifest["buildMilliseconds"], "build duration", 0)
    if total_source_files != len(entries) + excluded_count:
        raise ValueError("native context pack source-file counts are inconsistent")
    if compiled_tokens > maximum_tokens:
        raise ValueError("native context pack compiled tokens exceed policy")
    expected_reduction = (
        round((1 - compiled_tokens / naive_tokens) * 100, 3)
        if naive_tokens
        else 0.0
    )
    if reduction_percent != expected_reduction:
        raise ValueError("native context pack token reduction is inconsistent")
    _require_safe_ids(manifest["warnings"], "warnings")

    source_manifest_hash = _sha256(
        json.dumps(
            [
                {key: entry[key] for key in ("path", "sourceHash", "renderedHash")}
                for entry in entries
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    if manifest["sourceManifestHash"] != source_manifest_hash:
        raise ValueError("native context pack source manifest hash is inconsistent")
    if manifest["packId"] != stable_pack_id(manifest):
        raise ValueError("native context pack identity does not match its manifest")


def _require_relative_path(value: Any) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or ".." in Path(value).parts
    ):
        raise ValueError("native context pack paths must be repository-relative")
