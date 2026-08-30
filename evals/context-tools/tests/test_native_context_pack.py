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
    (repo / "src" / "unused.ts").write_text(
        "\n".join(f"export const unused{index} = {index};" for index in range(50)),
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
    assert first[0] == second[0]
    assert first[1:] == second[1:]

    (repo / "src" / "service.ts").write_text("export function load() { return 'changed'; }\n")
    current = git_snapshot(repo)
    assert current is not None
    result = NativeContextPackProvider().verify_pack(first[0], repo, current, first[2])
    assert result.valid is False
    assert result.snapshot_current is False
    assert result.prompt_current is True
    assert result.changed_entries == ("src/service.ts",)


def test_native_pack_verification_binds_manifest_and_prompt_bytes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    snapshot = commit_fixture(repo)
    manifest, manifest_path, prompt_path = build_native_context_pack_preview(
        repo,
        snapshot,
        target_files=(repo / "src" / "app.ts",),
        data_dir=tmp_path / "data",
    )
    provider = NativeContextPackProvider()
    assert provider.verify_pack(manifest, repo, snapshot, prompt_path).valid is True

    prompt_path.write_text(prompt_path.read_text() + "\nmodified\n")
    prompt_path.chmod(0o600)
    tampered_prompt = provider.verify_pack(manifest, repo, snapshot, prompt_path)
    assert tampered_prompt.valid is False
    assert tampered_prompt.prompt_current is False

    tampered_manifest = json.loads(manifest_path.read_text())
    tampered_manifest["taskHash"] = "f" * 64
    with pytest.raises(ValueError, match="identity does not match"):
        provider.verify_pack(tampered_manifest, repo, snapshot, prompt_path)


def test_fixed_fixture_manifest_is_portable_across_host_roots(tmp_path: Path) -> None:
    first_repo = tmp_path / "host-a" / "project"
    second_repo = tmp_path / "host-b" / "project"
    write_static_typescript_fixture(first_repo)
    write_static_typescript_fixture(second_repo)
    snapshot = "fixture-" + "a" * 32

    first = NativeContextPackProvider().compile(
        first_repo,
        snapshot=snapshot,
        task_hash="8" * 64,
        targets=(first_repo / "src" / "app.ts",),
    )
    second = NativeContextPackProvider().compile(
        second_repo,
        snapshot=snapshot,
        task_hash="8" * 64,
        targets=(second_repo / "src" / "app.ts",),
    )

    assert first.manifest == second.manifest
    assert first.prompt == second.prompt


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
    assert pack.manifest["discovery"]["strategy"] == "rg"
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
    monkeypatch.setattr(native_provider, "_codegraph_healthy", lambda _repo: True)
    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="d" * 64,
        query="change the app behavior",
    )
    assert calls == ["change the app behavior"]
    assert pack.manifest["discovery"]["strategy"] == "codegraph"
    assert pack.manifest["discovery"]["targetPaths"] == ["src/app.ts"]


def test_impact_map_hint_expands_local_discovery_with_hash_only_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "decoy.py").write_text("def refresh_lifecycle():\n    return 'decoy'\n")
    (repo / "tenant_policy.py").write_text("def enforce_tenant_policy():\n    return True\n")
    plan_dir = repo / ".claude" / "plans"
    plan_dir.mkdir(parents=True)
    plan = plan_dir / "tenant-refresh.md"
    plan.write_text(
        "# Impact Map\n\n## Current structural touchpoints\n"
        "- `tenant_policy.py`: planned tenant authorization boundary.\n"
    )
    snapshot = commit_fixture(repo)
    monkeypatch.setattr(native_provider.shutil, "which", lambda command: "/usr/bin/rg" if command == "rg" else None)

    baseline = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="2" * 64,
        query="refresh lifecycle behavior",
    )
    assisted = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="3" * 64,
        query="refresh lifecycle behavior",
        impact_hint=plan,
    )

    assert "tenant_policy.py" not in baseline.manifest["discovery"]["targetPaths"]
    assert "tenant_policy.py" in assisted.manifest["discovery"]["targetPaths"]
    assert assisted.manifest["discovery"]["strategy"] == "impact_rg"
    provenance = assisted.manifest["impactHint"]
    assert set(provenance) == {"contentHash", "present", "seedCount", "termSetHash"}
    assert provenance["present"] is True
    assert len(provenance["contentHash"]) == 64
    assert str(plan) not in json.dumps(assisted.manifest)
    assert "tenant authorization boundary" not in json.dumps(assisted.manifest)


def test_impact_map_uses_only_healthy_existing_codegraph_then_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    plan_dir = repo / ".claude" / "plans"
    plan_dir.mkdir(parents=True)
    plan = plan_dir / "app.md"
    plan.write_text("- `src/app.ts`: application entry point\n")
    (repo / ".codegraph").mkdir()
    snapshot = commit_fixture(repo)
    calls: list[str] = []
    monkeypatch.setattr(native_provider, "_codegraph_healthy", lambda _repo: False)
    monkeypatch.setattr(
        native_provider,
        "_codegraph_targets",
        lambda *_args: calls.append("explore") or (),
    )

    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="4" * 64,
        query="change application behavior",
        impact_hint=plan,
    )
    assert calls == []
    assert pack.manifest["discovery"]["strategy"] == "impact_rg"
    assert "codegraph_discovery_unavailable_fell_back" in pack.manifest["warnings"]


def test_impact_map_hint_rejects_repository_local_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n")
    plan = repo / "plan.md"
    plan.write_text("Inspect `app.py`.\n")
    linked_plan = repo / "linked-plan.md"
    linked_plan.symlink_to(plan)
    snapshot = commit_fixture(repo)

    with pytest.raises(ValueError, match="regular repository-local markdown"):
        NativeContextPackProvider().compile(
            repo,
            snapshot=snapshot,
            task_hash="8" * 64,
            query="inspect app",
            impact_hint=linked_plan,
        )


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
    assert "dynamic_dependency_edge" in pack.manifest["policy"]["rejectionReasons"]
    assert "insufficient_compilation_benefit" in pack.manifest["policy"]["rejectionReasons"]
    assert pack.manifest["entries"][0]["path"] == "dispatcher.js"


def test_unresolved_local_dependencies_reject_use(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.ts"
    target.write_text(
        "import { missing } from './missing';\nexport const value = missing();\n",
        encoding="utf-8",
    )
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="e" * 64,
        targets=(target,),
    )

    assert pack.manifest["policy"]["acceptedForUse"] is False
    assert "unresolved_local_dependency" in pack.manifest["policy"]["rejectionReasons"]


def test_dependency_hop_truncation_rejects_use(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "types.ts").write_text("export interface User { id: string }\n")
    (repo / "service.ts").write_text(
        "import type { User } from './types';\nexport const load = (user: User) => user.id;\n"
    )
    target = repo / "app.ts"
    target.write_text("import { load } from './service';\nexport const value = load({id: '1'});\n")
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="f" * 64,
        targets=(target,),
        max_hops=1,
    )

    assert pack.manifest["policy"]["acceptedForUse"] is False
    assert "dependency_traversal_truncated" in pack.manifest["policy"]["rejectionReasons"]


def test_required_dependency_omitted_by_budget_rejects_use(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    dependency = repo / "service.ts"
    dependency.write_text(
        "\n".join(f"export const value{index} = {index};" for index in range(100)) + "\n"
    )
    target = repo / "app.ts"
    target.write_text("import { value0 } from './service';\nexport const value = value0;\n")
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="1" * 64,
        targets=(target,),
        max_tokens=40,
    )

    assert pack.manifest["policy"]["acceptedForUse"] is False
    assert "required_dependency_exceeds_token_budget" in pack.manifest["policy"]["rejectionReasons"]


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

def test_python_multiline_decorated_contract_is_complete(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "from typing import overload\n\n"
        "@overload\n"
        "def load(\n    value: str,\n    *,\n    strict: bool = False,\n) -> str:\n    ...\n\n"
        "def load(value: str, *, strict: bool = False) -> str:\n    return value\n"
    )
    target = repo / "app.py"
    target.write_text("from service import load\n\nresult = load('x')\n")
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(50)))
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="2" * 64, targets=(target,)
    )

    entry = next(item for item in pack.manifest["entries"] if item["path"] == "service.py")
    assert entry["role"] == "INTERFACE"
    assert "@overload\ndef load(\n    value: str" in pack.prompt
    assert "strict: bool = False" in pack.prompt
    assert pack.manifest["policy"]["acceptedForUse"] is True


def test_typescript_path_alias_and_workspace_exports_resolve(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "apps" / "web" / "src").mkdir(parents=True)
    (repo / "packages" / "shared" / "src").mkdir(parents=True)
    (repo / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["apps/web/src/*"]}}})
    )
    (repo / "package.json").write_text(json.dumps({"workspaces": ["apps/*", "packages/*"]}))
    (repo / "packages" / "shared" / "package.json").write_text(
        json.dumps({"name": "@rhize/shared", "exports": {"./feature": "./src/feature.ts"}})
    )
    (repo / "packages" / "shared" / "src" / "feature.ts").write_text(
        "export interface Feature { id: string }\n"
    )
    (repo / "apps" / "web" / "src" / "local.ts").write_text(
        "export function local(value: string): string { return value; }\n"
    )
    target = repo / "apps" / "web" / "src" / "app.ts"
    target.write_text(
        "import { local } from '@app/local';\n"
        "import type { Feature } from '@rhize/shared/feature';\n"
        "export const value: Feature = { id: local('x') };\n"
    )
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="3" * 64, targets=(target,)
    )

    paths = {item["path"] for item in pack.manifest["entries"]}
    assert "apps/web/src/local.ts" in paths
    assert "packages/shared/src/feature.ts" in paths
    assert "unresolved_local_dependency" not in pack.manifest["warnings"]


def test_typescript_multiline_import_and_generic_contract_are_complete(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "service.ts").write_text(
        "export interface Result<T extends string> {\n"
        "  readonly value: T;\n"
        "}\n"
        "export function load<T extends string>(\n"
        "  value: T,\n"
        "  options?: { strict: boolean },\n"
        "): Promise<Result<T>> {\n"
        "  return Promise.resolve({ value });\n"
        "}\n"
    )
    target = repo / "src" / "app.ts"
    target.write_text(
        "import {\n  load,\n  type Result,\n} from './service';\n"
        "export const result: Promise<Result<'x'>> = load('x');\n"
    )
    (repo / "src" / "unused.ts").write_text(
        "\n".join(f"export const unused{index} = {index};" for index in range(50))
    )
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="8" * 64, targets=(target,)
    )

    entry = next(item for item in pack.manifest["entries"] if item["path"] == "src/service.ts")
    assert entry["role"] == "INTERFACE"
    assert "export interface Result<T extends string>" in pack.prompt
    assert "options?: { strict: boolean }" in pack.prompt
    assert "): Promise<Result<T>>;" in pack.prompt
    assert "return Promise.resolve" not in pack.prompt
    assert pack.manifest["policy"]["acceptedForUse"] is True


def test_python_configured_source_root_resolves(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "acme").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        "[tool.setuptools.package-dir]\n\"\" = \"src\"\n"
    )
    (repo / "src" / "acme" / "service.py").write_text(
        "def load(value: str) -> str:\n    return value\n"
    )
    target = repo / "app.py"
    target.write_text("from acme.service import load\nresult = load('x')\n")
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="4" * 64, targets=(target,)
    )

    assert "src/acme/service.py" in {item["path"] for item in pack.manifest["entries"]}


def test_unresolved_alias_is_fail_closed_and_private_detail_stays_out_of_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"@app/*": ["src/*"]}}})
    )
    target = repo / "app.ts"
    target.write_text("import { missing } from '@app/missing';\nexport const value = missing();\n")
    (repo / "unused.ts").write_text("export const unused = true;\n")
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="5" * 64, targets=(target,)
    )

    assert "unresolved_local_dependency" in pack.manifest["policy"]["rejectionReasons"]
    assert "@app/missing" not in json.dumps(pack.manifest)
    assert "app.ts:1 (@app/missing)" in pack.prompt
    assert pack.manifest["exclusionLedger"]["privateIssueCount"] == 1


def test_unsupported_class_interface_widens_to_full_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.ts").write_text(
        "export class Service { load(value: string): string { return value; } }\n"
    )
    target = repo / "app.ts"
    target.write_text("import { Service } from './service';\nexport const value = new Service();\n")
    snapshot = commit_fixture(repo)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="6" * 64, targets=(target,)
    )

    entry = next(item for item in pack.manifest["entries"] if item["path"] == "service.ts")
    assert entry["role"] == "FULL"
    assert entry["reason"] == "interface_widened_to_full"
    assert "interface_widened_to_full" in pack.manifest["warnings"]


def test_scan_budget_and_small_repository_declines_are_explicit(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("value = 1\n")
    snapshot = commit_fixture(repo)
    monkeypatch.setattr(native_provider, "MAX_SOURCE_FILES", 0)

    pack = NativeContextPackProvider().compile(
        repo, snapshot=snapshot, task_hash="7" * 64, targets=(target,)
    )

    assert set(pack.manifest["policy"]["rejectionReasons"]) >= {
        "repository_scan_budget_exceeded", "insufficient_compilation_benefit"
    }
    assert pack.manifest["policy"]["eligibilityPolicy"]["version"] == "native-context-eligibility-v2"


def test_legacy_native_manifest_remains_validator_compatible(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_static_typescript_fixture(repo)
    snapshot = commit_fixture(repo)
    pack = NativeContextPackProvider().compile(
        repo,
        snapshot=snapshot,
        task_hash="8" * 64,
        targets=(repo / "src" / "app.ts",),
    )
    legacy = {
        key: value
        for key, value in pack.manifest.items()
        if key not in {"impactHint", "promptHash"}
    }
    legacy["provider"] = {
        "name": "rhize-native",
        "revision": "rhize-native-context-pack-v1",
    }
    legacy["packId"] = native_provider.stable_pack_id(legacy)
    validate_native_context_pack_manifest(legacy)
