"""Muse Code worker confinement: classifier contract on the 2026-11-11 capture, plus an opt-in live probe."""
import copy
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import muse_confinement_probe as probe  # noqa: E402

FIXTURE = json.loads((HERE / "fixtures" / "muse-1.4.15-confinement-2026-11-11.json").read_text())


def test_capture_is_not_confined_for_the_documented_reasons():
    verdict, reasons = probe.classify(FIXTURE["control"], FIXTURE["hardened"])
    assert verdict == "not_confined"
    assert reasons == FIXTURE["reasons"]
    joined = "\n".join(reasons)
    for expected in ("untrusted: ambient context", "untrusted: bundled developer_prompts", "untrusted: rules user_sources",
                     "trusted: active tools ['mcp__canary__canary_tool']", "trusted: user MCP server started"):
        assert expected in joined


def test_control_without_canaries_is_probe_broken_not_a_pass():
    control = copy.deepcopy(FIXTURE["control"])
    control["mcp_started"] = False
    control["lead"]["active_tools"] = [t for t in control["lead"]["active_tools"] if not t.startswith("mcp__")]
    del control["lead"]["context"]["rules_file"]
    clean = _clean(FIXTURE["hardened"][0])
    verdict, reasons = probe.classify(control, [clean])
    assert verdict == "probe_broken"
    assert len(reasons) == 2


def test_clean_record_is_confined():
    runs = [_clean(run) for run in FIXTURE["hardened"]]
    assert probe.classify(FIXTURE["control"], runs) == ("confined", [])


def test_launcher_script_is_refused(tmp_path):
    launcher = tmp_path / "muse"
    launcher.write_text("#!/usr/bin/env bash\nexec true\n")
    with pytest.raises(SystemExit, match="pinned muse-bin"):
        probe.probe(str(launcher))


@pytest.mark.skipif(not os.environ.get("RHIZE_MUSE_BIN"), reason="set RHIZE_MUSE_BIN to a pinned muse-bin-<version>")
def test_live_pinned_binary_matches_capture(tmp_path):
    result = probe.probe(os.environ["RHIZE_MUSE_BIN"], root=str(tmp_path))
    assert result["verdict"] != "probe_broken", result["reasons"]
    if result["binary"] == FIXTURE["binary"]:
        assert result["verdict"] == "not_confined"


def _clean(run):
    run = copy.deepcopy(run)
    run.update(mcp_started=False, subagent_runs=0)
    run["lead"].update(active_tools=[], reminders=[], delegation="inactive",
                       context={k: v for k, v in run["lead"]["context"].items() if k in probe.POSTURE_CONTEXT})
    run["trace"] = {"rules.context_load": {"user_sources": 0}, "plugin_capability_snapshot.compose": {"skills": 0},
                    "hook.admission": {"handlers": 0}, "lead_tool_surface": [0, 0]}
    return run
