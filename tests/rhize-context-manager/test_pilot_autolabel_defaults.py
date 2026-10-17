"""Labeler batch-size default: 50 cases per run; the allowed range is unchanged."""
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import pilot_autolabel as auto


def test_default_batch_is_fifty_within_the_unchanged_range():
    assert auto.DEFAULTS['maxCases'] == 50
    assert auto.LIMITS['maxCases'] == (1, 100)
