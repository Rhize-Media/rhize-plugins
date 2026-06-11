# /rhize-devflow:forge-scan

Read-only assessment of an external skill. No changes — just the profile, overlap, and a
recommended verb. Use this to triage a backlog of candidates before committing to any ingestion.

## Usage
```
/rhize-devflow:forge-scan <source>
```

## Steps
1. `python3 scripts/profile_skill.py <source>` — structure, license, deps.
2. `python3 scripts/overlap_scan.py <source> --skills-root <rhize-skills-root>` — nearest skill +
   suggested verb.
3. Output the recommendation block (no execution):
   ```
   🔨 Forge scan: <name> (v<version>, <license>)
   Nearest Rhize skill : <name> (<score>)
   Recommended verb    : <verb>
   Worth a closer look : <yes/no + one line>
   ```

Stop there. If the user wants to proceed, continue with `/rhize-devflow:forge-ingest`.
