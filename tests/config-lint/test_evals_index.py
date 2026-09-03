"""test_evals_index.py — evals/README.md documents every suite directory.

Guards against the `evals/` tree growing an undocumented suite the `## Suites`
section in `evals/README.md` doesn't mention. `results/` (auto-generated
output) and `__pycache__/` are not suites and are excluded, as is any
directory that contains no files at all (an empty placeholder is not a
suite either).

pytest-based, matching tests/config-lint/test_description_parity.py's style.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "evals"
README_PATH = EVALS_DIR / "README.md"
EXCLUDED_DIRS = {"results", "__pycache__"}


def _discovered_suite_dirs() -> list[str]:
    names = []
    for entry in sorted(EVALS_DIR.iterdir()):
        if not entry.is_dir() or entry.name in EXCLUDED_DIRS:
            continue
        if not any(p.is_file() for p in entry.rglob("*")):
            continue
        names.append(entry.name)
    return names


def _suites_section(text: str) -> str:
    start_match = re.search(r"(?m)^## Suites\s*$", text)
    assert start_match, "evals/README.md has no '## Suites' heading"
    start = start_match.end()
    next_heading = re.search(r"(?m)^## ", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


SUITE_DIRS = _discovered_suite_dirs()


def test_discovers_at_least_the_known_suite_directories() -> None:
    # Sanity check on the discovery helper itself — evals/ has had 15+ suite
    # directories since before this test existed.
    assert len(SUITE_DIRS) >= 10, SUITE_DIRS


@pytest.mark.parametrize("name", SUITE_DIRS)
def test_suite_directory_is_documented_in_suites_section(name: str) -> None:
    text = README_PATH.read_text(encoding="utf-8")
    section = _suites_section(text)
    heading = re.search(rf"(?m)^#{{1,6}}\s*{re.escape(name)}\b", section)
    bold_lead = re.search(rf"(?m)^\*\*{re.escape(name)}\*\*", section)
    assert heading or bold_lead, (
        f"evals/README.md's '## Suites' section does not document '{name}' "
        "(expected either a Markdown heading or a bold lead line naming it)"
    )
