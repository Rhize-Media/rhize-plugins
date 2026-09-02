# Generated Docs & Vault Publish

Deep reference for the "Generated docs" section summarized in
[`docs/skill-map.md`](../skill-map.md).

Phase 5 replaces the flat, hand-restated skill tables in this repo's READMEs with **managed
sections** — content between `<!-- SKILL-MAP:BEGIN -->` / `<!-- SKILL-MAP:END -->` markers,
produced by `scripts/render_skill_map_docs.py` from `generated/skill-map.static.json` and
`.claude-plugin/marketplace.json`. Everything outside a marker pair is ordinary hand-written prose
and is never touched by the script.

**What's managed:**

| File | Managed section |
|---|---|
| Root `README.md` | The Plugin Catalog table (`Plugin \| Version \| Skill Count \| Description \| Docs`). |
| Each plugin's `README.md` | Its skill table (`Skill \| Description \| Topics`). `rhize-context-manager`'s table covers only the Rhize-authored skills (those without a `fork-of` edge) — the curated-third-party group is prose, not a table, and stays hand-written. `obsidian-second-brain`'s table covers only the "Second Brain" group; "Format Skills" is a separate hand-written table left untouched. |
| `generated/SKILL-CATALOG.md` | The full cross-plugin catalog, one section per plugin, in marketplace order. |
| `docs/README.md` | The `docs/` index's per-plugin block — name, version, canonical description, README/GUIDE links, and a skill count linking into `generated/SKILL-CATALOG.md#<name>`. |

Every skill table (plugin READMEs and `SKILL-CATALOG.md`) prefers a skill's `metadata.rhize.summary`
frontmatter — a short, plain-language sentence written for a human reader — over the mechanically
derived first sentence of its `description`, which is a runtime trigger string ("ALWAYS invoke this
skill...") rather than a human summary. `summary` is optional; a skill without one still gets the
`first_sentence(description)` fallback. `scripts/build_skill_map.py` reads it from
`metadata.rhize.summary`; `scripts/validate_skill_map.py` enforces ≤160 characters and no backticks
when it's present.

**Regenerating:**

```bash
python3 scripts/build_skill_map.py          # rebuild the static artifact first if it's stale
python3 scripts/render_skill_map_docs.py    # fill managed sections; idempotent, refuses if a
                                             # target file has no marker pair
```

A file with no marker pair is a hard error, not a guess — add the `<!-- SKILL-MAP:BEGIN -->` /
`<!-- SKILL-MAP:END -->` pair by hand at the intended location once, then the script owns
everything between them from then on. `tests/skill-map/test_render_docs.py` covers idempotency,
marker preservation, and the refusal behavior.

**Vault publish** (`scripts/publish_skill_map_vault.py`) renders the same static artifact into an
Obsidian vault as one Markdown note per skill (structured frontmatter: `plugin`, `topics`,
`stacks`, `source_path`), a `Skill Map.base` inventory view over those notes, and a `Skill
Map.canvas` topology diagram (plugin → skill containment, `fork-of`/`replaces`/`depends-on`
edges, topic/stack tag clusters). No usage/co-occurrence data is published — structural facts
only. The vault path is resolved at runtime (`RHIZE_VAULT_PATH` env var, or the vault marked
`"open": true` in Obsidian's own global config) and is never hardcoded or committed; nothing this
script writes lives in this repo.

---

Back to [`docs/skill-map.md`](../skill-map.md).
