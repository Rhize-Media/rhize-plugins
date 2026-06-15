# /rhize-meta:skill-find &lt;query&gt;

Discover skills relevant to a task via **skills.sh**, vet them, and gate on safety before adopting.

Steps (scripts live in `rhize-meta/skills/rhize-skill-forge/scripts/`):

1. **Discover** — `python3 .../skills_sh.py search "<query>" --limit 10`
   Returns ranked matches with `id`, install count, and `npx skills add <installUrl>`.
2. **Partner audit** — for any candidate: `python3 .../skills_sh.py audit <id>`
   Aggregated verdicts from Socket / Snyk / Gen Agent Trust Hub / etc. (pass / warn / fail + risk).
3. **Deep local gate** — before adding it: `python3 .../skill_safety.py <path-or-git-url> --no-llm`
   Runs SkillSpector; **BLOCK on HIGH/CRITICAL**, CAUTION on MEDIUM. Never adds an unscanned skill.
4. **Decide** — hand a vetted candidate to the forge (`/rhize-meta:forge-ingest`) for the
   DEFER / ABSORB / FORK / REJECT / WATCH decision + provenance.

If discovery or scanning reports missing setup, run `/rhize-meta:skill-doctor` first.

The two-layer safety check is deliberate: skills.sh audits give a fast partner verdict; SkillSpector
adds a deep static (+ optional LLM) scan of the actual files. A skill must clear **both** before it's
added to a Rhize project or skill set.
