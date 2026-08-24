#!/usr/bin/env python3
"""Static and fixture tests for the rhize-delegation:v1 producer contract."""

from __future__ import annotations

import json
import subprocess
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
PARSER = REPO_ROOT / "rhize-tasks/service/src/connectors/delegation-parser.mjs"

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


def parse_with_consumer(fixtures: list[str]) -> list[dict[str, object]]:
    """Send producer fixtures through the real Rhize Tasks consumer parser."""
    harness = f"""
import {{parseDelegation}} from {json.dumps(PARSER.as_uri())};
let input = '';
for await (const chunk of process.stdin) input += chunk;
const allowlist = {{workspaceId: 'T1', channelId: 'C1', senderIds: ['B1']}};
const results = JSON.parse(input).map((text) => {{
  try {{
    return {{ok: true, value: parseDelegation({{workspaceId: 'T1', channelId: 'C1', senderId: 'B1', text}}, allowlist)}};
  }} catch (error) {{
    return {{ok: false, error: String(error?.message ?? error)}};
  }}
}});
process.stdout.write(JSON.stringify(results));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", harness],
        input=json.dumps(fixtures),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return json.loads(completed.stdout)


def fenced_block_after(text: str, heading: str) -> str:
    start = text.index(heading)
    fence_start = text.index("```", start) + 3
    newline = text.index("\n", fence_start)
    fence_end = text.index("\n```", newline)
    return text[newline + 1 : fence_end]


def test_contract_fixtures_cover_ready_and_needs_jira() -> None:
    ready, needs_jira = parse_with_consumer([READY_FIXTURE, NEEDS_JIRA_FIXTURE])
    assert ready["ok"] is True
    assert ready["value"]["jira"] == {"kind": "key", "value": "RHIZE-42"}
    assert needs_jira["ok"] is True
    assert needs_jira["value"]["jira"] == {"kind": "needs_jira", "value": None}


def test_batch_fixtures_use_distinct_per_task_ids() -> None:
    ready, needs_jira = parse_with_consumer([READY_FIXTURE, NEEDS_JIRA_FIXTURE])
    ready_id = ready["value"]["delegationId"]
    needs_jira_id = needs_jira["value"]["delegationId"]
    assert ready_id != needs_jira_id


def test_jira_and_slack_fixtures_reuse_the_same_task_id() -> None:
    parsed = parse_with_consumer([READY_FIXTURE])[0]
    assert parsed["ok"] is True
    delegation_id = parsed["value"]["delegationId"]
    jira_description = (
        "# Task: Audit paid search\n\n"
        "Review the campaign structure.\n\n"
        f"rhize-delegation:v1:{delegation_id}"
    )
    assert jira_description.splitlines()[-1] == READY_FIXTURE.splitlines()[-1]
    assert jira_description.count(f"rhize-delegation:v1:{delegation_id}") == 1
    assert READY_FIXTURE.count(f"rhize-delegation:v1:{delegation_id}") == 1


def test_producer_fixtures_round_trip_through_real_consumer() -> None:
    invalid = [
        READY_FIXTURE.replace("*Task:*", "Intro\n*Task:*", 1),
        READY_FIXTURE.replace("*Priority:* high", "*Priority:* critical"),
        READY_FIXTURE.replace("*Jira:* RHIZE-42", "*Jira:* javascript:alert(1)"),
        READY_FIXTURE.replace("550e8400", "550E8400"),
        READY_FIXTURE.replace("550e8400-e29b-41d4-a716", "550e8400-e29b-11d4-a716"),
        READY_FIXTURE + "\ntrailing text",
        READY_FIXTURE + "\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000",
        READY_FIXTURE.replace(
            "Rich human detail.",
            "> rhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000",
        ),
        READY_FIXTURE.replace("Rich human detail.", "rhize-delegation:v1:not-a-uuid"),
        READY_FIXTURE.replace("Rich human detail.", "> *Jira:* RHIZE-999"),
        READY_FIXTURE.replace("Rich human detail.", "context *Due:* 2026-08-18"),
    ]
    results = parse_with_consumer([READY_FIXTURE, NEEDS_JIRA_FIXTURE, *invalid])
    assert [result["ok"] for result in results[:2]] == [True, True]
    assert not any(result["ok"] for result in results[2:])


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
    assert "choose exactly one Jira status fragment" in skill
    assert ":ticket: needs_jira" in skill
    assert "Never invent a tracker URL or issue key" in skill
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
        test_producer_fixtures_round_trip_through_real_consumer,
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
