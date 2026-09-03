# rhize-cowork

Cowork project skill set — scaffolding the context layer that makes every later task in a Cowork project sharp instead of generic.

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `project-kickoff` | Scaffold the four standard Cowork client-context files — CLAUDE.md (operating manual), BUSINESS.md (the business/offer/market), PERSONALITY… | content-authoring, knowledge-management, project-planning |
<!-- SKILL-MAP:END -->

## Architecture

```
rhize-cowork/
├── .claude-plugin/
│   └── plugin.json
├── README.md                          # This file (technical reference)
├── GUIDE.md                           # User-facing walkthrough
├── setup/
│   └── manifest.json                  # Opt-in capabilities for /rhize-core:setup (currently empty)
└── skills/
    └── project-kickoff/
        ├── SKILL.md                   # Workflow: inventory inputs → confirm frame → gap interview → write files → hand off
        └── assets/
            ├── CLAUDE.template.md     # Operating-manual template ({{TOKEN}} placeholders)
            ├── BUSINESS.template.md   # Business/offer/market template
            ├── PERSONALITY.template.md# Brand voice & tone template
            └── INFO.template.md       # Links, tools, people template
```

## How it works

1. **Inventory inputs** — website given → fetch and extract (tagged `[inferred]`); owner docs given → extract as confirmed; nothing given → guided interview.
2. **Confirm the frame** — whose business this is, and the one-line win the project must produce.
3. **Gap interview** — asks only what the inputs didn't answer, batched in small groups (frame → business → voice → reference).
4. **Write files** — copies each template from `assets/`, fills every `{{TOKEN}}`, saves to the project root.
5. **Hand off** — surfaces every `[TBD — confirm]` and `[inferred]` item as a punch-out list for verification.

## Data-integrity rules (non-negotiable)

- **Never fabricates business facts.** Unconfirmed → `[TBD — confirm]`; pulled from a website/doc rather than the owner → `[inferred]`. Tags are preserved verbatim in output.
- Empty fields stay cleanly `[TBD — confirm]` — no filler padding.
- Shaky or dated stats/claims are flagged before they ship.

## Setup

No external credentials or MCP servers required. Web fetch/browser access improves Scenario A (website-driven kickoff) but the skill degrades gracefully to the interview without it.

## Optional outputs

`SCOPE.md`, `OFFER.md`, and an `ASSETS/` pointer folder are offered only when the engagement warrants them — never built unprompted.
