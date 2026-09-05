"""Ensure pending targeted activations cannot enter the legacy triaged drain."""
from pathlib import Path

def test_capture_uses_a_distinct_non_drainable_status():
    text = (Path(__file__).resolve().parents[2] / "rhize-context-manager/commands/skill-refine.md").read_text()
    capture = text.split("## `capture`", 1)[1].split("## `run`", 1)[0]
    run = text.split("## `run`", 1)[1]
    assert "Before capture," in capture
    assert "status `activation-pending`" in capture
    assert "Never drain `activation-pending`" in run
    assert "Only after that read-back and scenario check" in capture
    assert "continue only the unfinished" in capture
