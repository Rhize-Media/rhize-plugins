"""Fail-closed adapter for pinned grepai with local Ollama and GOB storage."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .context_compiler import ProviderHealth


PINNED_GREPAI_VERSION = "0.35.0"
PINNED_OLLAMA_MODEL = "nomic-embed-text:v1.5"
PINNED_OLLAMA_MANIFEST_DIGEST = (
    "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"
)
MAX_RESULTS = 50
MAX_OUTPUT_BYTES = 1_000_000
DENIED_PARTS = {".git", ".next", ".turbo", ".vercel", "node_modules", "coverage", "dist", "build", "vendor", "venv", ".venv"}
DENIED_NAMES = {".env", ".env.local", ".env.production", ".npmrc", ".pypirc", ".netrc", "auth.json", "cookies.json", "credentials", "credentials.json", "id_rsa", "id_ed25519", "service-account.json", "token.json"}
DENIED_SUFFIXES = {".cer", ".crt", ".der", ".jks", ".key", ".keystore", ".p12", ".pem", ".pfx"}
_VERSION = re.compile(r"(?<!\d)v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)(?!\d)")
_SHA256 = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True)
class GrepaiLayout:
    """Reviewed repository-relative grepai artifact locations."""

    config: Path
    index: Path
    snapshot_marker: Path


@dataclass(frozen=True)
class SearchCandidate:
    path: str
    score: float
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "score": self.score, "startLine": self.start_line, "endLine": self.end_line}


@dataclass(frozen=True)
class GrepaiSearchResult:
    manifest: dict[str, Any]
    candidates: tuple[SearchCandidate, ...]
    result_bytes: int


Runner = Callable[..., subprocess.CompletedProcess[Any]]


class GrepaiProvider:
    name = "grepai"

    def __init__(
        self,
        layout: GrepaiLayout,
        *,
        expected_config_sha256: str,
        executable: str | None = None,
        ollama_executable: str | None = None,
        expected_model_digest: str = PINNED_OLLAMA_MANIFEST_DIGEST,
        ollama_host: str = "http://127.0.0.1:11434",
        ollama_models_dir: Path | None = None,
        command_runner: Runner | None = None,
    ) -> None:
        self.layout = layout
        self.expected_config_sha256 = expected_config_sha256
        self.executable = executable if executable is not None else shutil.which("grepai")
        self.ollama_executable = ollama_executable if ollama_executable is not None else shutil.which("ollama")
        self.expected_version = PINNED_GREPAI_VERSION
        self.expected_model = PINNED_OLLAMA_MODEL
        self.expected_model_digest = expected_model_digest.removeprefix("sha256:")
        self.ollama_host = ollama_host
        configured_models = os.environ.get("OLLAMA_MODELS")
        self.ollama_models_dir = (ollama_models_dir or (Path(configured_models) if configured_models else Path.home() / ".ollama/models")).expanduser()
        self._run = command_runner or subprocess.run

    def doctor(self, repo_root: Path) -> ProviderHealth:
        """Check existing state only; never start grepai watch or an Ollama daemon."""

        error = self._configuration_error()
        if error:
            return ProviderHealth(False, error)
        try:
            version = self._run(self.version_command(), capture_output=True, text=True, timeout=5, check=False, env=self._local_env())
        except (OSError, subprocess.TimeoutExpired):
            return ProviderHealth(False, "cannot run the pinned grepai CLI")
        observed = _parse_version(f"{version.stdout or ''}\n{version.stderr or ''}")
        if version.returncode or observed != self.expected_version:
            return ProviderHealth(False, "installed grepai does not match the pinned version", observed)
        if not _local_endpoint(self.ollama_host):
            return ProviderHealth(False, "Ollama endpoint is not local", observed)
        try:
            models = self._run([self.ollama_executable, "list"], capture_output=True, text=True, timeout=5, check=False, env=self._local_env())
        except (OSError, subprocess.TimeoutExpired):
            return ProviderHealth(False, "local Ollama endpoint is unavailable", observed)
        names = {line.split()[0] for line in (models.stdout or "").splitlines()[1:] if line.split()}
        if models.returncode or self.expected_model not in names:
            return ProviderHealth(False, "pinned Ollama model is unavailable locally", observed)
        manifest = self._model_manifest()
        if not _regular(manifest) or _sha256(manifest) != self.expected_model_digest:
            return ProviderHealth(False, "local Ollama model does not match the pinned manifest", observed)
        try:
            repo = _repo(repo_root)
            if not self._single_worktree(repo):
                return ProviderHealth(False, "linked Git worktrees make grepai indexing unsafe", observed)
            config, index, marker = self._paths(repo)
            if not _regular(config) or _sha256(config) != self.expected_config_sha256:
                return ProviderHealth(False, "grepai config does not match its reviewed checksum", observed)
            if not _regular(index):
                return ProviderHealth(False, "local grepai GOB index is unavailable", observed)
            status = self._run(self.status_command(), cwd=repo, capture_output=True, text=True, timeout=5, check=False, env=self._local_env())
            current = self.inventory(repo)
            saved = json.loads(marker.read_text(encoding="utf-8")) if _regular(marker) else None
        except (OSError, RuntimeError, UnicodeError, ValueError, json.JSONDecodeError):
            return ProviderHealth(False, "cannot verify local grepai repository artifacts", observed)
        if status.returncode:
            return ProviderHealth(False, "grepai status check failed", observed)
        if saved != self._marker(repo, current, index):
            return ProviderHealth(False, "grepai index snapshot is stale or unverified", observed)
        return ProviderHealth(True, "pinned grepai and current local index verified", observed)

    def inventory(self, repo_root: Path, *, max_file_size: int = 1_000_000, max_file_count: int = 10_000) -> dict[str, Any]:
        """Build a metadata-only inventory; hard denies override ignore negations."""

        if max_file_size < 1 or max_file_count < 1:
            raise ValueError("grepai inventory limits must be positive")
        repo = _repo(repo_root)
        listed = self._git(repo, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
        ignored = self._ignored(repo, listed.stdout)
        included: list[dict[str, Any]] = []
        excluded: list[dict[str, str]] = []
        for raw in sorted(item for item in listed.stdout.split(b"\0") if item):
            relative = _relative(raw.decode("utf-8", errors="strict"))
            path = repo / relative
            reason = _deny_reason(path, relative, max_file_size)
            if reason is None and relative.as_posix() in ignored:
                reason = "git_or_grepai_ignore"
            if reason:
                excluded.append({"path": relative.as_posix(), "reason": reason})
            else:
                content = path.read_bytes()
                included.append({"path": relative.as_posix(), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        if len(included) > max_file_count:
            raise ValueError("grepai inventory exceeds the file-count cap")
        digest = hashlib.sha256(json.dumps(included, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"schemaVersion": 1, "repoId": _repo_id(repo), "snapshot": self._snapshot(repo), "inventorySha256": digest, "included": included, "excluded": excluded}

    def build_snapshot_marker(self, repo_root: Path) -> dict[str, Any]:
        """Build evidence for the caller to persist after foreground indexing succeeds."""

        repo = _repo(repo_root)
        if not self._single_worktree(repo):
            raise RuntimeError("linked Git worktrees make grepai indexing unsafe")
        config, index, _ = self._paths(repo)
        if not _regular(config) or _sha256(config) != self.expected_config_sha256 or not _regular(index):
            raise RuntimeError("reviewed grepai config or local index is unavailable")
        return self._marker(repo, self.inventory(repo), index)

    def version_command(self) -> list[str]:
        return [self._executable(), "version"]

    def init_command(self, repo_root: Path) -> list[str]:
        if not self._single_worktree(_repo(repo_root)):
            raise RuntimeError("linked Git worktrees make grepai initialization unsafe")
        return [self._executable(), "init", "--provider", "ollama", "--backend", "gob", "--yes"]

    def index_command(self, repo_root: Path) -> list[str]:
        """Foreground-only index command; caller must bound it and send SIGINT after readiness."""

        repo = _repo(repo_root)
        if not self._single_worktree(repo):
            raise RuntimeError("linked Git worktrees make grepai indexing unsafe")
        config, _, _ = self._paths(repo)
        if not _regular(config) or _sha256(config) != self.expected_config_sha256:
            raise RuntimeError("grepai config does not match its reviewed checksum")
        return [self._executable(), "watch", "--no-ui"]

    def status_command(self) -> list[str]:
        return [self._executable(), "status", "--no-ui"]

    def cleanup_commands(self) -> tuple[list[str], list[str]]:
        """Return explicit watcher inspection/stop commands; never delete artifacts implicitly."""

        return ([self._executable(), "watch", "--status"], [self._executable(), "watch", "--stop"])

    def search(self, repo_root: Path, query: str, *, limit: int = 10, timeout: int = 30) -> GrepaiSearchResult:
        repo = _repo(repo_root)
        if not query.strip() or len(query) > 4096 or "\0" in query or not 1 <= limit <= MAX_RESULTS:
            raise ValueError("grepai query or result limit is invalid")
        if not 1 <= timeout <= 30:
            raise ValueError("grepai timeout must be between 1 and 30 seconds")
        health = self.doctor(repo)
        if not health.ready:
            raise RuntimeError(health.note)
        try:
            result = self._run([self._executable(), "search", query, "--json", "--compact"], cwd=repo, capture_output=True, text=True, timeout=timeout, check=False, env=self._local_env())
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("grepai search exceeded its bounded timeout") from error
        except OSError as error:
            raise RuntimeError("cannot run local grepai search") from error
        output = result.stdout or ""
        if result.returncode:
            raise RuntimeError("local grepai search failed")
        output_bytes = len(output.encode())
        if output_bytes > MAX_OUTPUT_BYTES:
            raise RuntimeError("grepai search output is too large")
        current = self.inventory(repo)
        eligible = {row["path"] for row in current["included"]}
        candidates = _parse_results(output, repo, eligible)[:limit]
        _, index, marker = self._paths(repo)
        saved = json.loads(marker.read_text(encoding="utf-8")) if _regular(marker) else None
        if saved != self._marker(repo, current, index):
            raise RuntimeError("grepai index snapshot became stale during search")
        manifest = {"schemaVersion": 1, "provider": "grepai", "providerVersion": health.version, "model": self.expected_model, "repoId": _repo_id(repo), "queryHash": hashlib.sha256(query.encode()).hexdigest(), "snapshot": current["snapshot"], "indexedSnapshot": saved["snapshot"], "snapshotCurrent": True, "candidateCount": len(candidates)}
        return GrepaiSearchResult(manifest, candidates, output_bytes)

    def _configuration_error(self) -> str | None:
        if not self.executable:
            return "grepai is not installed"
        if not self.ollama_executable:
            return "Ollama CLI is not installed"
        if not _VERSION.fullmatch(self.expected_version) or not _SHA256.fullmatch(self.expected_config_sha256) or not _SHA256.fullmatch(self.expected_model_digest):
            return "grepai pins or reviewed config checksum are invalid"
        try:
            for path in (self.layout.config, self.layout.index, self.layout.snapshot_marker):
                _relative(path.as_posix())
        except ValueError:
            return "grepai artifact layout is invalid"
        return None

    def _paths(self, repo: Path) -> tuple[Path, Path, Path]:
        paths = tuple(repo / _relative(path.as_posix()) for path in (self.layout.config, self.layout.index, self.layout.snapshot_marker))
        try:
            for path in paths:
                path.resolve(strict=False).relative_to(repo)
        except ValueError as error:
            raise ValueError("grepai artifact path escapes the repository") from error
        return paths  # type: ignore[return-value]

    def _model_manifest(self) -> Path:
        name, tag = self.expected_model.rsplit(":", 1)
        return self.ollama_models_dir / "manifests/registry.ollama.ai/library" / name / tag

    def _local_env(self) -> dict[str, str]:
        return {**os.environ, "OLLAMA_HOST": self.ollama_host, "OLLAMA_NO_CLOUD": "1"}

    def _executable(self) -> str:
        if not self.executable:
            raise RuntimeError("grepai is not installed")
        return self.executable

    def _git(self, repo: Path, args: list[str], *, input: bytes | None = None) -> subprocess.CompletedProcess[Any]:
        try:
            result = self._run(["git", "-C", str(repo), *args], input=input, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("local git inventory check failed") from error
        if result.returncode not in {0, 1} or not isinstance(result.stdout, bytes):
            raise RuntimeError("local git inventory check failed")
        return result

    def _ignored(self, repo: Path, candidates: bytes) -> set[str]:
        outputs = [self._git(repo, ["check-ignore", "--no-index", "--stdin", "-z"], input=candidates).stdout]
        ignore_file = repo / ".grepaiignore"
        if ignore_file.is_file() and not ignore_file.is_symlink():
            outputs.append(self._git(repo, ["-c", f"core.excludesFile={ignore_file}", "check-ignore", "--no-index", "--stdin", "-z"], input=candidates).stdout)
        return {item.decode("utf-8", errors="strict") for output in outputs for item in output.split(b"\0") if item}

    def _snapshot(self, repo: Path) -> str:
        commit = self._git(repo, ["rev-parse", "HEAD"]).stdout.decode("ascii").strip()
        status = self._git(repo, ["status", "--porcelain=v1", "-z"]).stdout
        if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
            raise RuntimeError("repository snapshot is invalid")
        return commit if not status else f"{commit}-dirty-{hashlib.sha256(status).hexdigest()[:16]}"

    def _single_worktree(self, repo: Path) -> bool:
        output = self._git(repo, ["worktree", "list", "--porcelain"]).stdout
        roots = [Path(line[9:].decode("utf-8", errors="strict")).resolve(strict=False) for line in output.splitlines() if line.startswith(b"worktree ")]
        return roots == [repo]

    def _marker(self, repo: Path, inventory: dict[str, Any], index: Path) -> dict[str, Any]:
        stat = index.stat()
        # grepai rewrites GOB metadata during its read-only ``status`` command, so
        # neither the file mtime nor a whole-file digest is a stable freshness key.
        # Source freshness is instead bound to the independently hashed inventory
        # and Git snapshot. Size is retained as a coarse non-empty artifact check.
        return {"schemaVersion": 1, "provider": "grepai", "providerVersion": self.expected_version, "model": self.expected_model, "modelManifestDigest": self.expected_model_digest, "repoId": _repo_id(repo), "snapshot": inventory["snapshot"], "inventorySha256": inventory["inventorySha256"], "configSha256": self.expected_config_sha256, "indexSize": stat.st_size}


def _parse_results(output: str, repo: Path, eligible: set[str]) -> tuple[SearchCandidate, ...]:
    try:
        rows = json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError("grepai search returned malformed JSON") from error
    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError("grepai search returned an error payload")
    if not isinstance(rows, list):
        raise RuntimeError("grepai search JSON has an unsupported shape")
    candidates = []
    seen_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not {"file_path", "start_line", "end_line", "score"} <= set(row):
            raise RuntimeError("grepai search candidate has an unsupported shape")
        path, start, end, score = row["file_path"], row["start_line"], row["end_line"], row["score"]
        if not isinstance(path, str) or isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise RuntimeError("grepai search candidate metadata is invalid")
        if isinstance(start, bool) or not isinstance(start, int) or start < 1 or isinstance(end, bool) or not isinstance(end, int) or end < start:
            raise RuntimeError("grepai search candidate line range is invalid")
        try:
            relative = _relative(path).as_posix()
        except ValueError as error:
            raise RuntimeError("grepai search returned a non-relative path") from error
        file = repo / relative
        if relative not in eligible or not file.is_file() or file.is_symlink():
            raise RuntimeError("grepai search returned a denied or unindexed path")
        if relative in seen_paths:
            continue
        seen_paths.add(relative)
        candidates.append(SearchCandidate(relative, float(score), start, end))
    return tuple(candidates)


def _relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."} or "\\" in value or "\0" in value or re.match(r"^[A-Za-z]:", value):
        raise ValueError("path must be repository-relative")
    return path


def _deny_reason(path: Path, relative: Path, max_size: int) -> str | None:
    if path.is_symlink(): return "symlink"
    if not path.is_file(): return "not_regular_file"
    if any(part.startswith(".") for part in relative.parts): return "hidden_path"
    if any(part in DENIED_PARTS for part in relative.parts): return "denied_directory"
    if path.name in DENIED_NAMES or path.name.startswith(".env."): return "secret_filename"
    if path.suffix.lower() in DENIED_SUFFIXES: return "secret_suffix"
    if path.stat().st_size > max_size: return "file_size_cap"
    return None


def _parse_version(output: str) -> str | None:
    versions = {match.group(1) for match in _VERSION.finditer(output)}
    return next(iter(versions)) if len(versions) == 1 else None


def _local_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}


def _repo(path: Path) -> Path:
    repo = path.expanduser().resolve(strict=True)
    if not repo.is_dir():
        raise ValueError("repository root must be a directory")
    return repo


def _regular(path: Path) -> bool:
    return not path.is_symlink() and path.is_file() and path.stat().st_size > 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_id(repo: Path) -> str:
    return hashlib.sha256(str(repo).encode()).hexdigest()[:16]
