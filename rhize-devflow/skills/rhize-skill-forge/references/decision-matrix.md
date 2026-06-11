# Decision Matrix — the five verbs

Every candidate resolves to exactly one verb. The forced choice is deliberate: ambiguity is where
bloat and licensing risk enter. Use this file to disambiguate.

## Inputs to the decision

1. **Overlap** with the nearest existing Rhize skill (from `overlap_scan.py`): high / medium / low.
2. **Quality** of the candidate: structure, specificity, whether it explains *why*, test coverage.
3. **License**: permissive (MIT/Apache/BSD/CC-BY/public-domain) / attribution-required / copyleft /
   none-stated / restrictive. See `provenance.md`.
4. **Maintenance**: is upstream active? versioned? likely to change?
5. **Stack fit**: does it assume a stack that matches Rhize (Next.js/Sanity/Payload/Supabase/Vercel/
   n8n) or something foreign?

## The matrix

```
                 LOW overlap            MEDIUM overlap          HIGH overlap
HIGH quality   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
permissive     │ DEFER (install,  │  │ FORK (re-skin to  │  │ ABSORB (patch the │
               │ point our skills │  │ Rhize conventions)│  │ better parts into │
               │ at it)           │  │                   │  │ the near skill)   │
               └──────────────────┘  └──────────────────┘  └──────────────────┘
LOW quality    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  or           │ WATCH (link as   │  │ REJECT (or ABSORB │  │ REJECT (we already│
poor fit       │ reference, track)│  │ one good doc only)│  │ do this better)   │
               └──────────────────┘  └──────────────────┘  └──────────────────┘
```

License overrides everything: **none-stated, copyleft into a permissive set, or restrictive →
REJECT or escalate to the user**, regardless of quality or overlap.

## Verb definitions

### DEFER
Adopt the external skill as-is (install the plugin, keep the marketplace skill). Take nothing into
Rhize except a one-line pointer in the nearest Rhize skill's description ("for X, defer to
`plugin:skill`"). Best when the candidate is high quality, actively maintained, and you'd only be
re-typing it. Example: the official `sentry:*` developer kit vs. our thin `sentry-instrumentation`.

### ABSORB
Pull specific patterns/files into an existing Rhize skill via a `skill-refinement` patch. Use when
one Rhize skill clearly owns this domain and the candidate has a handful of better parts (a script,
a reference table, a sharper heuristic). Never absorb the whole thing — name the exact parts in the
ingestion report. The output is a `SKILL.patch.md` / `SKILL.extend.md` / new reference file on the
target skill, plus a `SOURCES.md` entry.

### FORK
Copy the candidate into a new `rhize-<name>/` skill and re-skin it: valid frontmatter, pushy
description, Rhize stack assumptions, `/rhize-devflow:` command namespace, provenance entry. Use when the
bones are good but it's a new capability for Rhize (low overlap) OR the house style differs enough
that a patch would be messier than a clean fork. Forking is heavier — justify it over DEFER.

### REJECT
Take nothing. Record the reason so the candidate isn't silently re-evaluated next quarter. Common
reasons: redundant with an existing Rhize skill that's already better, low quality, or a license
you can't accept.

### WATCH
Don't adopt now. Add a reference link in the nearest Rhize skill and a ledger entry with an
upstream-check command. Use for promising-but-immature skills, or things you only want as a
citation. Revisit on drift.

## Anti-patterns

- **Absorbing the whole skill** "to be safe" — that's just FORK with extra steps and no re-skin.
- **FORK when DEFER would do** — if you'd copy it nearly verbatim and it's well maintained, defer.
- **Skipping verification** because the candidate "is obviously good" — prove it beats baseline.
- **Two verbs at once** — if it looks like ABSORB *and* FORK, your overlap analysis is unfinished.
