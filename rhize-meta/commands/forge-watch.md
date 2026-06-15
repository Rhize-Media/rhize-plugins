# /rhize-meta:forge-watch

Drift check across every external source already absorbed, deferred, or watched. Surfaces sources
whose upstream has moved since ingestion, so absorbed patterns don't silently rot.

## Usage
```
/rhize-meta:forge-watch
```

## Steps
1. `python3 scripts/record_provenance.py --check-drift --skills-root <rhize-skills-root>`.
2. For each listed source, run its stored drift-check command (compare stored upstream ref to
   current). Where upstream moved, note the delta.
3. For anything that changed materially, recommend re-running `/rhize-meta:forge-ingest` on the delta.

Good fit for a weekly scheduled task.
