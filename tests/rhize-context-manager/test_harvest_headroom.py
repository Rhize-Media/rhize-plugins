"""test_harvest_headroom.py — the deterministic headroom-capture collector.

Background: on 2026-08-26 the prose collector step in `commands/learn-harvest.md` produced
seven refinement-queue entries whose `pattern` was cut at exactly 550 characters mid-word.
`rhize-context-manager/scripts/harvest_headroom.py` replaces that step. These tests pin:

  1. every block is stored verbatim — no length cap, savings line folded in, indented body
     lines joined with single spaces, `####` blocks accepted, empty blocks dropped;
  2. ids are `sha1-12(source + pattern)` and re-ingesting the same capture appends nothing;
  3. `--dry-run` writes nothing; a normal run appends valid JSONL with the documented shape;
  4. `--audit` flags exactly the truncation shapes (550 chars; long + no terminal punctuation)
     and only among `pending` rows.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "rhize-context-manager" / "scripts" / "harvest_headroom.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "headroom-capture-sample.txt"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_blocks_are_stored_verbatim_with_no_length_cap(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    result = run(str(FIXTURE), "--queue", str(queue), "--repo", "rhize-plugins", "--json")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["blocks"] == 4  # empty-body heading dropped
    assert summary["appended"] == 4
    rows = load(queue)
    by_title = {r["pattern"].split(" — ")[0]: r for r in rows}

    long = by_title["Codex Harness"]  # title itself contains " — "; check the full pattern instead
    long = next(r for r in rows if r["pattern"].startswith("Codex Harness — exec output truncates"))
    assert len(long["pattern"]) > 550
    assert long["pattern"].startswith(
        "Codex Harness — exec output truncates at ~41KB (read narrow ranges) — *~219,199 tokens/session saved* In Codex sessions"
    )
    assert long["pattern"].endswith("padding padding padding.")
    assert long["est_savings"] == 219199

    zsh = next(r for r in rows if r["pattern"].startswith("Shell Gotchas (zsh)"))
    assert "ABORTS the whole command. Guard with a literal-safe path" in zsh["pattern"]
    assert zsh["est_savings"] == 600

    no_savings = next(r for r in rows if r["pattern"].startswith("A block with no savings line"))
    assert no_savings["pattern"] == "A block with no savings line — Body only, indented, two lines that must be joined with a single space."
    assert no_savings["est_savings"] is None

    assert not any(r["pattern"].startswith("Heading with an empty body") for r in rows)
    for r in rows:
        assert r["source"] == "headroom-learn"
        assert r["repo"] == "rhize-plugins"
        assert r["status"] == "pending"
        assert r["target_skill"] is None
        assert r["harvest_log"] == FIXTURE.name
        assert set(r) == {"id", "ts", "source", "repo", "pattern", "est_savings", "target_skill", "status", "harvest_log"}


def test_ids_are_sha1_12_of_source_plus_pattern_and_reingest_is_a_noop(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    assert run(str(FIXTURE), "--queue", str(queue)).returncode == 0
    rows = load(queue)
    for r in rows:
        assert r["id"] == hashlib.sha1(("headroom-learn" + r["pattern"]).encode()).hexdigest()[:12]
    second = run(str(FIXTURE), "--queue", str(queue), "--json")
    assert second.returncode == 0
    summary = json.loads(second.stdout)
    assert summary["appended"] == 0 and summary["duplicates_skipped"] == 4
    assert load(queue) == rows


def test_rows_restored_from_a_harvest_log_are_not_reingested(tmp_path: Path) -> None:
    """A restored row keeps its pre-restore id and may hold a differently bounded text; the
    block's title is what identifies it, so a re-run must skip it rather than append a twin."""
    queue = tmp_path / "queue.jsonl"
    restored = {
        "id": "1e6e1fedced6",  # sha1 of the old truncated text, deliberately not sha1 of the block
        "ts": "2026-08-26T18:16:56Z",
        "source": "headroom-learn",
        "repo": "rhize-plugins",
        "pattern": "Shell Gotchas (zsh) — *~600 tokens/session saved* A differently joined body.",
        "est_savings": 600,
        "target_skill": None,
        "status": "pending",
        "pattern_truncated_at_ingest": 550,
        "pattern_restored_from": "harvest-logs/2026-08-26-headroom.txt",
    }
    queue.write_text(json.dumps(restored) + "\n")
    result = run(str(FIXTURE), "--queue", str(queue), "--json")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["appended"] == 3 and summary["duplicates_skipped"] == 1
    assert not any(r["pattern"].startswith("Shell Gotchas (zsh)") for r in load(queue)[1:])


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    result = run(str(FIXTURE), "--queue", str(queue), "--dry-run", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["would_append"] == 4
    assert not queue.exists()


def test_unreadable_capture_exits_2(tmp_path: Path) -> None:
    result = run(str(tmp_path / "missing.txt"), "--queue", str(tmp_path / "q.jsonl"))
    assert result.returncode == 2
    assert "cannot read" in result.stderr


@pytest.mark.parametrize(
    "pattern,status,expected",
    [
        ("x" * 550, "pending", "exactly 550"),
        ("word " * 120, "pending", "terminal punctuation"),  # 600 chars, ends with a space
        ("word " * 120 + "done.", "pending", None),
        ("x" * 550, "consumed", None),  # only pending rows are audited
        ("short and fine.", "pending", None),
    ],
)
def test_audit_flags_only_truncation_shapes_among_pending(tmp_path: Path, pattern: str, status: str, expected: str | None) -> None:
    queue = tmp_path / "queue.jsonl"
    queue.write_text(json.dumps({"id": "abc123def456", "ts": "2026-08-26T18:16:56Z", "source": "headroom-learn", "repo": "r", "pattern": pattern, "est_savings": None, "target_skill": None, "status": status}) + "\n")
    result = run("--audit", "--queue", str(queue), "--json")
    assert result.returncode == 0, result.stderr
    suspect = json.loads(result.stdout)["suspect"]
    if expected is None:
        assert suspect == []
    else:
        assert len(suspect) == 1 and expected in suspect[0]["why"]
