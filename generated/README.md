# generated/

Generated files only — never hand-edit. Rebuild with `python3 scripts/build_skill_map.py`.

Pass `--install` to also copy the artifact to
`~/.claude/context-manager/skill-map.static.json` — the location installed-plugin
consumers (e.g. `rhize-context-manager/hooks/skill-router.js`) read from, since an
installed plugin cannot see this repo's `generated/` directory.
