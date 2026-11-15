"""test_refinement_backlog.py — the read-only refinement-queue backlog report."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "rhize-context-manager" / "scripts"
          / "refinement_backlog.py")
NOW = "2026-11-15T00:00:00Z"
MARK = "SECRET-MARKER-XYZ"


def run(queue, *extra, as_json=True):
    cmd = [sys.executable, str(SCRIPT), "report", "--queue", str(queue), "--now", NOW, *extra]
    if as_json:
        cmd.append("--json")
    return subprocess.run(cmd, capture_output=True, text=True)


def write(path, rows, raw=()):
    lines = [json.dumps(r) for r in rows] + list(raw)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ent(i, **kw):
    base = {"id": i, "ts": "2026-11-10T00:00:00Z", "source": "s", "repo": "r", "status": "pending"}
    base.update(kw)
    return base


def test_ranking_and_tiebreak(tmp_path):
    q = write(tmp_path / "q.jsonl", [
        ent("b"), ent("a"),
        ent("c", count=5, ts="2026-01-01T00:00:00Z"),
        ent("d", ts="2026-11-14T00:00:00Z"),
        ent("e", evidence={"generated_at": "2026-11-15T00:00:00Z"}),
    ])
    rep = json.loads(run(q).stdout)
    assert [r["id"] for r in rep["top"]] == ["c", "e", "d", "a", "b"]
    assert rep["ranking"]["sessions"] == "not available"


def test_stale_and_ts_handling(tmp_path):
    q = write(tmp_path / "q.jsonl", [
        ent("old", ts="2026-10-01T00:00:00+00:00"),
        ent("new", ts="2026-11-10T00:00:00Z"),
        ent("none", ts=None), ent("bad", ts="not-a-date"),
    ])
    rep = json.loads(run(q, "--stale-days", "30").stdout)
    rows = {r["id"]: r for r in rep["top"]}
    assert rows["old"]["stale"] and rows["old"]["age_days"] == 45.0
    assert not rows["new"]["stale"]
    for k in ("none", "bad"):
        assert rows[k]["age_days"] is None and rows[k]["stale"] is False
        assert rows[k]["age_unknown"] is True
    assert rep["stale"] == 1


def test_non_pending_counted_not_ranked_and_unparsable(tmp_path):
    q = write(tmp_path / "q.jsonl",
              [ent("p"), ent("t", status="triaged"), ent("x", status="rejected")],
              raw=["{broken", "[1,2]", ""])
    rep = json.loads(run(q).stdout)
    assert [r["id"] for r in rep["top"]] == ["p"]
    assert rep["totals_by_status"] == {"pending": 1, "triaged": 1, "rejected": 1}
    assert rep["unparsable"] == 2 and rep["pending"] == 1


def test_supersession(tmp_path):
    kw = dict(target_skill="foo", signal_type="t", subtype="u")
    q = write(tmp_path / "q.jsonl", [
        ent("o1", ts="2026-11-01T00:00:00Z", **kw),
        ent("new", ts="2026-11-09T00:00:00Z", **kw),
        ent("o2", ts="2026-11-05T00:00:00Z", **kw),
        ent("other", ts="2026-11-02T00:00:00Z", target_skill="foo", signal_type="z", subtype="u"),
        ent("noskill", ts="2026-11-02T00:00:00Z", **{**kw, "target_skill": ""}),
    ])
    rep = json.loads(run(q).stdout)
    assert rep["supersession_candidates"] == [
        {"older_id": "o1", "newer_id": "new"}, {"older_id": "o2", "newer_id": "new"}]


def test_target_outcomes(tmp_path):
    root = tmp_path / "skills"
    (root / "here").mkdir(parents=True)
    q = write(tmp_path / "q.jsonl", [
        ent("p", target_skill="here"),
        ent("abs", target_path=str(root / "gone")),
        ent("pre", target_skill="rhize-context-manager/skills/gone"),
        ent("bare", target_skill="gone"),
        ent("esc", target_skill="../x"),
    ])
    rep = json.loads(run(q, "--root", str(root)).stdout)
    loss = {c["id"]: c for c in rep["target_loss_candidates"]}
    assert "p" not in loss
    # Absence is provable for an absolute path under a root and for a prefixed path.
    for k in ("abs", "pre"):
        assert loss[k]["status"] == "target_missing" and loss[k]["checked"]
    # A bare name may be a built-in or another host's skill: never "missing".
    assert loss["bare"]["status"] == "lookup_failed"
    assert loss["esc"]["status"] == "lookup_failed"
    rep = json.loads(run(q, "--root", str(tmp_path / "absent")).stdout)
    assert {c["status"] for c in rep["target_loss_candidates"]} == {"lookup_failed"}


def test_plugin_skill_ids(tmp_path):
    plugins = tmp_path / "repo"
    (plugins / "alpha" / "skills" / "real").mkdir(parents=True)
    q = write(tmp_path / "q.jsonl", [
        ent("ok", target_skill="alpha/real"),
        ent("gone", target_skill="alpha/removed"),
        ent("unknown", target_skill="no-such-plugin/thing"),
    ])
    rep = json.loads(run(q, "--root", str(tmp_path / "skills"), "--plugins-root", str(plugins)).stdout)
    loss = {c["id"]: c for c in rep["target_loss_candidates"]}
    assert "ok" not in loss
    assert loss["gone"]["status"] == "target_missing"
    assert loss["gone"]["checked"] == [str(plugins / "alpha" / "skills" / "removed")]
    assert loss["unknown"]["status"] == "lookup_failed"


def test_supersession_needs_the_same_lesson(tmp_path):
    q = write(tmp_path / "q.jsonl", [
        ent("a", ts="2026-11-01T00:00:00Z", target_skill="foo", pattern="First  lesson"),
        ent("b", ts="2026-11-05T00:00:00Z", target_skill="foo", pattern="a different lesson"),
        ent("c", ts="2026-11-09T00:00:00Z", target_skill="foo", pattern="first lesson"),
        ent("d", ts="2026-11-02T00:00:00Z", target_skill="foo"),
        # Same lesson, same timestamp as the newest: no order is proved, so no pair.
        ent("e", ts="2026-11-09T00:00:00Z", target_skill="foo", pattern="FIRST lesson"),
        # Same lesson, no valid timestamp: never a pair.
        ent("f", ts="not-a-date", target_skill="foo", pattern="first lesson"),
    ])
    rep = json.loads(run(q).stdout)
    assert rep["supersession_candidates"] == [{"older_id": "a", "newer_id": "c"}]


def test_free_text_in_identifier_fields_and_status(tmp_path):
    q = write(tmp_path / "q.jsonl", [
        ent("has space " + MARK),
        ent("ok1", source="some words " + MARK, repo="a b " + MARK, signal_type=MARK + " x"),
        ent("ok2", target_path="/tmp/a path with " + MARK),
        ent("ok3", status=MARK + " secret status"),
        ent({"note": MARK}),
    ])
    for as_json in (True, False):
        r = run(q, as_json=as_json)
        assert r.returncode == 0 and MARK not in r.stdout + r.stderr
    rep = json.loads(run(q).stdout)
    assert rep["totals_by_status"] == {"pending": 4, "other": 1}
    # A target that is not identifier-shaped is never resolved or echoed.
    assert [c for c in rep["target_loss_candidates"] if c["id"] == "ok2"] == [
        {"status": "lookup_failed", "id": "ok2"}]


def test_paths_cannot_leave_their_base(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("x", encoding="utf-8")
    os.symlink(str(outside), str(root / "link"))
    q = write(tmp_path / "q.jsonl", [
        ent("slash", target_skill="rhize-context-manager/skills/" + str(outside / "secret.md")),
        ent("sym", target_skill="rhize-context-manager/skills/link/secret.md"),
        ent("symgone", target_skill="rhize-context-manager/skills/link/absent.md"),
    ])
    rep = json.loads(run(q, "--root", str(root)).stdout)
    loss = {c["id"]: c for c in rep["target_loss_candidates"]}
    # Neither "present" (it would be absent from the list) nor "target_missing".
    assert {k: loss[k]["status"] for k in ("slash", "sym", "symgone")} == {
        "slash": "lookup_failed", "sym": "lookup_failed", "symgone": "lookup_failed"}


def test_non_finite_numbers_give_strict_json(tmp_path):
    q = write(tmp_path / "q.jsonl", [], raw=[
        '{"id":"n1","ts":"2026-11-10T00:00:00Z","status":"pending","est_savings":NaN,"count":1e999}',
        '{"id":"n2","ts":"2026-11-10T00:00:00Z","status":"pending","est_savings":Infinity,"count":-5}',
    ])
    r = run(q)

    def reject(token):
        raise AssertionError("non-standard JSON token: %s" % token)

    rep = json.loads(r.stdout, parse_constant=reject)
    assert [(x["id"], x["evidence_count"], x["est_savings"]) for x in rep["top"]] == [
        ("n1", 1, None), ("n2", 1, None)]


def test_non_string_identifiers_are_dropped(tmp_path):
    q = write(tmp_path / "q.jsonl", [ent("p", source={"x": MARK}, repo=[MARK], subtype=MARK * 40)])
    for as_json in (True, False):
        r = run(q, as_json=as_json)
        assert r.returncode == 0 and MARK not in r.stdout + r.stderr


def test_top_and_json_shape(tmp_path):
    q = write(tmp_path / "q.jsonl", [ent("a%d" % i) for i in range(5)])
    rep = json.loads(run(q, "--top", "2").stdout)
    assert len(rep["top"]) == 2
    assert set(rep) == {"totals_by_status", "pending", "stale", "unparsable", "stale_days",
                        "ranking", "top", "supersession_candidates", "target_loss_candidates"}
    text = run(q, "--top", "2", as_json=False).stdout
    assert "pending: 5" in text and "Supersession" in text


def test_missing_queue_exit_2(tmp_path):
    r = run(tmp_path / "nope.jsonl")
    assert r.returncode == 2 and r.stderr


def test_privacy(tmp_path):
    q = write(tmp_path / "q.jsonl", [ent(
        "p", pattern=MARK, note=MARK, filter_note=MARK, triage_reason=MARK, harvest_log=MARK,
        disposition=MARK, evidence={"kind": MARK, "generated_at": "2026-11-01T00:00:00Z"},
        target_skill="skill-" + "a", est_savings="~" + MARK)])
    for as_json in (True, False):
        r = run(q, as_json=as_json)
        assert r.returncode == 0 and MARK not in r.stdout + r.stderr


def test_no_write(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    q = write(d / "q.jsonl", [ent("a"), ent("b", target_skill="x")])
    before = (q.read_bytes(), q.stat().st_mtime_ns, sorted(os.listdir(d)))
    assert run(q, "--root", str(tmp_path)).returncode == 0
    assert run(q, as_json=False).returncode == 0
    assert (q.read_bytes(), q.stat().st_mtime_ns, sorted(os.listdir(d))) == before
