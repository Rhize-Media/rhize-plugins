# Tom's ad research guide

Start with `/rhize-ad-research:setup` in Claude Code or `$rhize-ad-research-setup` in Codex. Say “Set up TAG ad research on this Mac in both hosts.” The assistant checks Python, connects the official Meta MCP and prepares private shared storage. You sign in with your own Rhize-authorized Meta identity. Never paste a token into chat. Apify is no longer required.

The setup assistant follows [native setup](docs/native-setup.md), verifies your app role and active ad-account access, and restricts the server to library search. Local doctor success alone does not prove access. Use the same Mac user and workspace in both hosts. If the source package was updated, restart the host before continuing.

Then invoke `/rhize-ad-research:research` or `$rhize-ad-research-collect` and ask: “Research detailing and ceramic coating equally for TAG, five ads per service. Compare hooks, offers and consumer concerns with source links.” Review the chosen queries, country and limits. The assistant calls Meta and saves a bounded sample. You do not need to write JSON. Keep the run IDs; switching hosts or restarting must inspect/resume those IDs without another provider request.

| Status | Meaning and action |
| --- | --- |
| Awaiting response | Make the single planned native call and import its capture. |
| Held | Inspect the named failure and original evidence; do not overwrite or re-query automatically. |
| No ads returned | Absence is unverified; check access and query coverage. |
| Partial sample | Some returned rows were rejected. Review usable evidence and shortfalls. |
| Bounded sample | Export and check advertiser relevance; this is not complete coverage. |
| Historical Apify | Inspect/export retained files only; reconcile historical billing separately. |

Ask for JSON/CSV exports. Review detailing and coating separately; source links, missing fields and shortfalls must stay visible. Treat candidate hooks/offers as hypotheses for original tests. Public-library ads do not disclose conversion performance, so none is a verified winner from this evidence alone.

Your acceptance checklist: authenticate each host, retrieve one bounded sample in each, compare captured IDs/titles with the tool result, restart/resume without re-querying, export, then inspect the same run from the other host. Verify non-search Meta tools are blocked without making an external mutation. Jim's successful host probes do not prove your permissions or Mac setup. No automatic schedules, media copying, creative production or campaign launch are included.

## Public research beyond ads

Run `/rhize-ad-research:brief` or `$rhize-research-brief` and state your question. Ask for a cited brief plus limitations and JSON/CSV. This uses your host's existing public tools and does not require Meta access unless you also collect ads. The [research guide](docs/research-brief.md) gives the shared schema and your acceptance checklist. Full upstream Agent Reach/browser-session reuse stays excluded; no cookies or login tokens should be supplied.

## Agent Reach public research

Use the [public adapter setup guide](docs/agent-reach-public.md) for bounded Reddit/web search, Jina page reads, GitHub repositories/issues and V2EX topics. Docker Desktop and Python3.11+ are required; no cookies, session transfer or Meta token is used. Both native hosts passed source checks. Exa page reads returned a rate limit during qualification, so that operation has no successful live acceptance yet. See [verification](docs/verification.md) for release and Tom acceptance status. Existing tools and official Meta research remain independent.
