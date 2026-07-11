# /rhize-meta:forge-ingest

Full ingestion pipeline for an external skill: profile → scan → decide → execute → verify → record.

## Usage
```
/rhize-meta:forge-ingest [source]
```
`<source>` = a directory, a `SKILL.md`, a `.skill` bundle, a marketplace skill name, or a GitHub URL.
For a GitHub URL, fetch it to a temp dir first, then proceed.

**No `<source>`** — drain the `skill-forge` CLI's pending queue instead. Check
`~/.skill-forge/queue.json` for `status: "pending"` entries and process each one (see the "CLI
pending queue" section of `SKILL.md`): reuse the entry's gate results rather than re-profiling or
re-scanning, decide, execute, verify, record, then close the entry as `"ingested"` or `"dismissed"`.

## Steps
1. **Profile** — `python3 scripts/profile_skill.py <source> --json`. Read it. Triage the license
   immediately (see `references/provenance.md`).
2. **Scan** — `python3 scripts/overlap_scan.py <source> --skills-root <rhize-skills-root> --json`.
3. **Decide** — open the nearest 1–2 Rhize skills + the candidate; pick one verb from
   `references/decision-matrix.md`. Present the recommendation block and get explicit confirmation.
   Block on copyleft/none/restrictive licenses.
4. **Execute** the verb:
   - ABSORB → hand the chosen patterns to `skill-refinement` as a patch against the target.
   - FORK → copy to `rhize-<name>/`, re-skin to the Rhize frontmatter/description standard.
   - DEFER → add a pointer in the nearest skill's description.
   - WATCH/REJECT → ledger entry only.
5. **Verify** (ABSORB/FORK) — run the `skill-creator` eval loop; absorbed output must beat baseline.
6. **Record** — `python3 scripts/record_provenance.py --source ... --name ... --verb ... --skills-root ... --vault <vault-dir>`.

Fill `templates/ingestion-report.md` as you go.
