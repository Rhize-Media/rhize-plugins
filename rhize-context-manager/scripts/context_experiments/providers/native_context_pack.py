"""Deterministic, local-only context packs for mixed-language repositories."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .context_compiler import CompiledPack, ProviderHealth, stable_pack_id


PROVIDER_REVISION = "rhize-native-context-pack-v1"
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
CONFIG_NAMES = {
    "package.json",
    "pyproject.toml",
    "tsconfig.json",
    "vite.config.js",
    "vite.config.ts",
}
MAX_SOURCE_BYTES = 512_000


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    snapshot_current: bool
    changed_entries: tuple[str, ...]
    missing_entries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "snapshotCurrent": self.snapshot_current,
            "changedEntries": list(self.changed_entries),
            "missingEntries": list(self.missing_entries),
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
        max_hops: int = 2,
        max_tokens: int = 40_000,
    ) -> CompiledPack:
        started = time.monotonic()
        repo = repo_root.expanduser().resolve(strict=True)
        if not repo.is_dir():
            raise ValueError("repository root must be a directory")
        if not 1 <= max_hops <= 5:
            raise ValueError("max_hops must be between 1 and 5")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        source_paths = _source_paths(repo)
        if not source_paths:
            raise ValueError("repository contains no supported source files")
        target_paths, strategy, discovery_warnings = _discover_targets(
            repo, source_paths, targets, query
        )
        if not target_paths:
            raise ValueError("native context-pack discovery found no target")

        edge_warnings: set[str] = set(discovery_warnings)
        selected_distance: dict[Path, int] = {path: 0 for path in target_paths}
        frontier = list(target_paths)
        for hop in range(max_hops):
            next_frontier: list[Path] = []
            for path in frontier:
                dependencies, warnings = _dependencies(repo, path)
                edge_warnings.update(warnings)
                for dependency in dependencies:
                    if dependency not in selected_distance:
                        selected_distance[dependency] = hop + 1
                        next_frontier.append(dependency)
            frontier = next_frontier
            if not frontier:
                break

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
                _role_order(item[1]),
                item[3],
                item[0].relative_to(repo).as_posix(),
            )
        )

        entries: list[dict[str, Any]] = []
        rendered: list[tuple[dict[str, Any], str]] = []
        used_tokens = 0
        budget_truncated = False
        seen: set[Path] = set()
        for path, role, reason, _distance in candidates:
            if path in seen:
                continue
            seen.add(path)
            content = path.read_text(encoding="utf-8", errors="replace")
            selected_content = content if role == "FULL" else _interface_content(path, content)
            token_count = _estimate_tokens(selected_content)
            if used_tokens + token_count > max_tokens:
                if role == "FULL" and path in target_paths:
                    edge_warnings.add("required_target_exceeds_token_budget")
                else:
                    budget_truncated = True
                continue
            relative = path.relative_to(repo).as_posix()
            entry = {
                "path": relative,
                "role": role,
                "reason": reason,
                "sourceHash": _sha256(path.read_bytes()),
                "renderedHash": _sha256(selected_content.encode()),
                "estimatedTokens": token_count,
            }
            entries.append(entry)
            rendered.append((entry, selected_content))
            used_tokens += token_count
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

        all_warnings = sorted(edge_warnings)
        rejection_reasons = sorted(
            warning
            for warning in all_warnings
            if warning
            in {
                "ambiguous_dependency_name_collision",
                "dynamic_dependency_edge",
                "required_target_exceeds_token_budget",
                "unsupported_source_syntax",
            }
        )
        naive_tokens = sum(
            _estimate_tokens(path.read_text(encoding="utf-8", errors="replace"))
            for path in source_paths
        )
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
            "repoId": _sha256(str(repo).encode())[:16],
            "snapshot": snapshot,
            "taskHash": task_hash,
            "provider": {"name": self.name, "revision": PROVIDER_REVISION},
            "discovery": {
                "strategy": strategy,
                "queryHash": _sha256(query.strip().encode()) if query and query.strip() else None,
                "targetPaths": [path.relative_to(repo).as_posix() for path in target_paths],
            },
            "entries": entries,
            "excludedCount": max(
                0, len(source_paths) - len({entry["path"] for entry in entries})
            ),
            "totalSourceFiles": len(source_paths),
            "naiveDumpTokens": naive_tokens,
            "compiledTokens": used_tokens,
            "reductionPercent": (
                round((1 - used_tokens / naive_tokens) * 100, 3)
                if naive_tokens
                else 0.0
            ),
            "buildMilliseconds": round((time.monotonic() - started) * 1000, 3),
            "sourceManifestHash": source_manifest_hash,
            "policy": {
                "acceptedForUse": not rejection_reasons,
                "maximumTokens": max_tokens,
                "rejectionReasons": rejection_reasons,
            },
            "warnings": all_warnings,
        }
        manifest["packId"] = stable_pack_id(manifest)
        prompt = _render_prompt(manifest, rendered)
        return CompiledPack(manifest=manifest, prompt=prompt)

    def write_pack(self, pack: CompiledPack, directory: Path) -> tuple[Path, Path]:
        validate_native_context_pack_manifest(pack.manifest)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
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
        self, manifest: dict[str, Any], repo_root: Path, current_snapshot: str
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
        return VerificationResult(
            valid=snapshot_current and not changed and not missing,
            snapshot_current=snapshot_current,
            changed_entries=tuple(sorted(changed)),
            missing_entries=tuple(sorted(missing)),
        )


def _source_paths(repo: Path) -> tuple[Path, ...]:
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
    paths = []
    for relative in relative_paths:
        path = repo / relative
        if (
            path.is_file()
            and not path.is_symlink()
            and path.stat().st_size <= MAX_SOURCE_BYTES
            and (path.suffix in SOURCE_SUFFIXES or path.name in CONFIG_NAMES)
            and not any(
                part in {"node_modules", ".git", "dist", "build"}
                for part in relative.parts
            )
        ):
            paths.append(path.resolve())
    return tuple(sorted(set(paths), key=lambda path: path.relative_to(repo).as_posix()))


def _discover_targets(
    repo: Path,
    source_paths: tuple[Path, ...],
    targets: Iterable[Path],
    query: str | None,
) -> tuple[tuple[Path, ...], str, tuple[str, ...]]:
    explicit = tuple(_safe_target(repo, target) for target in targets)
    if explicit:
        return tuple(sorted(set(explicit))), "explicit", ()
    if not query or not query.strip():
        raise ValueError("native context-pack requires --target or --query")
    warnings: list[str] = []
    if (repo / ".codegraph").is_dir():
        discovered = _codegraph_targets(repo, source_paths, query)
        if discovered:
            return discovered, "codegraph", ()
        warnings.append("codegraph_discovery_unavailable_fell_back")
    discovered = _baseline_targets(repo, source_paths, query)
    return discovered, "baseline", tuple(warnings)


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


def _dependencies(repo: Path, path: Path) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    content = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return _python_dependencies(repo, path, content)
    return _javascript_dependencies(repo, path, content)


def _python_dependencies(
    repo: Path, path: Path, content: str
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return (), ("unsupported_source_syntax",)
    dependencies: set[Path] = set()
    warnings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            base = path.parent
            for _ in range(max(0, node.level - 1)):
                base = base.parent
            modules = [module] if module else [alias.name for alias in node.names]
            for imported_module in modules:
                resolved = _resolve_python_module(
                    repo, base if node.level else repo, imported_module
                )
                if resolved:
                    dependencies.add(resolved)
                elif node.level:
                    warnings.add("unresolved_local_dependency")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_python_module(repo, repo, alias.name)
                if resolved:
                    dependencies.add(resolved)
    return tuple(sorted(dependencies)), tuple(sorted(warnings))


def _resolve_python_module(repo: Path, base: Path, module: str) -> Path | None:
    relative = Path(*module.split(".")) if module else Path()
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


def _javascript_dependencies(
    repo: Path, path: Path, content: str
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    specs = re.findall(
        r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']"
        r"|require\(\s*[\"']([^\"']+)[\"']\s*\)",
        content,
    )
    dependencies: set[Path] = set()
    warnings: set[str] = set()
    for pair in specs:
        spec = next((value for value in pair if value), "")
        if not spec.startswith("."):
            continue
        resolved = _resolve_javascript_spec(repo, path.parent, spec)
        if resolved:
            dependencies.add(resolved)
        else:
            warnings.add("unresolved_local_dependency")
    return tuple(sorted(dependencies)), tuple(sorted(warnings))


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


def _interface_content(path: Path, content: str) -> str:
    if path.suffix == ".py":
        lines = []
        for line in content.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("import ", "from ", "class ", "def ", "async def ")):
                lines.append(line.rstrip())
        return "\n".join(lines) + ("\n" if lines else "")
    lines = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(
            ("import ", "export ", "interface ", "type ", "class ", "function ", "const ")
        ):
            lines.append(line.rstrip())
    return "\n".join(lines) + ("\n" if lines else "")


def _render_prompt(
    manifest: dict[str, Any], rendered: list[tuple[dict[str, Any], str]]
) -> str:
    lines = [
        "# Rhize native context pack",
        "",
        f"Pack: {manifest['packId']}",
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


def validate_native_context_pack_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schemaVersion", "packId", "repoId", "snapshot", "taskHash", "provider",
        "discovery", "entries", "excludedCount", "totalSourceFiles", "naiveDumpTokens",
        "compiledTokens", "reductionPercent", "buildMilliseconds", "sourceManifestHash",
        "policy", "warnings",
    }
    if set(manifest) != required or manifest.get("schemaVersion") != 2:
        raise ValueError("native context pack manifest has an invalid top-level shape")
    if not re.fullmatch(r"pack-[a-f0-9]{32}", str(manifest["packId"])):
        raise ValueError("native context pack has an invalid packId")
    if not re.fullmatch(r"[a-f0-9]{16}", str(manifest["repoId"])):
        raise ValueError("native context pack has an invalid repoId")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest["taskHash"])):
        raise ValueError("native context pack has an invalid taskHash")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", str(manifest["snapshot"])
    ):
        raise ValueError("native context pack has an invalid snapshot")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest["sourceManifestHash"])):
        raise ValueError("native context pack has an invalid source manifest hash")
    if manifest.get("provider") != {"name": "rhize-native", "revision": PROVIDER_REVISION}:
        raise ValueError("native context pack provider provenance is invalid")
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
        for key in ("sourceHash", "renderedHash"):
            if not re.fullmatch(r"[a-f0-9]{64}", str(entry[key])):
                raise ValueError("native context pack entry has an invalid hash")
    discovery = manifest.get("discovery")
    if not isinstance(discovery, dict) or set(discovery) != {
        "strategy", "queryHash", "targetPaths"
    }:
        raise ValueError("native context pack discovery is invalid")
    if discovery["strategy"] not in {"explicit", "baseline", "codegraph"}:
        raise ValueError("native context pack discovery strategy is invalid")
    for path in discovery["targetPaths"]:
        _require_relative_path(path)
    query_hash = discovery["queryHash"]
    if query_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", str(query_hash)):
        raise ValueError("native context pack query hash is invalid")
    policy = manifest.get("policy")
    if not isinstance(policy, dict) or set(policy) != {
        "acceptedForUse", "maximumTokens", "rejectionReasons"
    }:
        raise ValueError("native context pack policy is invalid")
    if not isinstance(policy["acceptedForUse"], bool):
        raise ValueError("native context pack policy verdict is invalid")


def _require_relative_path(value: Any) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or ".." in Path(value).parts
    ):
        raise ValueError("native context pack paths must be repository-relative")
