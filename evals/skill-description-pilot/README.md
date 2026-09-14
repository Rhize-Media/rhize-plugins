# Shared skill description pilot

This is a static fixture for a description-only discovery experiment across Claude Code and
Codex. Arm A is the baseline commit and descriptions recorded in `fixture.json`; Arm B is the
candidate descriptions in that file. Each host must be evaluated within its own matched model,
version, tools, and reasoning cohort. Do not compare one host's baseline with another host's
candidate as an A/B result.

The prompts cover positive routing, negative routing, adjacent skills, and explicit invocation.
Expectations apply to the first skill selected for the initial prompt; workflow-driven downstream
skill calls remain allowed. Expected outcomes are hypotheses to check in bounded host runs, not
measured behavior.
Fixture consistency tests and lexical description matches are not behavioral proof. Record exact
host observations, source/fixture digests, failures, and unavailable usage separately; do not claim
token savings or runtime improvement from this static pilot.

The fixture pins the starting source commit, whole-file SHA-256 values, exact before/after
description text and hashes, plus hashes for frontmatter outside the description and the complete
skill body. The three description fields are the only skill-source changes in Arm B.

Run the focused fixture invariants with:

```bash
python3 -m pytest tests/evals/test_skill_description_pilot.py -q
```
