# /rhize-devflow:forge-watch

Drift check across every external source already absorbed, deferred, or watched. Surfaces sources
whose upstream has moved since ingestion, so absorbed patterns don't silently rot.

## Usage
```
/rhize-devflow:forge-watch
```

## Steps
1. `python3 scripts/record_provenance.py --check-drift --skills-root <forge-skill-dir>` (the dir holding `SOURCES.md`).
2. For each listed source, run its stored drift-check command (compare stored upstream ref to
   current). Where upstream moved, note the delta.
3. For anything that changed materially, recommend re-running `/rhize-devflow:forge-ingest` on the delta.

Invoked, not scheduled — drift detection has a single cron (the `ai-stack-version-drift` sensor);
this command is the on-demand classifier it feeds. See `references/drift-boundaries.md`.
