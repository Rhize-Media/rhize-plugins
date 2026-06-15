# /rhize-meta:skill-doctor

Check that the skill discovery + safety tooling is ready (skills.sh + SkillSpector). This is the
lightweight setup step — run it before first use, or whenever discovery/scanning reports a gap.

Run:

```bash
python3 rhize-meta/skills/rhize-skill-forge/scripts/skill_doctor.py
```

It reports whether **SkillSpector** is installed (deep local safety scan), whether the **skills.sh**
Vercel OIDC token is present (discovery + partner audits), and whether an optional LLM provider is
configured for SkillSpector's semantic stage — with exact setup steps for any gaps.

- Static safety scanning needs only SkillSpector installed (no API key).
- skills.sh discovery + audits additionally need `VERCEL_OIDC_TOKEN` (enable OIDC Federation on a
  Vercel project, then `vercel link && vercel env pull`).
