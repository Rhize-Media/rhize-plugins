"""S4 check relaxation: deterministic eligibility, never-relaxable set, Laya can only remove relaxable items."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_plan_test", ROOT / "rhize-devflow/scripts/check_plan.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

CHECKS = [
    {"id": "unit", "kind": "test-full"}, {"id": "lint", "kind": "lint"}, {"id": "qa", "kind": "browser-qa"},
    {"id": "mut", "kind": "mutation"}, {"id": "tc", "kind": "typecheck"}, {"id": "bld", "kind": "build"},
    {"id": "sec", "kind": "security-review"}, {"id": "ci", "kind": "required-ci"}, {"id": "dep", "kind": "deploy"},
    {"id": "pub", "kind": "publish"}, {"id": "cred", "kind": "credentials"}, {"id": "appr", "kind": "approval"},
    {"id": "pmr", "kind": "production-merge-review"}, {"id": "odd", "kind": "something-new"},
]
NEVER_IDS = {"tc", "bld", "sec", "ci", "dep", "pub", "cred", "appr", "pmr", "odd"}


def git(repo, *args):
    return subprocess.run(["git", "-c", "core.excludesFile=/dev/null", "-c", "user.name=t", "-c", "user.email=t@t",
                           "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    for rel, text in {"README.md": "r", "docs/a.md": "a", "src/app.py": "x = 1\n", "tests/test_a.py": "def test(): pass\n",
                      "components/Button.tsx": "export const B = 1\n", "package.json": "{}", "yarn.lock": "l",
                      ".github/ci.yml": "on: push"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-qm", "one")
    (root / "docs/b.md").write_text("b")
    git(root, "add", ".")
    git(root, "commit", "-qm", "two")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")  # the trunk the base is measured from
    return root


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir(mode=0o700)
    monkeypatch.setenv("RHIZE_TYPED_DECISIONS_ROOT", str(store))
    monkeypatch.setattr(cp._advice(), "holdback", lambda decision, key: False)
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps(CHECKS))
    return store, checks


def earn_advise(store, mode="advise"):
    ta = cp._advice()
    (store / "laya-runtime.json").write_text(json.dumps({"revision": "r1"}))
    (store / "registry-state.json").write_text(json.dumps({
        "schemaVersion": 1, "revision": 1, "updatedAt": "2026-10-16T00:00:00Z", "decisions": {cp.DECISION: {
            "mode": mode, "pinned": False, "since": "2026-10-16T00:00:00Z", "reason": "earned",
            "policySha256": ta.policy_sha256(cp.DECISION, cp.QUESTION, cp.POLICY),
            "instrumentSha256": ta.INSTRUMENT_SHA256, "layaRevision": "r1", "cohortId": None}}}))


def fake(choice):
    def call(request, files, question, candidates, **_):
        return {"status": "ok", "choice": choice, "probabilities": {"full": 0.4, "relaxed": 0.6}, "latencyMs": 1.0}
    return call


def plan(repo, env, stage="check", choice="relaxed", earned=True, base="HEAD", **kwargs):
    store, checks = env
    if earned:
        earn_advise(store)
    return cp.build_plan(repo, stage, checks, base=base, advise_options={"call": fake(choice), "store": store},
                         **kwargs)


def verify(plan_file, repo, env, stage="check", **kwargs):
    return cp.verify_plan(plan_file, stage, repo, env[1], **kwargs)


def ids(result, key="plan"):
    return {c["id"] for c in result[key]}


def test_docs_only_is_eligible_and_relaxes_when_laya_advises(repo, env):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env)
    assert result["eligible"] and result["advice"]["recommendation"] == "relaxed"
    by_id = {c["id"]: c for c in result["plan"]}
    assert by_id["unit:affected"]["kind"] == "test-affected" and "unit" not in by_id
    assert by_id["lint:changed"]["kind"] == "lint-changed"
    assert "qa" not in by_id and "mut" not in by_id and ids(result, "skipped") == {"qa", "mut"}
    assert NEVER_IDS <= ids(result)


def test_shadow_and_missing_recommendation_run_full(repo, env):
    (repo / "docs/a.md").write_text("changed")
    shadow = plan(repo, env, earned=False)  # records Laya's answer but shows nothing
    assert shadow["advice"]["mode"] == "shadow" and shadow["advice"]["recommendation"] is None
    (repo / "docs/a.md").write_text("different change, new decision key")
    for result in (shadow, plan(repo, env, choice="full")):
        assert result["eligible"] and result["plan"] == result["full"]
    broken = cp.build_plan(repo, "check", env[1], base="HEAD",
                           advise_options={"call": lambda *a, **k: {"status": "unavailable"}, "store": env[0]})
    assert broken["plan"] == broken["full"]


@pytest.mark.parametrize("setup", ["workflow", "lockfile_deleted", "env_untracked", "rename_into_github",
                                   "package_json", "migration", "terraform", "auth", "claude_dir", "unknown_ext",
                                   "mode_change", "symlink"])
def test_protected_or_unknown_paths_are_ineligible_in_any_form(repo, env, setup):
    (repo / "docs/a.md").write_text("changed")
    if setup == "workflow":
        (repo / ".github/ci.yml").write_text("on: pull_request")
    elif setup == "lockfile_deleted":
        (repo / "yarn.lock").unlink()
    elif setup == "env_untracked":
        (repo / "docs/.env.local").write_text("TOKEN=1")
    elif setup == "rename_into_github":
        git(repo, "mv", "docs/a.md", ".github/a.yml")
    elif setup == "package_json":
        (repo / "package.json").write_text('{"scripts":{"x":"y"}}')
    elif setup == "migration":
        (repo / "db/migrations").mkdir(parents=True)
        (repo / "db/migrations/001.py").write_text("x")
    elif setup == "terraform":
        (repo / "main.tf").write_text("x")
    elif setup == "auth":
        (repo / "src/authService.py").write_text("x")
    elif setup == "claude_dir":
        (repo / ".claude").mkdir()
        (repo / ".claude/settings.json").write_text("{}")
    elif setup == "unknown_ext":
        (repo / "docs/blob.bin").write_bytes(b"\0")
    elif setup == "mode_change":
        (repo / "src/app.py").chmod(0o755)
    elif setup == "symlink":
        (repo / "docs/link.md").symlink_to("a.md")
    result = plan(repo, env)
    assert not result["eligible"] and result["plan"] == result["full"] and result["relaxable"] == []
    assert NEVER_IDS <= ids(result)


def test_renamed_from_docs_into_protected_reports_both_paths(repo, env):
    git(repo, "mv", "docs/a.md", ".github/a.yml")
    state = cp.analyse(repo, "HEAD", "check", CHECKS, "x")
    assert {"docs/a.md", ".github/a.yml"} <= set(state["paths"]) and not state["eligible"]


def test_mixed_diff_blocks_only_what_it_touches(repo, env):
    (repo / "docs/a.md").write_text("changed")
    (repo / "src/app.py").write_text("x = 2\n")
    result = plan(repo, env)
    assert result["eligible"] and "lint:changed" in ids(result)
    assert "unit" in ids(result) and "mut" in ids(result) and "qa" not in ids(result)
    (repo / "components/Button.tsx").write_text("export const B = 2\n")
    result = plan(repo, env)
    assert "qa" in ids(result) and "mut" in ids(result)


def test_config_and_release_stage_are_ineligible(repo, env):
    (repo / "docs/a.md").write_text("changed")
    for stage in ("release", "production", "review", "deploy", "mystery", ""):
        result = plan(repo, env, stage=stage)
        assert not result["eligible"] and result["plan"] == result["full"], stage
    (repo / "tsconfig.json").write_text("{}")
    assert not plan(repo, env)["eligible"]


def test_no_changes_and_git_failure_give_full_plan(repo, env, tmp_path):
    assert not plan(repo, env)["eligible"]
    for bad in (cp.build_plan(tmp_path, "check", env[1], base="HEAD"), plan(repo, env, base="no-such-ref"),
                plan(repo, env, base="--output=x")):
        assert not bad["eligible"] and bad["plan"] == bad["full"] and bad["diffSha256"] is None


def commit(repo, rel, text, message):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
    git(repo, "add", rel)
    git(repo, "commit", "-qm", message)


def test_default_base_is_merge_base_with_trunk(repo, env):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env, base=None)
    assert result["eligible"] and result["base"] == git(repo, "rev-parse", "origin/main").strip()
    commit(repo, "docs/c.md", "c", "three")  # unpushed commit: the merge-base stays at the trunk
    assert plan(repo, env, base=None)["base"] == git(repo, "rev-parse", "origin/main").strip()


def test_missing_trunk_is_full_and_there_is_no_head_parent_fallback(repo, env):
    commit(repo, "package.json", '{"scripts":{"x":"y"}}', "protected, two commits back")
    commit(repo, "docs/c.md", "c", "docs")
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    (repo / "docs/a.md").write_text("changed")
    for kwargs in ({}, {"trunk": "no-such-trunk"}, {"trunk": "--output=x"}):
        result = plan(repo, env, base=None, **kwargs)
        assert not result["eligible"] and result["plan"] == result["full"] and result["diffSha256"] is None, kwargs
        assert any("trunk" in r for r in result["reasons"]), kwargs
    assert not plan(repo, env, base="HEAD")["eligible"]  # an explicit base cannot replace the trunk


def test_protected_change_committed_before_head_parent_is_seen(repo, env):
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    commit(repo, "package.json", '{"scripts":{"x":"y"}}', "protected")
    commit(repo, "docs/c.md", "c", "docs")
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env, base=None)  # trunk is still the old HEAD, so both commits are in the window
    assert result["base"] == git(repo, "rev-parse", "HEAD~2").strip()
    assert not result["eligible"] and result["plan"] == result["full"]
    assert any("package.json" in r for r in result["reasons"])
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")  # pushed: only the docs edit remains
    assert plan(repo, env, base=None)["eligible"]


def test_base_must_be_an_ancestor_of_the_merge_base(repo, env):
    (repo / "docs/a.md").write_text("changed")
    wider = plan(repo, env, base="HEAD~")  # an older base only widens the window
    assert wider["eligible"] and wider["base"] == git(repo, "rev-parse", "HEAD~").strip()
    side = git(repo, "commit-tree", "HEAD^{tree}", "-p", "HEAD~", "-m", "side").strip()  # not an ancestor of HEAD
    for base in (side, "HEAD~~~", "-p"):
        result = plan(repo, env, base=base)
        assert not result["eligible"] and result["plan"] == result["full"] and result["diffSha256"] is None, base
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD~")  # trunk behind HEAD: HEAD is no longer an ancestor
    assert not plan(repo, env, base="HEAD")["eligible"]


def test_repo_must_be_the_toplevel(repo, env):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo / "docs", env)
    assert not result["eligible"] and result["diffSha256"] is None and result["plan"] == result["full"]


def test_git_environment_is_ignored(repo, env, tmp_path, monkeypatch):
    (repo / "package.json").write_text('{"scripts":{"x":"y"}}')
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "bogus-index"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/bin/false")
    result = plan(repo, env)
    assert not result["eligible"] and any("package.json" in r for r in result["reasons"])
    assert "GIT_DIR" not in cp._env() and cp._env()["GIT_CONFIG_NOSYSTEM"] == "1"
    assert cp._env()["GIT_OPTIONAL_LOCKS"] == "0"


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_hidden_index_flags_refuse_the_plan(repo, env, flag):
    (repo / "docs/a.md").write_text("changed")
    assert plan(repo, env)["eligible"]
    git(repo, "update-index", flag, "package.json")
    (repo / "package.json").write_text('{"scripts":{"x":"y"}}')
    assert git(repo, "diff", "--name-only", "HEAD").strip() == "docs/a.md"  # the edit really is invisible to diff
    result = plan(repo, env)
    assert not result["eligible"] and result["plan"] == result["full"]
    assert any("assume-unchanged or skip-worktree" in r and "package.json" in r for r in result["reasons"])


def test_staged_protected_change_with_restored_worktree_is_seen_and_bound(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    relaxed = plan(repo, env)
    plan_file = write_plan(tmp_path, relaxed)
    assert relaxed["eligible"] and verify(plan_file, repo, env)["valid"]
    original = (repo / "package.json").read_text()
    (repo / "package.json").write_text('{"scripts":{"x":"y"}}')
    git(repo, "add", "package.json")
    (repo / "package.json").write_text(original)  # worktree matches the base again
    assert git(repo, "diff", "--name-only", "HEAD").strip() == "docs/a.md"
    assert git(repo, "diff", "--cached", "--name-only", "HEAD").strip() == "package.json"
    result = plan(repo, env)
    assert not result["eligible"] and result["plan"] == result["full"]
    assert any("package.json" in r for r in result["reasons"])
    expired = verify(plan_file, repo, env)
    assert not expired["valid"] and expired["plan"] == relaxed["full"]


def test_index_state_is_bound_not_only_worktree_bytes(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    plan_file = write_plan(tmp_path, plan(repo, env))
    assert verify(plan_file, repo, env)["valid"]
    git(repo, "add", "docs/a.md")  # same bytes, different index
    assert not verify(plan_file, repo, env)["valid"]


def test_test_only_diff_keeps_mutation(repo, env):
    (repo / "tests/test_a.py").write_text("def test(): assert True\n")
    result = plan(repo, env)
    assert result["eligible"] and "mut" in ids(result) and "lint:changed" in ids(result)
    assert "unit" in ids(result) and "qa" not in ids(result) and ids(result, "skipped") == {"qa"}
    (repo / "tests/e2e").mkdir()
    (repo / "tests/e2e/home.ts").write_text("export {}\n")
    assert "qa" in ids(plan(repo, env))  # an e2e test also keeps browser QA


def test_never_relaxable_kinds_always_listed_even_when_laya_says_relaxed(repo, env):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env)
    assert result["plan"] != result["full"] and NEVER_IDS <= ids(result)
    assert not (NEVER_IDS & ids(result, "relaxable"))
    assert all(c["kind"] in cp.RELAXABLE_KINDS for c in result["relaxable"])


def test_corrupted_relaxed_plan_fails_closed_to_full(repo, env, monkeypatch):
    (repo / "docs/a.md").write_text("changed")
    real = cp.analyse

    def tampered(*args):
        state = real(*args)
        state["relaxedPlan"] = [c for c in state["relaxedPlan"] if c["id"] != "sec"]
        return state
    monkeypatch.setattr(cp, "analyse", tampered)
    result = plan(repo, env)
    assert result["plan"] == result["full"] and "sec" in ids(result)
    assert any("violates" in r for r in result["reasons"])


def write_plan(tmp_path, result):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(result))
    return path


def test_verify_accepts_unchanged_state_and_expires_on_any_change(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env)
    plan_file = write_plan(tmp_path, result)
    assert verify(plan_file, repo, env)["valid"]
    (repo / "docs/a.md").write_text("changed again")
    expired = verify(plan_file, repo, env)
    assert not expired["valid"] and expired["plan"] == result["full"]
    (repo / "docs/a.md").write_text("changed")
    assert verify(plan_file, repo, env)["valid"]

    (repo / "docs/new.md").write_text("n")
    assert not verify(plan_file, repo, env)["valid"]
    (repo / "docs/new.md").unlink()
    git(repo, "mv", "docs/b.md", "docs/c.md")
    assert not verify(plan_file, repo, env)["valid"]
    git(repo, "mv", "docs/c.md", "docs/b.md")
    assert verify(plan_file, repo, env)["valid"]


def test_verify_expires_on_stage_change_and_checks_change(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    plan_file = write_plan(tmp_path, plan(repo, env))
    for stage in ("release", "production", "review"):
        assert not verify(plan_file, repo, env, stage)["valid"], stage
    env[1].write_text(json.dumps(CHECKS[:-1]))
    assert not verify(plan_file, repo, env)["valid"]


def test_verify_rejects_a_hand_edited_plan_and_git_failure(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env)
    result["plan"] = [c for c in result["plan"] if c["id"] != "ci"]
    assert not verify(write_plan(tmp_path, result), repo, env)["valid"]
    result = plan(repo, env)
    result["repo"] = str(tmp_path)
    assert not verify(write_plan(tmp_path, result), repo, env)["valid"]
    assert not verify(tmp_path / "missing.json", repo, env)["valid"]
    result = plan(repo, env)
    plan_file = write_plan(tmp_path, result)
    other_checks = tmp_path / "other-checks.json"
    other_checks.write_text(env[1].read_text())  # identical bytes, different file than the plan names
    assert not cp.verify_plan(plan_file, "check", repo, other_checks)["valid"]
    assert not cp.verify_plan(plan_file, "check", repo / "docs", env[1])["valid"]
    for key, value in (("base", "-p"), ("base", ["x"]), ("plan", {"x": 1}), ("stage", 7)):
        tampered = dict(result, **{key: value})
        assert not verify(write_plan(tmp_path, tampered), repo, env)["valid"], key


def test_cli_plan_verify_outcome_exit_codes(repo, env, tmp_path, capsys):
    store, checks = env
    (repo / "docs/a.md").write_text("changed")
    out = tmp_path / "p.json"
    assert cp.main(["plan", "--repo", str(repo), "--base", "HEAD", "--stage", "check", "--checks", str(checks),
                    "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["eligible"] and oct(out.stat().st_mode & 0o777) == "0o600"
    flags = ["verify", "--plan-file", str(out), "--repo", str(repo), "--checks", str(checks)]
    assert cp.main([*flags, "--stage", "check"]) == 0
    (repo / "docs/a.md").write_text("again")
    assert cp.main([*flags, "--stage", "check"]) == 3
    for missing in (["--repo"], ["--checks"], ["--stage", "check", "--repo"]):  # required flags: usage error
        argv = ["verify", "--plan-file", str(out), "--stage", "check"] + (
            ["--repo", str(repo)] if "--repo" not in missing else []) + (
            ["--checks", str(checks)] if "--checks" not in missing else [])
        with pytest.raises(SystemExit) as usage:
            cp.main(argv)
        assert usage.value.code == 2
    with pytest.raises(SystemExit) as usage:
        cp.main(flags)  # no --stage
    assert usage.value.code == 2
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    assert cp.main(["plan", "--repo", str(repo), "--stage", "check", "--checks", str(bad)]) == 2
    decision_id = data["advice"]["decisionId"]
    assert cp.main(["outcome", "--decision-id", decision_id, "--chosen", "full"]) == 0
    assert cp.main(["outcome", "--decision-id", decision_id, "--chosen", "relaxed"]) == 1
    assert cp.main(["outcome", "--decision-id", "0" * 32, "--chosen", "full"]) == 1


@pytest.mark.parametrize("path,expected", [
    ("docs/guide.md", {"docs"}), ("README.md", {"docs"}), ("pkg/CHANGELOG.md", {"docs"}),
    ("skills/x/SKILL.md", {"logic"}), ("commands/check.md", {"logic"}), ("CLAUDE.md", {"logic"}),
    ("src/a.py", {"logic"}), ("web/Card.tsx", {"ui", "logic"}), ("web/site.css", {"ui"}),
    ("tests/test_a.py", {"test"}), ("web/a.test.ts", {"test"}), ("tests/e2e/home.ts", {"test", "ui"}),
    ("tsconfig.json", {"config"}), ("src/a.weird", {"unknown"}), ("notes/todo.md", {"unknown"}),
    ("package.json", {"protected"}), ("poetry.lock", {"protected"}), ("db/schema.sql", {"protected"}),
    ("infra/x.py", {"protected"}), (".env.production", {"protected"}), ("src/middleware.ts", {"protected"}),
    ("ci/build.yml", {"protected"}), ("Dockerfile", {"protected"}), ("hooks/hooks.json", {"protected"}),
    ("docs/AUTHORS.md", {"docs"}), ("src/block.py", {"logic"}),
])
def test_classification(path, expected):
    assert cp.classify(path) == expected


@pytest.mark.parametrize("path", [
    "ci/check.py", "pipelines/build.sh", "release/publish.js", "next.config.js", ".eslintrc.js", "jest.config.js",
    "eslint.config.mjs", "conftest.py", "tests/conftest.py", "alembic/versions/1.py", "scripts/deploy.sh",
    "scripts/tools/lint.bash", "src/signIn.ts", "src/logOut.ts", "src/JWTVerifier.ts", "src/authutils.ts",
    "lib/passwords.ts", "Package.swift", "build.rs", "tools/publish.js", "bin/release.py", ".prettierrc.json",
    ".babelrc.cjs", "src/SSOHandler.py", "src/csrfGuard.ts", "app/api/oauth/callback.ts", "lib/crypto.ts",
    "src/userSession.ts", "src/apiKeys.ts", "src/PrivateKeyLoader.ts", "cd/promote.py", "workflows/x.sh",
])
def test_reviewer_probe_paths_are_protected(path):
    assert cp.classify(path) == {"protected"}


@pytest.mark.parametrize("path", ["src/author.py", "docs/AUTHORS.md", "lib/helpers.ts", "src/block.py",
                                  "scripts/data.py", "src/util/strings.py"])
def test_ordinary_paths_stay_unprotected(path):
    assert "protected" not in cp.classify(path)


@pytest.mark.parametrize("path", ["ci/check.py", "next.config.js", "scripts/deploy.sh", "src/signIn.ts"])
def test_protected_probe_path_blocks_an_otherwise_eligible_diff(repo, env, path):
    (repo / "docs/a.md").write_text("changed")
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text("x")
    result = plan(repo, env)
    assert not result["eligible"] and result["plan"] == result["full"] and any(path in r for r in result["reasons"])


def test_policy_binds_candidate_text_and_classifier_tables():
    ta = cp._advice()
    assert cp.POLICY["candidates"] == cp.CANDIDATES and cp.POLICY["classifierSha256"] == cp.sha256(cp._tables())
    base = ta.policy_sha256(cp.DECISION, cp.QUESTION, cp.POLICY)
    reworded = dict(cp.POLICY, candidates=[dict(cp.CANDIDATES[0], criterion="Run everything"), cp.CANDIDATES[1]])
    assert ta.policy_sha256(cp.DECISION, cp.QUESTION, reworded) != base
    other_tables = dict(cp.POLICY, classifierSha256=cp.sha256(dict(cp._tables(), ciDirs=["ci"])))
    assert ta.policy_sha256(cp.DECISION, cp.QUESTION, other_tables) != base


def test_plan_out_is_created_exclusively_with_mode_0600(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    args = ["plan", "--repo", str(repo), "--base", "HEAD", "--stage", "check", "--checks", str(env[1])]
    fresh = tmp_path / "plan.json"
    assert cp.main([*args, "--out", str(fresh)]) == 0 and (fresh.stat().st_mode & 0o777) == 0o600
    before = fresh.read_text()
    assert cp.main([*args, "--out", str(fresh)]) == 2 and fresh.read_text() == before  # never overwrites
    target = tmp_path / "target.json"
    target.write_text("keep")
    link = tmp_path / "link.json"
    os.symlink(target, link)
    assert cp.main([*args, "--out", str(link)]) == 2 and target.read_text() == "keep"
    dangling = tmp_path / "dangling.json"
    os.symlink(tmp_path / "nowhere.json", dangling)
    assert cp.main([*args, "--out", str(dangling)]) == 2 and not (tmp_path / "nowhere.json").exists()


def relaxed_plan_file(repo, env, tmp_path, **kwargs):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env, **kwargs)
    return result, write_plan(tmp_path, result)


def test_relaxed_plan_is_valid_only_while_the_advice_record_authorizes_it(repo, env, tmp_path):
    result, plan_file = relaxed_plan_file(repo, env, tmp_path)
    assert result["plan"] != result["full"] and result["advice"]["policySha256"]
    ok = verify(plan_file, repo, env)
    assert ok["valid"] and ok["plan"] == result["plan"]


def test_demoted_registry_makes_a_relaxed_plan_expire_to_full(repo, env, tmp_path):
    result, plan_file = relaxed_plan_file(repo, env, tmp_path)
    for mode in ("shadow", "off"):
        earn_advise(env[0], mode)
        expired = verify(plan_file, repo, env)
        assert not expired["valid"] and expired["plan"] == result["full"], mode
    earn_advise(env[0])
    assert verify(plan_file, repo, env)["valid"]
    (env[0] / "registry-state.json").unlink()
    assert not verify(plan_file, repo, env)["valid"]
    earn_advise(env[0])
    (env[0] / "laya-runtime.json").write_text(json.dumps({"revision": "r2"}))  # Laya changed under the plan
    assert not verify(plan_file, repo, env)["valid"]


def test_hand_edited_relaxed_plan_without_a_treatment_relaxed_record_is_full(repo, env, tmp_path, monkeypatch):
    # Laya said full: the plan is the full list. Hand-editing it into the relaxed list must not validate.
    (repo / "docs/a.md").write_text("changed")
    said_full = plan(repo, env, choice="full")
    assert said_full["plan"] == said_full["full"]
    relaxed = cp.analyse(repo, "HEAD", "check", cp.load_checks(env[1])[0], cp.load_checks(env[1])[1])["relaxedPlan"]
    forged = dict(said_full, plan=relaxed)
    result = verify(write_plan(tmp_path, forged), repo, env)
    assert not result["valid"] and result["plan"] == said_full["full"]

    # No advice block, a foreign decision id, or a different policy hash.
    (repo / "docs/a.md").write_text("changed again")
    good = plan(repo, env)
    assert good["plan"] != good["full"]
    for mutate in (lambda a: a.clear(), lambda a: a.update(decisionId="0" * 32),
                   lambda a: a.update(policySha256="1" * 64), lambda a: a.pop("policySha256"),
                   lambda a: a.update(decisionId=None)):
        advice = dict(good["advice"])
        mutate(advice)
        assert not verify(write_plan(tmp_path, dict(good, advice=advice)), repo, env)["valid"]
    assert not verify(write_plan(tmp_path, {k: v for k, v in good.items() if k != "advice"}), repo, env)["valid"]
    assert verify(write_plan(tmp_path, good), repo, env)["valid"]

    # A record stored for another diff does not authorize this one (decision id derives from the diff hash).
    (repo / "docs/a.md").write_text("a third version")
    third = plan(repo, env)
    mixed = dict(third, advice=good["advice"])
    assert not verify(write_plan(tmp_path, mixed), repo, env)["valid"]


def test_holdback_arm_and_non_ok_record_never_authorize_relaxation(repo, env, tmp_path, monkeypatch):
    ta = cp._advice()
    result, plan_file = relaxed_plan_file(repo, env, tmp_path)
    path = env[0] / cp.DECISION / "choice" / f"{result['advice']['decisionId']}.json"
    record = json.loads(path.read_text())
    for edit in ({"arm": "holdback"}, {"laya": dict(record["laya"], choice="full")},
                 {"laya": dict(record["laya"], status="timeout")}, {"policySha256": "2" * 64},
                 {"instrumentSha256": "3" * 64}, {"decisionId": "4" * 32}):
        path.write_text(json.dumps(dict(record, **edit)))
        assert not verify(plan_file, repo, env)["valid"], edit
        assert verify(plan_file, repo, env)["plan"] == result["full"]
    path.write_text(json.dumps(record))
    assert verify(plan_file, repo, env)["valid"]
    path.write_text("not json")
    assert not verify(plan_file, repo, env)["valid"]
    path.unlink()
    assert not verify(plan_file, repo, env)["valid"]
    assert ta.load(cp.DECISION, "../../etc/passwd") is None


def test_verify_uses_the_callers_trunk_not_the_plan_files(repo, env, tmp_path):
    result, plan_file = relaxed_plan_file(repo, env, tmp_path)
    assert verify(plan_file, repo, env, trunk="origin/main")["valid"]
    assert not verify(plan_file, repo, env, trunk="origin/missing")["valid"]  # missing trunk: full
