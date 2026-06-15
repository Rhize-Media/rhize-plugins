# Provenance & License Handling

You are adopting other people's work. You must always be able to answer: **where did this come
from, what version, and are we allowed to use it this way?** This file defines the rules and the
ledger format.

## License triage (do this in Step 1, before forming an opinion)

`profile_skill.py` reports a detected license (from a LICENSE file or frontmatter). Classify it:

| Class | Examples | Action |
|-------|----------|--------|
| **Permissive** | MIT, Apache-2.0, BSD-2/3, ISC, CC0, Unlicense, public domain | OK to ABSORB/FORK. Keep attribution where the license asks (Apache NOTICE, BSD copyright line). |
| **Attribution** | CC-BY, MIT (attribution clause) | OK, but you MUST keep the copyright/attribution in `SOURCES.md` and any forked files. |
| **Copyleft** | GPL, AGPL, CC-BY-SA, MPL | Escalate. Copyleft can infect a permissively-licensed Rhize set. Default: DEFER (use without copying) or REJECT. Do not ABSORB/FORK without explicit user sign-off. |
| **None stated** | no LICENSE, no frontmatter license | Escalate. Absence of a license means all rights reserved by default. Default: REJECT or WATCH; ask the user. |
| **Restrictive / proprietary** | "all rights reserved", custom EULA, "personal use only" | REJECT. Surface the exact clause to the user. |

**Rule:** never ABSORB or FORK on copyleft, none-stated, or restrictive licenses without showing
the user the exact license text and getting explicit approval. DEFER (use the installed skill
without copying its source into ours) is usually safe regardless of license — you're not
redistributing.

## What counts as "taking"

- Copying SKILL.md prose, a reference doc, a script, a config, or a template → **taking** (license
  applies).
- Reading a skill and independently writing your own pattern that happens to be similar → generally
  not taking, but cite the inspiration in `SOURCES.md` anyway for honesty and drift tracking.
- Installing/using a marketplace skill as-is (DEFER) → not redistributing; lowest risk.

## SOURCES.md ledger format

`record_provenance.py` maintains `SOURCES.md` at the Rhize skills root. One entry per ingestion:

```markdown
## <candidate-name> — <YYYY-MM-DD>
- **Source:** <url-or-path>
- **Upstream ref:** <version | git commit | "n/a">
- **License:** <SPDX or description> (<permissive|attribution|copyleft|none|restrictive>)
- **Verb:** <DEFER|ABSORB|FORK|REJECT|WATCH>
- **Target:** <rhize-skill or "n/a">
- **Took:** <specific files/patterns taken, or "nothing">
- **Verified:** <eval-loop result, or "n/a">
- **Drift check:** `<command to detect upstream change>`
- **Notes:** <reason for the verb>
```

## Vault note

`record_provenance.py` also emits a stub note for the Obsidian vault (under `Projects/` or a
`Skill Forge/` MOC) so the decision lives in the second brain, links to related skills with
`[[wikilinks]]`, and is searchable later. The git ledger is the audit trail; the vault note is the
narrative.

## Drift

Each non-REJECT entry stores an upstream ref. `record_provenance.py --check-drift` compares stored
refs against current upstream (where resolvable) and lists what moved, so absorbed patterns don't
silently rot against their source.
