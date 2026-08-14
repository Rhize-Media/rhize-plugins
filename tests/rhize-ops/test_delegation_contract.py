#!/usr/bin/env python3
"""Static and fixture tests for the rhize-delegation:v1 producer contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "rhize-ops/skills/delegate-to-teammate/SKILL.md"
REFERENCE = (
    REPO_ROOT
    / "rhize-ops/skills/delegate-to-teammate/references/rhize-delegation-v1.md"
)
README = REPO_ROOT / "rhize-ops/README.md"
GUIDE = REPO_ROOT / "rhize-ops/GUIDE.md"

UUID_V4 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
FOOTER = re.compile(
    r"^rhize-delegation:v1:"
    r"([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)
FIELD = re.compile(r"^\*(Task|Due|Priority|Jira):\* (.+)$")
PRIORITIES = {"urgent", "high", "normal", "low"}

READY_FIXTURE = """*Task:* Audit paid search
*Due:* 2026-08-17
*Priority:* high
*Jira:* RHIZE-42

Rich human detail.

rhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000"""

NEEDS_JIRA_FIXTURE = """*Task:* Audit paid search
*Due:* 2026-08-17
*Priority:* normal
*Jira:* needs_jira

Rich human detail.

rhize-delegation:v1:9e6f4516-4a70-4d4b-9227-3dd74f2c9be2"""


def parse_fixture(text: str) -> dict[str, str]:
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 5:
        raise ValueError("missing fields or footer")

    expected = ["Task", "Due", "Priority", "Jira"]
    fields: dict[str, str] = {}
    for index, name in enumerate(expected):
        match = FIELD.fullmatch(lines[index])
        if not match or match.group(1) != name:
            raise ValueError("fields must be anchored and ordered")
        fields[name] = match.group(2)

    extra_fields = [line for line in lines[4:-1] if FIELD.fullmatch(line)]
    if extra_fields:
        raise ValueError("duplicate fields")
    markers = [match for line in lines if (match := FOOTER.fullmatch(line))]
    if len(markers) != 1 or not FOOTER.fullmatch(lines[-1]):
        raise ValueError("footer must occur once as the final nonblank line")
    if "\n" in fields["Task"] or not fields["Task"].strip():
        raise ValueError("invalid task")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields["Due"]):
        raise ValueError("invalid due date")
    if fields["Priority"] not in PRIORITIES:
        raise ValueError("invalid priority")
    if not (
        fields["Jira"] == "needs_jira"
        or re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", fields["Jira"])
        or fields["Jira"].startswith("https://")
    ):
        raise ValueError("invalid Jira value")
    if not UUID_V4.fullmatch(markers[0].group(1)):
        raise ValueError("invalid UUID")
    fields["delegation_id"] = markers[0].group(1)
    return fields


def fenced_block_after(text: str, heading: str) -> str:
    start = text.index(heading)
    fence_start = text.index("```", start) + 3
    newline = text.index("\n", fence_start)
    fence_end = text.index("\n```", newline)
    return text[newline + 1 : fence_end]


def test_contract_fixtures_cover_ready_and_needs_jira() -> None:
    assert parse_fixture(READY_FIXTURE)["Jira"] == "RHIZE-42"
    assert parse_fixture(NEEDS_JIRA_FIXTURE)["Jira"] == "needs_jira"


def test_batch_fixtures_use_distinct_per_task_ids() -> None:
    ready_id = parse_fixture(READY_FIXTURE)["delegation_id"]
    needs_jira_id = parse_fixture(NEEDS_JIRA_FIXTURE)["delegation_id"]
    assert ready_id != needs_jira_id


def test_jira_and_slack_fixtures_reuse_the_same_task_id() -> None:
    delegation_id = parse_fixture(READY_FIXTURE)["delegation_id"]
    jira_description = (
        "# Task: Audit paid search\n\n"
        "Review the campaign structure.\n\n"
        f"rhize-delegation:v1:{delegation_id}"
    )
    assert jira_description.splitlines()[-1] == READY_FIXTURE.splitlines()[-1]
    assert jira_description.count(f"rhize-delegation:v1:{delegation_id}") == 1
    assert READY_FIXTURE.count(f"rhize-delegation:v1:{delegation_id}") == 1


def test_contract_fixtures_reject_invalid_variants() -> None:
    invalid = [
        READY_FIXTURE.replace("*Task:*", "Intro\n*Task:*", 1),
        READY_FIXTURE.replace("*Priority:* high", "*Priority:* critical"),
        READY_FIXTURE.replace("*Jira:* RHIZE-42", "*Jira:* javascript:alert(1)"),
        READY_FIXTURE.replace("550e8400", "550E8400"),
        READY_FIXTURE.replace("550e8400-e29b-41d4-a716", "550e8400-e29b-11d4-a716"),
        READY_FIXTURE + "\ntrailing text",
        READY_FIXTURE + "\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000",
    ]
    for value in invalid:
        try:
            parse_fixture(value)
        except ValueError:
            continue
        raise AssertionError(f"invalid fixture was accepted: {value!r}")


def test_each_task_gets_one_stable_id_before_side_effects() -> None:
    skill = SKILL.read_text()
    assert skill.index("Generate delegation IDs") < skill.index("Create a Jira Issue")
    assert "uuidgen | tr '[:upper:]' '[:lower:]'" in skill
    assert "never regenerate" in skill.lower()
    assert "Never reuse one task's delegation ID for another task" in skill


def test_skill_has_parser_stable_ready_and_needs_jira_templates() -> None:
    skill = SKILL.read_text()
    ready = fenced_block_after(skill, "Jira-ready per-task Slack reply")
    needs_jira = fenced_block_after(skill, "Jira-skipped or Jira-failed per-task Slack reply")
    for block, expected_jira in ((ready, "[Tracker URL or ISSUE-KEY]"), (needs_jira, "needs_jira")):
        lines = block.splitlines()
        assert lines[:4] == [
            "*Task:* [Single-line task title]",
            "*Due:* YYYY-MM-DD",
            "*Priority:* urgent|high|normal|low",
            f"*Jira:* {expected_jira}",
        ]
        assert block.count("rhize-delegation:v1:<delegation-id>") == 1
        assert block.rstrip().endswith("rhize-delegation:v1:<delegation-id>")


def test_jira_description_and_slack_ready_template_share_one_id() -> None:
    skill = SKILL.read_text()
    jira = fenced_block_after(skill, "Jira description template")
    slack = fenced_block_after(skill, "Jira-ready per-task Slack reply")
    assert jira.count("rhize-delegation:v1:<delegation-id>") == 1
    assert jira.rstrip().endswith("rhize-delegation:v1:<delegation-id>")
    assert slack.count("rhize-delegation:v1:<delegation-id>") == 1
    assert "same in-memory `<delegation-id>`" in skill


def test_root_is_unmarked_and_priority_mapping_is_closed() -> None:
    skill = SKILL.read_text()
    assert "Never add contract fields or a delegation marker to the shared multi-task root message" in skill
    for mapping in (
        "Urgent/Highest → `urgent`",
        "High → `high`",
        "Medium/Normal → `normal`",
        "Low → `low`",
    ):
        assert mapping in skill


def test_reference_documents_grammar_identity_and_merge_rules() -> None:
    reference = REFERENCE.read_text()
    for required in (
        "one ID per task",
        "final nonblank line",
        "exact ID only",
        "root message is ignored",
        "actual Slack event sender",
        "never regenerate",
        "workspace ID, channel ID, and delegation ID",
        "untrusted data",
    ):
        assert required.lower() in reference.lower()
    assert reference.count("rhize-delegation:v1:") >= 6


def test_plugin_docs_explain_the_strict_fallback() -> None:
    for path in (README, GUIDE):
        text = path.read_text()
        assert "rhize-delegation:v1" in text
        assert "rhize-delegation-v1.md" in text
        assert "arbitrary Slack" in text


def main() -> int:
    tests = [
        test_contract_fixtures_cover_ready_and_needs_jira,
        test_batch_fixtures_use_distinct_per_task_ids,
        test_jira_and_slack_fixtures_reuse_the_same_task_id,
        test_contract_fixtures_reject_invalid_variants,
        test_each_task_gets_one_stable_id_before_side_effects,
        test_skill_has_parser_stable_ready_and_needs_jira_templates,
        test_jira_description_and_slack_ready_template_share_one_id,
        test_root_is_unmarked_and_priority_mapping_is_closed,
        test_reference_documents_grammar_identity_and_merge_rules,
        test_plugin_docs_explain_the_strict_fallback,
    ]
    failures = 0
    for function in tests:
        try:
            function()
            print(f"PASS {function.__name__}")
        except (AssertionError, ValueError, FileNotFoundError) as error:
            failures += 1
            print(f"FAIL {function.__name__}: {error}")
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print("\nAll delegation contract tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
