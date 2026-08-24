"""Fixture repo builders for `/rhize-devflow:review` contract tests.

Each builder constructs a hermetic `tmp_path` git repo representing one of the eight golden
review cases named in `.claude/plans/rhize-devflow-v3-engineering-control-plane.md`, Task
6's Verify list: cross-repo production release, protected workflow touch, migration change,
Sentry privacy change, trivial docs diff, unavailable reviewer, ambiguous target branch, and
accepted non-blocking product constraint. All content is sanitized/synthetic — no real
client names or paths.

`/rhize-devflow:review` itself is an agent workflow — pytest never runs it. These builders
exist so `tests/rhize-devflow/test_command_contracts.py` can run the deterministic half
(`devflow.py evidence`) against a representative repo and assert the evidence packet, jointly
with `review.md`'s command text, gives the agent what it needs to reach the right verdict
class and routing. Git-repo-building mirrors `check_scenarios.py`/`test_devflow_cli.py`'s
`make_git_repo`/`commit_all` conventions rather than committing static trees, because every
scenario here depends on real Git state (diffs, working-tree status, protected-path
matching, base-ref resolution).

devflow.py was not extended for this task — every fixture assertion in the paired test file
is satisfiable from evidence fields that already existed after Task 3
(`git.changed_files`, `git.base.resolved_via`, `protected_matches`, `findings`,
`instruction_files`).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed in {repo}: {result.stderr}"
    return result


def make_git_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.email", "fixture@example.com")
    run_git(repo, "config", "user.name", "Fixture")
    return repo


def commit_all(repo: Path, message: str = "init") -> None:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)


def build_cross_repo_production_release(tmp_path: Path) -> tuple[Path, Path]:
    """Two independently-versioned roots (frontend + backend), each with a genuine change
    and a production-deploy signal (`vercel.json` / `pyproject.toml`). Review must resolve
    and report each root's range/risk separately — never merge them into one verdict."""
    frontend = make_git_repo(tmp_path, "cross-repo-frontend")
    (frontend / "vercel.json").write_text(json.dumps({"framework": "nextjs"}) + "\n")
    (frontend / "app").mkdir()
    (frontend / "app" / "page.tsx").write_text("export default function Page() { return null; }\n")
    commit_all(frontend, "initial")
    (frontend / "app" / "page.tsx").write_text("export default function Page() { return <div/>; }\n")

    backend = make_git_repo(tmp_path, "cross-repo-backend")
    (backend / "pyproject.toml").write_text('[project]\nname = "backend"\n')
    (backend / "api").mkdir()
    (backend / "api" / "handler.py").write_text("def handle():\n    return 'ok'\n")
    commit_all(backend, "initial")
    (backend / "api" / "handler.py").write_text("def handle():\n    return {'status': 'ok'}\n")

    return frontend, backend


def build_protected_workflow_touch(tmp_path: Path) -> Path:
    """A change that touches `.github/workflows/*` — review must always require explicit
    human signoff for this, never an automatic PASS."""
    repo = make_git_repo(tmp_path, "protected-workflow")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: [push]\n")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("VERSION = 1\n")
    commit_all(repo, "initial")
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: [push, pull_request]\n")
    return repo


def build_migration_change(tmp_path: Path) -> Path:
    """A new file under `migrations/` — review's risk map must route a database/migration
    reviewer for this, not treat it as an ordinary source change."""
    repo = make_git_repo(tmp_path, "migration-change")
    (repo / "migrations").mkdir()
    (repo / "app.py").write_text("VERSION = 1\n")
    commit_all(repo, "initial")
    (repo / "migrations" / "0002_add_column.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN name text NOT NULL DEFAULT '';\n"
    )
    return repo


def build_sentry_privacy_change(tmp_path: Path) -> Path:
    """A changed Sentry instrumentation config that touches PII-scrubbing/redaction logic —
    review's risk map must route a security reviewer, not treat it as routine
    instrumentation."""
    repo = make_git_repo(tmp_path, "sentry-privacy-change")
    (repo / "sentry.server.config.ts").write_text(
        "export default { beforeSend: (event) => event };\n"
    )
    commit_all(repo, "initial")
    (repo / "sentry.server.config.ts").write_text(
        "export default { beforeSend: (event) => { delete event.user; return event; } };\n"
    )
    return repo


def build_trivial_docs_diff(tmp_path: Path) -> Path:
    """Only Markdown changed — no deployment/data/security/authorization/billing/migration/
    cache/external-write risk category applies, so review must not route a full specialist
    panel or block on a missing independent reviewer."""
    repo = make_git_repo(tmp_path, "trivial-docs-diff")
    (repo / "README.md").write_text("# Fixture\n\nOriginal.\n")
    commit_all(repo, "initial")
    (repo / "README.md").write_text("# Fixture\n\nUpdated wording only.\n")
    return repo


def build_unavailable_independent_reviewer(tmp_path: Path) -> Path:
    """A genuinely non-trivial code change (not docs-only), used to pair with a text-only
    assertion that review.md discloses a cold review and its limitation when no independent
    reviewer is available — there is no evidence-side signal for reviewer availability, so
    this fixture only needs to be non-trivial."""
    repo = make_git_repo(tmp_path, "unavailable-reviewer")
    (repo / "auth.py").write_text("def check(token):\n    return True\n")
    commit_all(repo, "initial")
    (repo / "auth.py").write_text("def check(token):\n    return token == 'secret'\n")
    return repo


def build_ambiguous_target_branch(tmp_path: Path) -> Path:
    """No explicit `--base` given, no upstream configured, no `origin/HEAD` — resolution
    falls through to a local-branch guess (`local-fallback`). Review must not treat this
    guess as settled the way it would treat an explicit or upstream signal; it must
    ask/report instead of assuming the guessed branch is the actual merge target."""
    repo = make_git_repo(tmp_path, "ambiguous-target-branch")
    (repo / "app.py").write_text("VERSION = 1\n")
    commit_all(repo, "initial")
    run_git(repo, "checkout", "-q", "-b", "feature/change")
    (repo / "app.py").write_text("VERSION = 2\n")
    commit_all(repo, "feature change")
    return repo


def build_accepted_product_constraint(tmp_path: Path) -> Path:
    """`CLAUDE.md` documents an already-accepted product decision (deferring a non-blocking
    validation to a follow-up release). Review must preserve that decision as a constraint —
    not relitigate scope or treat the already-accepted gap as a new blocking finding."""
    repo = make_git_repo(tmp_path, "accepted-product-constraint")
    (repo / "CLAUDE.md").write_text(
        "# Repo policy\n\n"
        "Product decision (accepted, tracked in RT-42): server-side validation for the "
        "legacy CSV importer is deferred to a follow-up release. This is NOT a review "
        "blocker — do not relitigate this scope decision.\n"
    )
    commit_all(repo, "initial")
    (repo / "importer.py").write_text("def import_csv(path):\n    return open(path).read()\n")
    return repo
