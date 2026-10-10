"""End-to-end check of the skill-map routing harness (evals/skill-map-routing).

Runs the real pipeline (python3 + node subprocesses) on this checkout into a temp dir and
asserts the output shape, determinism of the committed corpus, and that the scorer's
--check mechanism passes against the committed baseline.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "evals" / "skill-map-routing"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for the routing harness")


def run(*args, **kw):
    return subprocess.run([sys.executable, str(HARNESS / "run.py"), *map(str, args)], capture_output=True, text=True, timeout=120, **kw)


@pytest.fixture(scope="module")
def harness_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("routing")
    proc = run("--out", out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def test_results_shape(harness_run):
    res = json.loads((harness_run / "results.json").read_text())
    s = res["summary"]
    assert set(s) == {"eval_positives", "eval_negatives", "probes", "long_negatives"}
    for k in ("hit", "wrong", "silent"):
        assert k in s["eval_positives"] and k in s["probes"]
    assert s["eval_positives"]["n"] == sum(s["eval_positives"][k] for k in ("hit", "wrong", "silent"))
    neg = s["eval_negatives"]
    assert neg["n"] == sum(neg[k] for k in ("false_trigger", "other_cross_plugin", "other_same_plugin", "silent"))
    assert s["probes"]["n"] == 17
    ln = s["long_negatives"]
    assert ln["n"] >= 60 and ln["fires"] + ln["acceptable"] + ln["silent"] == ln["n"]
    assert 0 <= ln["fire_rate"] <= 1
    assert res["per_plugin"] and all("rhize" in p or "-" in p for p in res["per_plugin"])
    assert len(res["rows"]) == sum(v["n"] for v in s.values())


def test_corpus_is_fresh_and_deterministic(harness_run):
    committed = (HARNESS / "corpus.json").read_text()
    assert (harness_run / "corpus.json").read_text() == committed, (
        "committed corpus.json is stale: run evals/skill-map-routing/run.py and refresh corpus.json, baseline.json, inferred_baseline.json"
    )
    corpus = json.loads(committed)
    probes = [r for r in corpus["rows"] if r["group"] == "probe"]
    assert len(probes) == 17 and all(r["authored"] == "author-written" for r in probes)


def test_long_negatives_file():
    rows = json.loads((HARNESS / "long_negatives.json").read_text())["rows"]
    assert len(rows) >= 60 and len({r["id"] for r in rows}) == len(rows)
    assert all({"id", "prompt", "kind"} <= set(r) for r in rows)
    assert sum(1 for r in rows if r.get("acceptable")) <= 15


def test_gates_pass_against_committed_baseline(harness_run, tmp_path):
    # The committed thresholds hold literal limits (e.g. probe wrong <= 2) that unmodified main
    # does not necessarily meet, so verify the --check mechanism with every gate relative to the
    # baseline: the run under test must reproduce its own committed baseline.
    t = json.loads((HARNESS / "thresholds.json").read_text())
    ids = {g["id"] for g in t["gates"]}
    assert {"eval_false_trigger", "eval_other_cross_plugin", "long_negative_fire_rate", "probe_wrong", "eval_wrong", "eval_hit"} <= ids
    for g in t["gates"]:
        if g["id"] != "eval_false_trigger":
            g["value"] = "baseline"
    rel = tmp_path / "relative_thresholds.json"
    rel.write_text(json.dumps(t))
    proc = subprocess.run(
        [sys.executable, str(HARNESS / "score.py"), "--check", str(HARNESS / "baseline.json"),
         "--thresholds", str(rel), "--results", str(harness_run / "results.json"), "--strict-rows"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_check_fails_when_a_gate_is_violated(harness_run, tmp_path):
    res = json.loads((harness_run / "results.json").read_text())
    res["summary"]["eval_negatives"]["false_trigger"] = 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(res))
    proc = subprocess.run(
        [sys.executable, str(HARNESS / "score.py"), "--check", str(HARNESS / "baseline.json"),
         "--thresholds", str(HARNESS / "thresholds.json"), "--results", str(bad)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 1 and "FAIL  eval_false_trigger" in proc.stdout
