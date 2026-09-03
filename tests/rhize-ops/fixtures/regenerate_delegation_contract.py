#!/usr/bin/env python3
"""regenerate_delegation_contract.py — rebuild delegation-parser-contract.json.

test_delegation_contract.py no longer imports the rhize-delegation:v1 parser directly (the
runtime it lives in, service/src/connectors/delegation-parser.mjs, moved out of this repo to
Rhize-Media/rhize-tasks). Instead it asserts against a captured contract: this script's output,
`delegation-parser-contract.json`, sitting alongside it.

Run this again whenever:
  - the producer fixture strings in test_delegation_contract.py change (the test will fail with
    an "input drifted from the captured contract" message telling you to), or
  - the runtime repo ships a new pinned tag and you want to confirm the parser still accepts the
    same producer format.

Usage (from the rhize-plugins repo root):

    python3 tests/rhize-ops/fixtures/regenerate_delegation_contract.py \\
        --runtime-root /path/to/a/rhize-tasks/checkout \\
        --runtime-tag v0.5.0

`--runtime-root` must be a checkout of https://github.com/Rhize-Media/rhize-tasks at the tag
named by `--runtime-tag` (the script does not verify the checkout's ref — pass the tag you
actually checked out). Requires `node` on PATH; writes no files outside this fixtures/ directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = Path(__file__).resolve().parent
OUTPUT = FIXTURES_DIR / "delegation-parser-contract.json"
PARSER_RELATIVE_PATH = "service/src/connectors/delegation-parser.mjs"

TEST_MODULE_PATH = FIXTURES_DIR.parent / "test_delegation_contract.py"
SPEC = importlib.util.spec_from_file_location("test_delegation_contract", TEST_MODULE_PATH)
test_delegation_contract = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(test_delegation_contract)


def run_parser(parser_path: Path, fixtures: list[str]) -> list[dict[str, object]]:
    """Send producer fixtures through the real parser via a throwaway Node subprocess."""
    harness = f"""
import {{parseDelegation}} from {json.dumps(parser_path.as_uri())};
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
        check=True,
    )
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path, help="Path to a rhize-tasks runtime checkout")
    parser.add_argument("--runtime-tag", required=True, help="Tag the checkout is pinned to, e.g. v0.5.0")
    args = parser.parse_args()

    parser_path = args.runtime_root.resolve() / PARSER_RELATIVE_PATH
    if not parser_path.is_file():
        print(f"ERROR: {parser_path} does not exist", file=sys.stderr)
        return 1
    parser_sha256 = hashlib.sha256(parser_path.read_bytes()).hexdigest()

    ready = test_delegation_contract.READY_FIXTURE
    needs_jira = test_delegation_contract.NEEDS_JIRA_FIXTURE
    invalid = test_delegation_contract.invalid_fixtures(ready)

    results = run_parser(parser_path, [ready, needs_jira, *invalid])
    ready_result, needs_jira_result, *invalid_results = results

    contract = {
        "runtimeRepo": "https://github.com/Rhize-Media/rhize-tasks",
        "runtimeTag": args.runtime_tag,
        "parserRelativePath": PARSER_RELATIVE_PATH,
        "parserSha256": parser_sha256,
        "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fixtures": {
            "ready": {"input": ready, "result": ready_result},
            "needsJira": {"input": needs_jira, "result": needs_jira_result},
            "invalid": [{"input": text, "result": result} for text, result in zip(invalid, invalid_results)],
        },
    }
    OUTPUT.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
