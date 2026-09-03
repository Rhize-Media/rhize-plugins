#!/usr/bin/env python3
"""Static and fixture tests for the rhize-delegation:v1 producer contract.

The rhize-delegation:v1 parser (the consumer side of this contract) used to live in-tree at
rhize-tasks/service/src/connectors/delegation-parser.mjs, and these tests invoked it directly
through a Node subprocess. That runtime moved out to Rhize-Media/rhize-tasks (repo shape R-C,
2026-09-03), so the parser's own tests now live there instead.

What stays here is the PRODUCER side: the delegate-to-teammate skill's message format, and a
captured CONTRACT recording what the last-known consumer accepted for that format —
fixtures/delegation-parser-contract.json, written by regenerate_delegation_contract.py. Tests
below assert the producer fixture strings defined in this file still match the contract's
recorded inputs (if they've drifted, regenerate the contract against a runtime checkout — see
regenerate_delegation_contract.py's own docstring for the exact command) and that the contract's
recorded parse results still satisfy the expectations the producer format promises.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "rhize-ops/skills/delegate-to-teammate/SKILL.md"
REFERENCE = (
    REPO_ROOT
    / "rhize-ops/skills/delegate-to-teammate/references/rhize-delegation-v1.md"
)
README = REPO_ROOT / "rhize-ops/README.md"
GUIDE = REPO_ROOT / "rhize-ops/GUIDE.md"
CONTRACT_FIXTURE = REPO_ROOT / "tests/rhize-ops/fixtures/delegation-parser-contract.json"
TEMPLATE_REFERENCE = (
    REPO_ROOT
    / "rhize-ops/skills/delegate-to-teammate/references/handoff-brief-template.md"
)

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


def invalid_fixtures(ready_fixture: str) -> list[str]:
    """The producer-format violations the contract must record as rejected.

    Kept as a standalone function (rather than inline in a test) so
    regenerate_delegation_contract.py can build the same list when re-capturing the contract
    against a runtime checkout.
    """
    return [
        ready_fixture.replace("*Task:*", "Intro\n*Task:*", 1),
        ready_fixture.replace("*Priority:* high", "*Priority:* critical"),
        ready_fixture.replace("*Jira:* RHIZE-42", "*Jira:* javascript:alert(1)"),
        ready_fixture.replace("550e8400", "550E8400"),
        ready_fixture.replace("550e8400-e29b-41d4-a716", "550e8400-e29b-11d4-a716"),
        ready_fixture + "\ntrailing text",
        ready_fixture + "\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000",
        ready_fixture.replace(
            "Rich human detail.",
            "> rhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000",
        ),
        ready_fixture.replace("Rich human detail.", "rhize-delegation:v1:not-a-uuid"),
        ready_fixture.replace("Rich human detail.", "> *Jira:* RHIZE-999"),
        ready_fixture.replace("Rich human detail.", "context *Due:* 2026-08-18"),
    ]


def load_contract() -> dict[str, Any]:
    if not CONTRACT_FIXTURE.is_file():
        raise FileNotFoundError(
            f"{CONTRACT_FIXTURE} is missing. Regenerate it against a rhize-tasks runtime "
            "checkout: python3 tests/rhize-ops/fixtures/regenerate_delegation_contract.py "
            "--runtime-root <checkout> --runtime-tag <tag>"
        )
    return json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))


def assert_input_matches_contract(actual: str, recorded: str, label: str) -> None:
    if actual != recorded:
        raise AssertionError(
            f"{label} has drifted from the captured contract's recorded input. Regenerate "
            "fixtures/delegation-parser-contract.json against a rhize-tasks runtime checkout: "
            "python3 tests/rhize-ops/fixtures/regenerate_delegation_contract.py "
            "--runtime-root <checkout> --runtime-tag <tag>"
        )


def fenced_block_after(text: str, heading: str) -> str:
    start = text.index(heading)
    fence_start = text.index("```", start) + 3
    newline = text.index("\n", fence_start)
    fence_end = text.index("\n```", newline)
    return text[newline + 1 : fence_end]


def test_contract_fixture_records_provenance() -> None:
    contract = load_contract()
    assert contract["runtimeRepo"] == "https://github.com/Rhize-Media/rhize-tasks"
    assert re.match(r"^v\d+\.\d+\.\d+$", contract["runtimeTag"])
    assert contract["parserRelativePath"] == "service/src/connectors/delegation-parser.mjs"
    assert re.match(r"^[0-9a-f]{64}$", contract["parserSha256"])


def test_contract_fixtures_cover_ready_and_needs_jira() -> None:
    contract = load_contract()
    ready = contract["fixtures"]["ready"]
    needs_jira = contract["fixtures"]["needsJira"]
    assert_input_matches_contract(READY_FIXTURE, ready["input"], "READY_FIXTURE")
    assert_input_matches_contract(NEEDS_JIRA_FIXTURE, needs_jira["input"], "NEEDS_JIRA_FIXTURE")
    assert ready["result"]["ok"] is True
    assert ready["result"]["value"]["jira"] == {"kind": "key", "value": "RHIZE-42"}
    assert needs_jira["result"]["ok"] is True
    assert needs_jira["result"]["value"]["jira"] == {"kind": "needs_jira", "value": None}


def test_batch_fixtures_use_distinct_per_task_ids() -> None:
    contract = load_contract()
    ready_id = contract["fixtures"]["ready"]["result"]["value"]["delegationId"]
    needs_jira_id = contract["fixtures"]["needsJira"]["result"]["value"]["delegationId"]
    assert ready_id != needs_jira_id


def test_jira_and_slack_fixtures_reuse_the_same_task_id() -> None:
    contract = load_contract()
    ready = contract["fixtures"]["ready"]
    assert_input_matches_contract(READY_FIXTURE, ready["input"], "READY_FIXTURE")
    assert ready["result"]["ok"] is True
    delegation_id = ready["result"]["value"]["delegationId"]
    jira_description = (
        "# Task: Audit paid search\n\n"
        "Review the campaign structure.\n\n"
        f"rhize-delegation:v1:{delegation_id}"
    )
    assert jira_description.splitlines()[-1] == READY_FIXTURE.splitlines()[-1]
    assert jira_description.count(f"rhize-delegation:v1:{delegation_id}") == 1
    assert READY_FIXTURE.count(f"rhize-delegation:v1:{delegation_id}") == 1


def test_producer_fixtures_round_trip_through_captured_contract() -> None:
    contract = load_contract()
    invalid = invalid_fixtures(READY_FIXTURE)
    recorded_invalid = contract["fixtures"]["invalid"]
    assert len(recorded_invalid) == len(invalid)
    for index, (text, recorded) in enumerate(zip(invalid, recorded_invalid)):
        assert_input_matches_contract(text, recorded["input"], f"invalid_fixtures()[{index}]")
    assert contract["fixtures"]["ready"]["result"]["ok"] is True
    assert contract["fixtures"]["needsJira"]["result"]["ok"] is True
    assert not any(entry["result"]["ok"] for entry in recorded_invalid)


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


def test_jira_description_template_is_a_concise_brief() -> None:
    skill = SKILL.read_text()
    block = fenced_block_after(skill, "Jira description template")
    assert not any(re.match(r"^#{1,6}\s*Step-by-Step", line) for line in block.splitlines())
    assert sum(1 for line in block.splitlines() if "Paste into Claude:" in line) == 1
    assert "Handoff brief" in block
    assert block.rstrip().endswith("rhize-delegation:v1:<delegation-id>")


def test_skill_bans_paths_in_output() -> None:
    skill = SKILL.read_text()
    assert (
        "No local path, vault-relative path, or repo-relative path may appear in any "
        "Jira, Slack, or Confluence output."
    ) in skill
    assert "delegation_lint.py" in skill


def test_skill_uses_current_obsidian_tool_names() -> None:
    skill = SKILL.read_text()
    for banned in ("obsidian_global_search", "obsidian_read_note", "session_info__read_transcript"):
        assert banned not in skill
    for required in ("obsidian_search_notes", "obsidian_get_note"):
        assert required in skill


def test_confluence_brief_before_jira_and_marker_never_on_confluence() -> None:
    skill = SKILL.read_text()
    assert skill.index("Create the Confluence Handoff Brief") < skill.index("Create a Jira Issue")
    assert "Never put the marker on any Confluence page" in skill


def test_slack_templates_unchanged_envelope() -> None:
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
    assert "Confluence brief" in ready


def test_reference_template_file_exists() -> None:
    assert TEMPLATE_REFERENCE.is_file()
    text = TEMPLATE_REFERENCE.read_text()
    assert "## Step-by-Step Instructions" in text
    assert "[Context]" in text


def main() -> int:
    tests = [
        test_contract_fixture_records_provenance,
        test_contract_fixtures_cover_ready_and_needs_jira,
        test_batch_fixtures_use_distinct_per_task_ids,
        test_jira_and_slack_fixtures_reuse_the_same_task_id,
        test_producer_fixtures_round_trip_through_captured_contract,
        test_each_task_gets_one_stable_id_before_side_effects,
        test_skill_has_parser_stable_ready_and_needs_jira_templates,
        test_jira_description_and_slack_ready_template_share_one_id,
        test_root_is_unmarked_and_priority_mapping_is_closed,
        test_reference_documents_grammar_identity_and_merge_rules,
        test_plugin_docs_explain_the_strict_fallback,
        test_jira_description_template_is_a_concise_brief,
        test_skill_bans_paths_in_output,
        test_skill_uses_current_obsidian_tool_names,
        test_confluence_brief_before_jira_and_marker_never_on_confluence,
        test_slack_templates_unchanged_envelope,
        test_reference_template_file_exists,
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
