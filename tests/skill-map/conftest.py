"""conftest.py — shared pytest fixtures for tests/skill-map/*.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "generated" / "skill-map.static.json"


@pytest.fixture(scope="session")
def doc() -> dict:
    """The parsed, committed generated/skill-map.static.json artifact.

    Session-scoped since the file doesn't change during a test run and
    parsing it repeatedly per-test would be wasted work.
    """
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
