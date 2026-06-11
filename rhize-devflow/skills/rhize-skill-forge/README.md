# rhize-skill-forge

The **import side** of the Rhize meta-toolchain.

- `skill-creator` → build skills from scratch
- `skill-refinement` → improve your own skills from usage feedback
- **`rhize-skill-forge` → decide what to pull IN from external skills, and how**

## What it does

Investigates an external skill (directory, `SKILL.md`, `.skill` bundle, marketplace skill, or
GitHub repo), then resolves it to exactly one verb:

| Verb | Meaning |
|------|---------|
| DEFER | adopt as-is, point our skills at it |
| ABSORB | patch the worthwhile parts into an existing Rhize skill |
| FORK | copy + re-skin to Rhize conventions as a new skill |
| REJECT | take nothing (and record why) |
| WATCH | link as reference, track upstream |

It reuses `skill-refinement`'s patch machinery to absorb, the `skill-creator` eval loop to verify
the result beats baseline, and writes a `SOURCES.md` ledger + vault note for provenance/license.

## Files

```
rhize-skill-forge/
├── SKILL.md                       # router + 6-step workflow
├── commands/
│   ├── forge-ingest.md            # /rhize-devflow:forge-ingest <source>  (full pipeline)
│   ├── forge-scan.md              # /rhize-devflow:forge-scan <source>    (read-only)
│   └── forge-watch.md             # /rhize-devflow:forge-watch            (drift check)
├── references/
│   ├── decision-matrix.md         # the five-verb criteria
│   ├── overlap-analysis.md        # how the similarity score works
│   └── provenance.md              # license handling + SOURCES.md format
├── scripts/
│   ├── profile_skill.py           # parse a candidate → JSON profile
│   ├── overlap_scan.py            # rank candidate vs existing Rhize skills
│   └── record_provenance.py       # ledger + vault note + drift check
└── templates/
    └── ingestion-report.md        # per-candidate worksheet
```

All scripts are stdlib-only and support `--json`.

## Quick start

```bash
# Read-only triage
python3 scripts/profile_skill.py /path/to/candidate-skill
python3 scripts/overlap_scan.py /path/to/candidate-skill --skills-root ~/dev-local/CLAUDE-SKILLS

# After deciding + verifying, record it
python3 scripts/record_provenance.py \
  --source "https://github.com/org/repo" --name "their-skill" --version "1.2.0" \
  --license "MIT" --verb ABSORB --target data-mutation-consistency \
  --took "the optimistic-update reference doc" --verified "beats baseline 2/2" \
  --skills-root ~/dev-local/CLAUDE-SKILLS --vault "/path/to/vault/Projects/Skill Forge"
```
