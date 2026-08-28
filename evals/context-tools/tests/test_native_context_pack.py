from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import context_experiments.providers.native_context_pack as native_provider
from context_experiments.providers.native_context_pack import (
    NativeContextPackProvider,
    validate_native_context_pack_manifest,
)
from context_experiments.runner import build_native_context_pack_preview, git_snapshot


def commit_fixture(repo: Path) -> str:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    snapshot = git_snapshot(repo)
    assert snapshot is not None
    return snapshot


def write_static_typescript_fixture(repo: Path) -> None:
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "types.ts").write_text(
        "export interface User { id: string }\nexport const hidden = 3;\n",
        encoding="utf-8",
    )
    (repo / "src" / "service.ts").write_text(
        "import type { User } from './types';\nexport function load(user: User) { return user.id; }\n",
        encoding="utf-8",
    )
    (repo / "src" / "app.ts").write_text(
        "import { load } from './service';\nexport const value = load({id: '1'});\n",
        encoding="utf-8",
    )
    (repo / "tests" / "app.test.ts").write_text(
        "import { value } from '../src/app';\nif (!value) throw new Error('app failed');\n",
        encoding="utf-8",
    )
    (repo / "package.json").write_text('{"scripts":{"test":"node tests/app.test.ts"}}\n')


def test_native_pack_selects_full_targets_interfaces_and_related_support(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    snapshot = commit_fixture(repo)

    manifest, manifest_path, prompt_path = build_native_context_pack_preview(
        repo,
        snapshot,
        target_files=(repo / "src" / "app.ts",),
        data_dir=tmp_path / "data",
    )

    validate_native_context_pack_manifest(manifest)
    by_path = {entry["path"]: entry for entry in manifest["entries"]}
    assert by_path["src/app.ts"]["role"] == "FULL"
    assert by_path["src/service.ts"]["role"] == "INTERFACE"
    assert by_path["src/types.ts"]["role"] == "INTERFACE"
    assert by_path["tests/app.test.ts"]["reason"] == "related_test"
    assert by_path["package.json"]["reason"] == "nearby_configuration"
    assert manifest["policy"]["acceptedForUse"] is True
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert prompt_path.stat().st_mode & 0o777 == 0o600
    assert str(repo) not in prompt_path.read_text(encoding="utf-8")


def test_native_pack_is_reproducible_and_detects_stale_entries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    snapshot = commit_fixture(repo)
    first = build_native_context_pack_preview(
        repo,
        snapshot,
        target_files=(repo / "src" / "app.ts",),
        data_dir=tmp_path / "data",
    )
    second = build_native_context_pack_preview(
        repo,
        snapshot,
        target_files=(repo / "src" / "app.ts",),
        data_dir=tmp_path / "data",
    )
    assert first[0]["packId"] == second[0]["packId"]
    assert first[1:] == second[1:]

    (repo / "src" / "service.ts").write_text("export function load() { return 'changed'; }\n")
    current = git_snapshot(repo)
    assert current is not None
    result = NativeContextPackProvider().verify_pack(first[0], repo, current)
    assert result.valid is False
    assert result.snapshot_current is False
    assert result.changed_entries == ("src/service.ts",)


def test_query_discovery_falls_back_explicitly_when_codegraph_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    (repo / ".codegraph").mkdir()
    snapshot = commit_fixture(repo)
    monkeypatch.setenv("PATH", "")

    provider = NativeContextPackProvider()
    pack = provider.compile(
        repo,
        snapshot=snapshot,
        task_hash="a" * 64,
        query="change app load behavior",
    )
    assert pack.manifest["discovery"]["strategy"] == "baseline"
    assert "codegraph_discovery_unavailable_fell_back" in pack.manifest["warnings"]
    assert pack.manifest["discovery"]["queryHash"] is not None


def test_query_discovery_uses_codegraph_first_when_the_index_exists(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    (repo / ".codegraph").mkdir()
    snapshot = commit_fixture(repo)
    calls: list[str] = []

    def discover(_repo: Path, _paths: tuple[Path, ...], query: str) -> tuple[Path, ...]:
        calls.append(query)
        return (repo / "src" / "app.ts",)

    monkeypatch.setattr(native_provider, "_codegraph_targets", discover)
    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="d" * 64,
        query="change the app behavior",
    )
    assert calls == ["change the app behavior"]
    assert pack.manifest["discovery"]["strategy"] == "codegraph"
    assert pack.manifest["discovery"]["targetPaths"] == ["src/app.ts"]


def test_dynamic_dependency_edges_reject_use_without_hiding_the_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "dispatcher.js").write_text(
        "export function dispatch(name) { return import(`./${name}.js`); }\n",
        encoding="utf-8",
    )
    snapshot = commit_fixture(repo)
    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="b" * 64,
        targets=(repo / "dispatcher.js",),
    )
    assert pack.manifest["policy"]["acceptedForUse"] is False
    assert pack.manifest["policy"]["rejectionReasons"] == ["dynamic_dependency_edge"]
    assert pack.manifest["entries"][0]["path"] == "dispatcher.js"


def test_manifest_contains_no_source_or_absolute_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    snapshot = commit_fixture(repo)
    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="c" * 64,
        targets=(repo / "src" / "app.ts",),
    )
    serialized = json.dumps(pack.manifest, sort_keys=True)
    assert str(repo) not in serialized
    assert "export const value" not in serialized

    malformed = {**pack.manifest, "snapshot": "/absolute/snapshot"}
    with pytest.raises(ValueError, match="invalid snapshot"):
        validate_native_context_pack_manifest(malformed)
