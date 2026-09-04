"""test_harvest_noise_filter.py — the content-dedupe gate in front of the refinement queue.

Background: `scripts/harvest_noise_filter.py` is the one step of the `daily-learn-harvest`
pipeline that makes accept/reject decisions. It sorts each candidate signal into
`suppressed` (a restatement of something already known — dropped), `flagged` (kept, but
tagged for the human at triage because it partly overlaps known facts), `thin` (too few
content tokens to act on — dropped) or kept clean. Until 2026-09-04 it had no automated
tests, and a read-only `--self-audit` that day measured that at the current calibration
roughly 46% of entries a human later rejected pass as clean. These tests pin the behavior
AND the calibration, so a change to either shows up as a failing test instead of a silent
shift in what reaches the triage queue:

  1. the tokenizer contract (`normalize`, `chunk_markdown`, the 4-token reference floor) —
     every threshold below was calibrated against this tokenizer, so changing it is a
     threshold change in disguise and must be a visible one;
  2. the four buckets on realistic candidates: a restatement is suppressed, a novel signal
     is kept clean, a composite of known facts plus a new one is flagged (kept + tagged),
     and a thin candidate is dropped whether or not it overlaps a reference;
  3. references come from queue rows of ANY status and from `--reference` docs; a row is
     never matched against itself; a missing doc warns and is skipped, the rest still count;
  4. coverage is a greedy union of up to `--max-blocks` (default 3) reference blocks,
     chosen by marginal gain rather than document order;
  5. the calibration baseline: suppress at >= 0.75, flag at >= 0.45 (both inclusive), thin
     below 6 content tokens, and the CLI flags really reach the classifier;
  6. `--keep-out` holds exactly the survivors, the text report names every suppression with
     the reference it matched ("never silent"), and the CLI contract holds (exit 0 for an
     all-suppressed batch, exit 2 without `--candidates`/`--self-audit`).

Every CLI run goes through `run_filter`, which always passes an explicit `--queue`: the
script's default is the LIVE queue at `~/.claude/context-manager/refinement-queue.jsonl`,
and a test that omitted the flag would read real, changing data.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "harvest_noise_filter.py"

SPEC = importlib.util.spec_from_file_location("harvest_noise_filter", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
noise_filter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(noise_filter)


# --- fixtures: a CLAUDE.md-style reference doc and the candidates scored against it ---------

# Five blocks once chunked: block0 is the heading (3 content tokens, below the 4-token
# reference floor, so it never becomes a reference); block1..block4 are the bullets. The two
# bullets with an indented continuation line are single blocks.
RULES_DOC = """# Environment and workflow rules

- Always invoke `python3`, never bare `python` (not on PATH, exits 127).
- `timeout` is unavailable on this macOS — use a background `sleep`+`kill` pair instead.
- vitest output is captured by the rtk tee — read the newest file under
  `~/Library/Application Support/rtk/tee/`; never pass `--reporter=basic`.
- Never `Read` a large `.jsonl` directly — it exceeds the 256KB/25,000-token tool limit;
  process it with `python3`/`jq` in Bash instead.
"""

# A headroom-style rephrasing of the python3 rule: 9 of its 10 content tokens are in block1.
RESTATED_PYTHON3 = (
    "Python — always invoke python3, never bare python: it is not on PATH and exits 127 on this machine."
)
# The same fact as the queue would already hold it, worded a third way.
QUEUED_PYTHON3 = "Always invoke python3, never bare python — it is not on PATH and exits 127."
# Nothing in RULES_DOC talks about Sanity, caching or query loops.
NOVEL_SANITY = (
    "Sanity MCP query loop — cache the first query_documents result in a scratchpad file; "
    "re-querying the same dataset eight times in one session wasted 3.2k tokens."
)
# Two documented facts (block1 + block2) bundled with one genuinely new one about pytest.ini:
# 14 of 21 content tokens are covered, which is the 0.45..0.75 band the filter refuses to
# auto-suppress.
COMPOSITE_SHELL = (
    "Shell gotchas — invoke python3, never bare python (exits 127); timeout is unavailable on this "
    "macOS, use a background sleep+kill pair. Also: pytest.ini pins testpaths to tests and evals."
)

# Five bullets that share no content token with each other; each holds exactly three of the
# fifteen content tokens in FIVE_FACTS. Coverage therefore climbs in steps of 0.2 per block
# unioned, which makes the greedy set-cover and the --max-blocks cap directly observable.
FACTS_DOC = """- Always invoke `python3` explicitly, never bare `python`.
- `timeout` is unavailable on this macOS build; use sleep and kill.
- vitest output is captured by the rtk tee; read the newest tee file.
- The scratchpad path resolves per session; resolve it once and reuse.
- Reach for codegraph before rg or broad manual reads.
"""
FIVE_FACTS = (
    "invoke python3 explicitly; the timeout is unavailable on macOS; the vitest output is in the tee; "
    "the scratchpad path is per session; codegraph before rg reads."
)


def make_row(pattern: str, *, status: str = "pending", source: str = "headroom-learn") -> dict:
    """A queue/candidate row shaped like harvest_headroom.py writes them (id = sha1-12(source + pattern))."""
    return {
        "id": hashlib.sha1((source + pattern).encode()).hexdigest()[:12],
        "ts": "2026-09-04T09:00:00Z",
        "source": source,
        "repo": "rhize-plugins",
        "pattern": pattern,
        "est_savings": None,
        "target_skill": None,
        "status": status,
        "harvest_log": "2026-09-04-headroom.txt",
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def run_filter(
    tmp_path: Path,
    candidates: list[dict],
    *,
    docs: dict[str, str] | None = None,
    queue_rows: list[dict] | None = None,
    extra: tuple[str, ...] = (),
    as_json: bool = True,
) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    """Run the CLI on `candidates` with the given reference docs and queue rows.

    `--queue` is always passed (an empty file when no rows are given) so a test can never fall
    back on the script's default, which is the live refinement queue.
    """
    cand_path = tmp_path / "candidates.jsonl"
    write_jsonl(cand_path, candidates)
    queue_path = tmp_path / "queue.jsonl"
    write_jsonl(queue_path, queue_rows or [])
    args = ["--candidates", str(cand_path), "--queue", str(queue_path)]
    for name, text in (docs or {}).items():
        doc_path = tmp_path / name
        doc_path.write_text(text, encoding="utf-8")
        args += ["--reference", str(doc_path)]
    args += list(extra)
    if as_json:
        args.append("--json")
    result = run(*args)
    assert result.returncode == 0, result.stderr
    return result, (json.loads(result.stdout) if as_json else None)


def bucket(report: dict, cand_id: str) -> str:
    """Which outcome a candidate landed in. Flagged entries are also listed under `kept`."""
    hits = {name for name in ("suppressed", "thin", "flagged", "kept") if any(r["id"] == cand_id for r in report[name])}
    if hits == {"suppressed"}:
        return "suppressed"
    if hits == {"thin"}:
        return "thin"
    if hits == {"flagged", "kept"}:
        return "flagged"
    if hits == {"kept"}:
        return "clean"
    raise AssertionError(f"{cand_id} landed in an impossible combination of buckets: {sorted(hits)}")


def record(report: dict, cand_id: str) -> dict:
    for name in ("suppressed", "thin", "flagged", "kept"):
        for rec in report[name]:
            if rec["id"] == cand_id:
                return rec
    raise AssertionError(f"{cand_id} is in no bucket of the report")


# --- 1. tokenizer contract ------------------------------------------------------------------


def test_normalize_strips_markdown_stopwords_and_short_tokens() -> None:
    """The thresholds were calibrated against exactly this tokenizer; a change here recalibrates them."""
    assert noise_filter.normalize(
        "- `timeout` is unavailable on this macOS — use a background `sleep`+`kill` pair instead."
    ) == ["timeout", "unavailable", "macos", "background", "sleep", "kill", "pair", "instead"]
    # Leading/trailing ./- are stripped from a token, and 1-char tokens are dropped.
    assert noise_filter.normalize("Use `--threshold 0.5`; a b I") == ["threshold", "0.5"]
    # Slash-joined path segments stay one token, so a path only matches as a unit.
    assert noise_filter.normalize("read `~/Library/Application Support/rtk/tee/`") == [
        "read", "library/application", "support/rtk/tee",
    ]
    # Underscores are stripped as markdown before tokenizing, so identifiers split into words.
    assert noise_filter.normalize("est_savings claims") == ["est", "savings", "claims"]


def test_chunk_markdown_splits_on_bullets_and_blank_lines_and_joins_continuations() -> None:
    blocks = noise_filter.chunk_markdown(RULES_DOC)
    assert len(blocks) == 5
    assert blocks[0] == "# Environment and workflow rules"
    assert blocks[1].startswith("- Always invoke `python3`")
    # The indented continuation line belongs to its bullet, not to a block of its own.
    assert blocks[3].startswith("- vitest output is captured by the rtk tee")
    assert "never pass `--reporter=basic`" in blocks[3] and blocks[3].count("\n") == 1
    # Plain paragraphs split on blank lines only.
    assert noise_filter.chunk_markdown("first line\nsecond line\n\nnext paragraph\n") == [
        "first line\nsecond line", "next paragraph",
    ]


def test_build_references_drops_blocks_under_four_tokens_and_labels_by_file_and_index(tmp_path: Path) -> None:
    doc = tmp_path / "rules.md"
    doc.write_text(RULES_DOC, encoding="utf-8")
    refs = noise_filter.build_references(None, [str(doc)], set())
    # The heading (3 content tokens) is skipped, but the index keeps counting from the raw chunks.
    assert [r.label for r in refs] == ["rules.md:block1", "rules.md:block2", "rules.md:block3", "rules.md:block4"]
    assert {r.origin for r in refs} == {"doc"}
    assert refs[0].tokens == {"always", "invoke", "python3", "never", "bare", "python", "path", "exits", "127"}


def test_build_references_takes_queue_rows_of_every_status_except_excluded_ids(tmp_path: Path) -> None:
    pending = make_row(QUEUED_PYTHON3)
    rejected = make_row(NOVEL_SANITY, status="rejected")
    excluded = make_row(COMPOSITE_SHELL, status="consumed")
    blank = make_row("", status="triaged")
    queue = tmp_path / "queue.jsonl"
    write_jsonl(queue, [pending, rejected, excluded, blank])
    refs = noise_filter.build_references(str(queue), [], {excluded["id"]})
    assert [r.label for r in refs] == [f"{pending['id']} [pending]", f"{rejected['id']} [rejected]"]
    assert {r.origin for r in refs} == {"queue"}


# --- 2. the four buckets on realistic candidates --------------------------------------------


def test_restatement_of_a_documented_rule_is_suppressed(tmp_path: Path) -> None:
    cand = make_row(RESTATED_PYTHON3)
    _, report = run_filter(tmp_path, [cand], docs={"rules.md": RULES_DOC})
    assert bucket(report, cand["id"]) == "suppressed"
    rec = record(report, cand["id"])
    assert rec["score"] == 0.9 and rec["content_tokens"] == 10
    assert rec["matched"] == ["rules.md:block1"] and rec["matched_origin"] == "doc"
    assert rec["matched_text"] == ["- Always invoke `python3`, never bare `python` (not on PATH, exits 127)."]
    assert rec["reason"].startswith("duplicate: 90% of content already covered by 1 block(s) in doc")


def test_novel_signal_is_kept_clean(tmp_path: Path) -> None:
    cand = make_row(NOVEL_SANITY)
    _, report = run_filter(tmp_path, [cand], docs={"rules.md": RULES_DOC}, extra=("--keep-out", str(tmp_path / "kept.jsonl")))
    assert bucket(report, cand["id"]) == "clean"
    rec = record(report, cand["id"])
    assert rec["score"] < 0.45
    assert "reason" not in rec
    (survivor,) = load_jsonl(tmp_path / "kept.jsonl")
    assert survivor == cand  # written back untouched: no filter_note on a clean keeper


def test_composite_of_known_facts_plus_a_new_one_is_flagged_not_dropped(tmp_path: Path) -> None:
    cand = make_row(COMPOSITE_SHELL)
    _, report = run_filter(tmp_path, [cand], docs={"rules.md": RULES_DOC}, extra=("--keep-out", str(tmp_path / "kept.jsonl")))
    assert bucket(report, cand["id"]) == "flagged"
    rec = record(report, cand["id"])
    assert 0.45 <= rec["score"] < 0.75
    assert rec["score"] == 0.667 and rec["content_tokens"] == 21
    assert rec["matched"] == ["rules.md:block1", "rules.md:block2"]
    assert rec["reason"].startswith("partial-duplicate: 67% already covered by doc")
    # It survives to the queue, carrying the note the human sees at triage.
    (survivor,) = load_jsonl(tmp_path / "kept.jsonl")
    assert survivor["id"] == cand["id"] and survivor["filter_note"] == rec["reason"]


@pytest.mark.parametrize(
    "pattern,content_tokens,score",
    [
        ("never bare python", 3, 1.0),  # fully covered by block1, still thin: the thin check runs first
        ("Shell Gotchas (zsh)", 3, 0.0),  # a bare heading with no overlap at all
        ("Sanity MCP query loop cache", 5, 0.0),  # one token under the floor
    ],
)
def test_thin_candidates_are_dropped_regardless_of_overlap(tmp_path: Path, pattern: str, content_tokens: int, score: float) -> None:
    cand = make_row(pattern)
    _, report = run_filter(tmp_path, [cand], docs={"rules.md": RULES_DOC})
    assert bucket(report, cand["id"]) == "thin"
    rec = record(report, cand["id"])
    assert rec["content_tokens"] == content_tokens and rec["score"] == score
    assert rec["reason"].startswith("thin:")


def test_six_content_tokens_is_the_first_size_that_gets_scored(tmp_path: Path) -> None:
    cand = make_row("Sanity MCP query loop cache result")
    _, report = run_filter(tmp_path, [cand], docs={"rules.md": RULES_DOC})
    assert record(report, cand["id"])["content_tokens"] == 6
    assert bucket(report, cand["id"]) == "clean"


# --- 3. where references come from --------------------------------------------------------


def test_queue_rows_of_any_status_are_references(tmp_path: Path) -> None:
    """A fact the human already rejected must not come back under a new id."""
    known = make_row(QUEUED_PYTHON3, status="rejected")
    cand = make_row(RESTATED_PYTHON3)
    _, report = run_filter(tmp_path, [cand], queue_rows=[known])
    assert bucket(report, cand["id"]) == "suppressed"
    rec = record(report, cand["id"])
    assert rec["matched"] == [f"{known['id']} [rejected]"] and rec["matched_origin"] == "queue"


def test_self_audit_scores_pending_rows_against_the_rest_but_never_against_themselves(tmp_path: Path) -> None:
    restated = make_row(QUEUED_PYTHON3)  # pending, restates the consumed row below
    consumed = make_row(RESTATED_PYTHON3, status="consumed")
    novel = make_row(NOVEL_SANITY)  # pending, matches nothing
    queue = tmp_path / "queue.jsonl"
    write_jsonl(queue, [restated, consumed, novel])
    result = run("--self-audit", "--status", "pending", "--queue", str(queue), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["candidates"] == 2
    assert bucket(report, restated["id"]) == "suppressed"
    assert record(report, restated["id"])["matched"] == [f"{consumed['id']} [consumed]"]
    assert bucket(report, novel["id"]) == "clean"
    assert record(report, novel["id"])["matched"] == []  # in particular, not its own id


def test_build_references_warns_and_skips_a_missing_doc(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    present = tmp_path / "rules.md"
    present.write_text(RULES_DOC, encoding="utf-8")
    absent = tmp_path / "absent.md"
    refs = noise_filter.build_references(None, [str(absent), str(present)], set())
    assert [r.label for r in refs] == ["rules.md:block1", "rules.md:block2", "rules.md:block3", "rules.md:block4"]
    err = capsys.readouterr().err
    assert f"warning: reference doc not found, skipping: {absent}" in err


def test_cli_with_a_missing_reference_doc_still_filters_against_the_rest(tmp_path: Path) -> None:
    cand = make_row(RESTATED_PYTHON3)
    result, report = run_filter(
        tmp_path, [cand], docs={"rules.md": RULES_DOC}, extra=("--reference", str(tmp_path / "absent.md")),
    )
    assert "warning: reference doc not found, skipping:" in result.stderr and "absent.md" in result.stderr
    assert bucket(report, cand["id"]) == "suppressed"
    assert record(report, cand["id"])["matched"] == ["rules.md:block1"]


# --- 4. greedy union across --max-blocks ---------------------------------------------------


@pytest.mark.parametrize(
    "extra,score,expected,blocks_used",
    [
        (("--max-blocks", "1"), 0.2, "clean", 1),
        (("--max-blocks", "2"), 0.4, "clean", 2),
        ((), 0.6, "flagged", 3),  # the CLI default: three blocks, not one and not all five
        (("--max-blocks", "5"), 1.0, "suppressed", 5),
    ],
)
def test_coverage_unions_up_to_max_blocks_and_the_default_is_three(
    tmp_path: Path, extra: tuple[str, ...], score: float, expected: str, blocks_used: int,
) -> None:
    cand = make_row(FIVE_FACTS)
    assert len(set(noise_filter.normalize(FIVE_FACTS))) == 15  # fixture self-check: 3 tokens per bullet
    _, report = run_filter(tmp_path, [cand], docs={"facts.md": FACTS_DOC}, extra=extra)
    rec = record(report, cand["id"])
    assert rec["score"] == score
    assert rec["matched"] == [f"facts.md:block{i}" for i in range(blocks_used)]
    assert bucket(report, cand["id"]) == expected


def test_score_candidate_picks_blocks_by_marginal_gain_not_document_order(tmp_path: Path) -> None:
    doc = tmp_path / "facts.md"
    doc.write_text(FACTS_DOC, encoding="utf-8")
    refs = noise_filter.build_references(None, [str(doc)], set())
    tokens = set(noise_filter.normalize("vitest output is captured by the rtk tee; invoke python3"))
    assert len(tokens) == 7
    score, used = noise_filter.score_candidate(tokens, refs, max_blocks=3)
    assert score == 1.0
    assert [r.label for r in used] == ["facts.md:block2", "facts.md:block0"]  # gain 5 before gain 2
    score, used = noise_filter.score_candidate(tokens, refs, max_blocks=1)
    assert score == pytest.approx(5 / 7) and [r.label for r in used] == ["facts.md:block2"]
    assert noise_filter.score_candidate(set(), refs) == (0.0, [])


# --- 5. calibration baseline ---------------------------------------------------------------


def test_default_calibration_is_pinned(tmp_path: Path) -> None:
    """Regression baseline: a threshold change must fail here, not shift the queue silently."""
    _, report = run_filter(tmp_path, [make_row(NOVEL_SANITY)], docs={"rules.md": RULES_DOC})
    assert report["threshold"] == 0.75
    assert report["flag_threshold"] == 0.45
    assert noise_filter.MIN_CONTENT_TOKENS == 6
    assert inspect.signature(noise_filter.score_candidate).parameters["max_blocks"].default == 3
    # The CLI's own --max-blocks default (a separate constant) is pinned by the staircase test above.


@pytest.mark.parametrize(
    "pattern,content_tokens,score,expected",
    [
        # 6 of 8 tokens covered by two FACTS_DOC bullets: exactly the suppress threshold.
        ("invoke python3 explicitly; the timeout is unavailable on macOS; pytest.ini testpaths", 8, 0.75, "suppressed"),
        # 9 of 20 covered by three bullets: exactly the flag threshold.
        (
            "invoke python3 explicitly; the timeout is unavailable on macOS; the vitest output is in the tee; "
            "pytest.ini sets testpaths to tests and evals; plugin-local test dirs are not collected; bump the version",
            20, 0.45, "flagged",
        ),
        # 8 of 20 covered: one token short of the flag band.
        (
            "invoke python3 first; the timeout is unavailable on macOS; the vitest output is in the tee; "
            "pytest.ini sets testpaths to tests and evals; plugin-local test dirs are not collected; bump the version",
            20, 0.4, "clean",
        ),
    ],
)
def test_thresholds_are_inclusive(tmp_path: Path, pattern: str, content_tokens: int, score: float, expected: str) -> None:
    assert len(set(noise_filter.normalize(pattern))) == content_tokens  # fixture self-check
    cand = make_row(pattern)
    _, report = run_filter(tmp_path, [cand], docs={"facts.md": FACTS_DOC})
    rec = record(report, cand["id"])
    assert rec["score"] == score
    assert bucket(report, cand["id"]) == expected


@pytest.mark.parametrize(
    "flag,value,reported_as,expected",
    [
        ("--threshold", "0.5", "threshold", "suppressed"),  # the 0.667 composite crosses a lowered suppress line
        ("--flag-threshold", "0.7", "flag_threshold", "clean"),  # ...and drops out of a raised flag band
    ],
)
def test_threshold_flags_reach_the_classifier(tmp_path: Path, flag: str, value: str, reported_as: str, expected: str) -> None:
    cand = make_row(COMPOSITE_SHELL)
    _, report = run_filter(tmp_path, [cand], docs={"rules.md": RULES_DOC}, extra=(flag, value))
    assert report[reported_as] == float(value)
    assert record(report, cand["id"])["score"] == 0.667
    assert bucket(report, cand["id"]) == expected


# --- 6. outputs and CLI contract -----------------------------------------------------------


def test_keep_out_holds_exactly_the_survivors_with_flagged_ones_tagged(tmp_path: Path) -> None:
    restated, novel, composite, thin = (
        make_row(RESTATED_PYTHON3), make_row(NOVEL_SANITY), make_row(COMPOSITE_SHELL), make_row("never bare python"),
    )
    kept_path = tmp_path / "kept.jsonl"
    result, report = run_filter(
        tmp_path, [restated, novel, composite, thin], docs={"rules.md": RULES_DOC}, extra=("--keep-out", str(kept_path)),
    )
    assert (report["candidates"], len(report["kept"]), len(report["flagged"]), len(report["suppressed"]), len(report["thin"])) == (4, 2, 1, 1, 1)
    survivors = load_jsonl(kept_path)
    assert [s["id"] for s in survivors] == [novel["id"], composite["id"]]  # input order, dropped rows absent
    assert survivors[0] == novel  # a clean survivor is written back untouched
    assert survivors[1] == {**composite, "filter_note": record(report, composite["id"])["reason"]}
    assert f"survivors written to {kept_path}" in result.stderr


def test_a_fully_suppressed_batch_exits_zero_with_an_empty_keep_out(tmp_path: Path) -> None:
    kept_path = tmp_path / "kept.jsonl"
    result, report = run_filter(
        tmp_path, [make_row(RESTATED_PYTHON3)], docs={"rules.md": RULES_DOC}, extra=("--keep-out", str(kept_path)),
    )
    assert result.returncode == 0
    assert report["kept"] == [] and len(report["suppressed"]) == 1
    assert kept_path.exists() and kept_path.read_text(encoding="utf-8") == ""


def test_text_report_names_every_suppression_with_the_reference_it_matched(tmp_path: Path) -> None:
    """A filtered run must be distinguishable from a run that never happened."""
    restated = make_row(RESTATED_PYTHON3)
    novel = make_row(NOVEL_SANITY)
    result, _ = run_filter(tmp_path, [restated, novel], docs={"rules.md": RULES_DOC}, as_json=False)
    out = result.stdout
    assert "harvest noise filter — 2 candidates, suppress>=0.75 flag>=0.45, 4 reference chunks" in out
    assert "kept 1 (of which 0 flagged) | suppressed 1 | thin 0" in out
    assert "--- SUPPRESSED (1) ---" in out and "--- KEPT (1) ---" in out
    assert f"[0.90] {restated['id']} (headroom-learn)" in out
    assert "^ rules.md:block1: - Always invoke `python3`, never bare `python` (not on PATH, exits 127)." in out
    assert f"[0.05] {novel['id']} (headroom-learn)" in out


def test_cli_requires_candidates_or_self_audit(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    queue.write_text("", encoding="utf-8")
    result = run("--queue", str(queue))
    assert result.returncode == 2
    assert "need --candidates or --self-audit" in result.stderr
