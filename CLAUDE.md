# Rhize Plugins

## Skill Usage (IMPORTANT)

This project contains Claude Code skills (plugins). When a user's request matches an available skill's description, you MUST invoke it using the Skill tool rather than handling the request with general knowledge and native tools.

**Rules:**
- Check the available skills list before responding to any user request
- If a skill's trigger description matches the user's intent, invoke it with the Skill tool immediately
- Do NOT attempt to replicate skill functionality using WebFetch, Bash, or other tools when a matching skill exists
- Skills contain specialized workflows, API integrations, and output formats that general-purpose tool use cannot replicate

**Available skill categories:**

*SEO/AEO/GEO plugin:*
- SEO auditing and analysis (`seo-site-audit`)
- Keyword research and intelligence (`keyword-intelligence`)
- Backlink analysis (`backlink-intelligence`)
- SERP checking and monitoring (`serp-intelligence`)
- Content SEO optimization (`content-seo`)
- AI/Answer Engine Optimization (`aeo-geo-optimization`)
- Next.js + Sanity SEO review (`nextjs-sanity-seo`)

*Obsidian Skills plugin:*
- Obsidian CLI operations (`obsidian-cli`)
- Obsidian markdown syntax (`obsidian-markdown`)
- Obsidian Bases database views (`obsidian-bases`)
- JSON Canvas visual boards (`json-canvas`)
- Web clipping with Defuddle (`defuddle`)
- Second brain / PKM methodology (`second-brain`)
- Vault note templates (`vault-templates`)
- Vault health and alignment (`vault-alignment`)

*Project Launcher plugin:*
- Full project launch pipeline — research, PRD, gap analysis, scaffold, GSD v2 handoff (`project-launcher`)
- Commands: `/launch-project`, `/write-prd`, `/scaffold-gsd`, `/grill-prd`
