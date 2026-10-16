"""S4 check relaxation: deterministic eligibility, never-relaxable set, Laya can only remove relaxable items."""
import importlib.util
import json
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


def earn_advise(store):
    ta = cp._advice()
    (store / "registry-state.json").write_text(json.dumps({"decisions": {cp.DECISION: {
        "mode": "advise", "policySha256": ta.policy_sha256(cp.DECISION, cp.QUESTION, cp.POLICY),
        "instrumentSha256": ta.INSTRUMENT_SHA256}}}))


def fake(choice):
    def call(request, files, question, candidates, **_):
        return {"status": "ok", "choice": choice, "probabilities": {"full": 0.4, "relaxed": 0.6}, "latencyMs": 1.0}
    return call


def plan(repo, env, stage="check", choice="relaxed", earned=True, base="HEAD"):
    store, checks = env
    if earned:
        earn_advise(store)
    return cp.build_plan(repo, stage, checks, base=base, advise_options={"call": fake(choice), "store": store})


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


def test_default_base_is_head_parent_without_origin(repo, env):
    result = plan(repo, env, base=None)  # HEAD~ adds docs/b.md
    assert result["eligible"]
    assert result["base"] == git(repo, "rev-parse", "HEAD~").strip()


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
    assert cp.verify_plan(plan_file, "check")["valid"]
    git(repo, "add", "docs/a.md")  # staging does not change the diff
    assert cp.verify_plan(plan_file)["valid"]

    (repo / "docs/a.md").write_text("changed again")
    expired = cp.verify_plan(plan_file)
    assert not expired["valid"] and expired["plan"] == result["full"]
    (repo / "docs/a.md").write_text("changed")
    assert cp.verify_plan(plan_file)["valid"]

    (repo / "docs/new.md").write_text("n")
    assert not cp.verify_plan(plan_file)["valid"]
    (repo / "docs/new.md").unlink()
    git(repo, "mv", "docs/b.md", "docs/c.md")
    assert not cp.verify_plan(plan_file)["valid"]
    git(repo, "mv", "docs/c.md", "docs/b.md")
    assert cp.verify_plan(plan_file)["valid"]


def test_verify_expires_on_stage_change_and_checks_change(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    plan_file = write_plan(tmp_path, plan(repo, env))
    for stage in ("release", "production", "review"):
        assert not cp.verify_plan(plan_file, stage)["valid"], stage
    env[1].write_text(json.dumps(CHECKS[:-1]))
    assert not cp.verify_plan(plan_file)["valid"]


def test_verify_rejects_a_hand_edited_plan_and_git_failure(repo, env, tmp_path):
    (repo / "docs/a.md").write_text("changed")
    result = plan(repo, env)
    result["plan"] = [c for c in result["plan"] if c["id"] != "ci"]
    assert not cp.verify_plan(write_plan(tmp_path, result))["valid"]
    result = plan(repo, env)
    result["repo"] = str(tmp_path)
    assert not cp.verify_plan(write_plan(tmp_path, result))["valid"]
    assert not cp.verify_plan(tmp_path / "missing.json")["valid"]


def test_cli_plan_verify_outcome_exit_codes(repo, env, tmp_path, capsys):
    store, checks = env
    (repo / "docs/a.md").write_text("changed")
    out = tmp_path / "p.json"
    assert cp.main(["plan", "--repo", str(repo), "--base", "HEAD", "--stage", "check", "--checks", str(checks),
                    "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["eligible"] and cp.main(["verify", "--plan-file", str(out), "--stage", "check"]) == 0
    (repo / "docs/a.md").write_text("again")
    assert cp.main(["verify", "--plan-file", str(out)]) == 3
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
