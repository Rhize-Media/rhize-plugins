# Three-way drift: reconciling upstream movement with local improvements

**Status:** approved 2026-08-09/10 (Jim) · builds on `572f919` (remote upstream URLs)

## Problem

The drift check is two-way (local-now vs upstream-now), so deliberate local improvements and
unreviewed upstream movement both read as "drifted". All 7 forks currently report drifted
solely because of Rhize's added `metadata.rhize` frontmatter — permanent noise that would
hide real upstream divergence.

## Design

**Baseline** = upstream content hash as of the last human review (ingestion or re-baseline).
Recorded as curated DATA in SOURCES.md, never fetched at build time (compiler stays offline
and deterministic).

Four-state verdict matrix (replaces the single "drifted"):

| localNormalized vs baseline | upstreamNow vs baseline | status | actionable |
|---|---|---|---|
| == | == | `in-sync` | no |
| != | == | `local-only` | no (ours, deliberate, in git) |
| == | != | `upstream-moved` | YES |
| != | != | `diverged` | YES |

`upstream-unreachable` / `local-missing` unchanged. Only `upstream-moved` + `diverged`
(+ `unreachable`) queue refinement entries; `local-only` is informational.

**Normalization** (the 5-line tagging exclusion): ONE implementation, in the Python
compiler only. Skill nodes that are `fork-of` sources gain `contentHashNormalized` =
sha256 of the file with the Rhize-injected `metadata.rhize` frontmatter block textually
removed (precise rule: the `metadata:` mapping line and its indented children are removed
IFF `rhize` is metadata's only key; else only the `rhize:` subtree lines). skill-forge
compares hashes it is handed — it never re-implements stripping (the duplicated-validator
lesson).

**Baseline storage/plumbing:**
- SOURCES.md per-entry field, matching the existing bullet format:
  `- **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)`
- New `scripts/baseline_upstreams.py`: fetches each entry's http(s) Source, hashes, writes/
  updates the baseline field (idempotent; `--skill <name>` filter; skips non-URL sources
  with a report; this is the intentional "I reviewed upstream, accept its state" action).
- Compiler copies the baseline onto the per-skill EXTERNAL node as `baselineHash`
  (NOT into edge `driftCheck` — skill-forge's guard test pins driftCheck as display-only;
  node data is the sanctioned read surface, same as `url`/`path`).

**skill-forge `watch` matrix:** upstreamHash = sha256(fetched body). With a baseline
present on the upstream node AND `contentHashNormalized` on the local node → emit the
four-state verdict + both hashes in `--json`. Missing either input → fall back to today's
two-way compare (status `drifted`) so older maps keep working. Never-execute invariant
untouched.

**Audit:** weekly-skill-audit step 0 queues only `upstream-moved`/`diverged`/`unreachable`;
`local-only` and `in-sync` are counted in the report line only. Re-baseline instruction
documented: after reviewing/adopting upstream changes, run `baseline_upstreams.py` and
commit SOURCES.md.

## Immediate effect once baselined (today's expected truth)

All 7 forks reclassify `drifted` → `local-only` (their only difference from upstream is our
tagging), i.e. quiet. Future upstream commits flip them to `upstream-moved`/`diverged`.

## Verification bar

rhize-plugins: baseline script idempotency test (run twice → no diff), normalization unit
tests (block present/absent/metadata-has-other-keys/no-frontmatter), compiler emits
baselineHash + contentHashNormalized only where SOURCES.md provides them, schema updated,
determinism + --check-stale + full suite green, docs (docs/skill-map.md) + CHANGELOG +
audit SKILL.md updated. skill-forge: matrix unit tests for all four states + fallback +
unreachable, build+test green, README updated. End-to-end: `watch --json` on the real map
reports 7× `local-only` after baselining.
