"""test_viewer_launcher.py — rhize-visual-plan viewer/bin/launch.mjs.

The launcher copies the viewer's shipped files into a private, content-addressed
cache, runs `npm ci` there, and execs bin/rhize-plan.mjs from the copy, so the
skill directory (possibly a version-pinned plugin cache) never gets node_modules.

No network: each test copies the viewer into a temp "skill" directory and points
RHIZE_PLAN_NPM at a stub that fakes `npm ci` by writing minimal `vite` and
`gray-matter` packages. The stub vite's createServer() exits with STUB_EXIT or
raises STUB_SIGNAL, which is how exit-status/signal propagation is observed.
"""
from __future__ import annotations

import concurrent.futures
import os
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWER = REPO_ROOT / "project-launcher" / "skills" / "rhize-visual-plan" / "viewer"
SHIPPED = ["package.json", "package-lock.json", "index.html", "vite.config.ts", "bin/rhize-plan.mjs"]
NODE = shutil.which("node")

pytestmark = [
    pytest.mark.skipif(NODE is None, reason="node is required"),
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX stub npm"),
]

STUB_NPM = r"""#!/bin/sh
[ "$1" = "ci" ] || { echo "stub npm: expected ci, got $*" >&2; exit 64; }
[ -f package-lock.json ] || { echo "stub npm: no lockfile" >&2; exit 65; }
[ -n "$STUB_SLEEP" ] && sleep "$STUB_SLEEP"
[ -n "$STUB_FAIL" ] && exit 3
mkdir -p node_modules/vite node_modules/gray-matter
echo '{"name":"vite","type":"module","exports":"./index.js"}' > node_modules/vite/package.json
cat > node_modules/vite/index.js <<'JS'
export async function createServer() {
  if (process.env.STUB_SIGNAL) process.kill(process.pid, process.env.STUB_SIGNAL);
  process.exit(Number(process.env.STUB_EXIT || 0));
}
export const build = createServer;
export const preview = createServer;
JS
echo '{"name":"gray-matter","type":"module","exports":"./index.js"}' > node_modules/gray-matter/package.json
echo 'export default function matter() { return { data: {} }; }' > node_modules/gray-matter/index.js
exit 0
"""


@pytest.fixture()
def env(tmp_path: Path) -> dict:
    skill = tmp_path / "skill" / "viewer"
    for rel in SHIPPED + ["README.md", "bin/launch.mjs"]:
        (skill / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(VIEWER / rel, skill / rel)
    shutil.copytree(VIEWER / "src", skill / "src")
    npm = tmp_path / "npm-stub.sh"
    npm.write_text(STUB_NPM)
    npm.chmod(0o755)
    plan = tmp_path / "plan.mdx"
    plan.write_text("---\ntitle: T\n---\n# Plan\n")
    run_env = {k: v for k, v in os.environ.items() if not k.startswith("STUB_")}
    run_env.update(RHIZE_PLAN_VIEWER_HOME=str(tmp_path / "cache"), RHIZE_PLAN_NPM=str(npm))
    return {"skill": skill, "cache": tmp_path / "cache", "plan": plan, "env": run_env, "tmp": tmp_path}


def launch(ctx: dict, *args: str, **extra_env: str) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, str(ctx["skill"] / "bin" / "launch.mjs"), *args],
                          env={**ctx["env"], **extra_env}, capture_output=True, text=True, timeout=60)


def tree(path: Path) -> set[str]:
    return {str(p.relative_to(path)) for p in path.rglob("*")}


def test_print_root_is_deterministic_and_content_addressed(env):
    first = launch(env, "--print-root").stdout.strip()
    assert first == launch(env, "--print-root").stdout.strip()
    assert Path(first).parent == env["cache"]
    assert not env["cache"].exists(), "--print-root must not install anything"
    (env["skill"] / "src" / "styles.css").write_text("/* changed */\n")
    assert launch(env, "--print-root").stdout.strip() != first


def test_prepare_copies_only_shipped_files_and_leaves_the_skill_untouched(env):
    (env["skill"] / "node_modules" / "junk").mkdir(parents=True)
    (env["skill"] / "dist").mkdir()
    (env["skill"] / "secret-notes.txt").write_text("not shipped\n")
    before = tree(env["skill"])
    result = launch(env, "--prepare-only")
    assert result.returncode == 0, result.stderr
    dest = Path(result.stdout.strip())
    assert tree(env["skill"]) == before
    copied = {p for p in tree(dest) if not p.startswith("node_modules")}
    assert "README.md" not in copied and "secret-notes.txt" not in copied and "bin/launch.mjs" not in copied
    assert "dist" not in copied and "node_modules/junk" not in tree(dest)
    assert {"package-lock.json", "bin/rhize-plan.mjs", "src/components.tsx", ".ready"} <= copied
    assert stat.S_IMODE(env["cache"].stat().st_mode) == 0o700
    assert [p.name for p in env["cache"].iterdir()] == [dest.name], "no temp directories left behind"


def test_missing_lockfile_refuses_unpinned_install(env):
    (env["skill"] / "package-lock.json").unlink()
    result = launch(env, "--prepare-only")
    assert result.returncode == 1
    assert "package-lock.json is missing" in result.stderr
    assert not env["cache"].exists()


def test_npm_failure_publishes_nothing(env):
    result = launch(env, "--prepare-only", STUB_FAIL="1")
    assert result.returncode == 1
    assert "failed" in result.stderr
    assert list(env["cache"].iterdir()) == []


def test_concurrent_first_runs_publish_one_verified_copy(env):
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        results = list(pool.map(lambda _: launch(env, "--prepare-only", STUB_SLEEP="0.5"), range(3)))
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert len({r.stdout.strip() for r in results}) == 1
    assert len(list(env["cache"].iterdir())) == 1


def test_incomplete_or_tampered_cache_entry_is_rebuilt(env):
    dest = Path(launch(env, "--print-root").stdout.strip())
    dest.mkdir(parents=True)
    (dest / "package.json").write_text("{}")  # half-copied, no .ready
    assert launch(env, "--prepare-only").returncode == 0
    assert (dest / ".ready").is_file()
    (dest / "src" / "components.tsx").write_text("tampered")
    assert launch(env, "--prepare-only").returncode == 0
    assert (dest / "src" / "components.tsx").read_bytes() == (VIEWER / "src" / "components.tsx").read_bytes()


def test_symlinks_are_refused(env):
    (env["skill"] / "src" / "escape.ts").symlink_to("/etc/hosts")
    result = launch(env, "--prepare-only")
    assert result.returncode == 1 and "symlink" in result.stderr
    (env["skill"] / "src" / "escape.ts").unlink()
    real = env["tmp"] / "elsewhere"
    real.mkdir()
    env["cache"].symlink_to(real)
    result = launch(env, "--prepare-only")
    assert result.returncode == 1 and "not a real directory" in result.stderr


def test_viewer_exit_status_and_signal_propagate(env):
    assert launch(env, "--prepare-only").returncode == 0
    assert launch(env, "serve", str(env["plan"]), "--no-open", STUB_EXIT="7").returncode == 7
    assert launch(env, "serve", str(env["plan"]), "--no-open").returncode == 0
    killed = launch(env, "serve", str(env["plan"]), "--no-open", STUB_SIGNAL="SIGTERM")
    assert killed.returncode == -signal.SIGTERM
