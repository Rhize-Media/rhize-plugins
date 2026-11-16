# Tom's ad research guide

**Current status:** the first live provider test returned a billed error after Meta blocked the scraper. Research collection is held; setup, status, evidence review and export remain usable. No usable ads were collected.

Start with `/rhize-ad-research:setup` in Claude Code or `$rhize-ad-research-setup` in Codex, and say “Set up Rhize Ad Research for TAG.” Use the same Mac account and workspace in both tools. The assistant will check Python, identify Apify access, and prepare local storage. You should not need to write JSON or copy secrets into the conversation.

Jim administers the account and authorizes the allowance. Complete account sign-in and secure Keychain enrollment when prompted. A provider connection alone does not permit paid work. The first allowance is a bounded qualification spike; subsequent collection needs applicable authority. Only one person/computer collects for the same account/client at a time.

Use `/rhize-ad-research:research` in Claude Code or `$rhize-ad-research-collect` in Codex, and ask: “Research detailing and ceramic coating equally within the approved allowance.” Review the selected search or advertiser URLs and the planned limits. Keep the run ID. Claude Code and Codex can inspect the same job; if the app closes, ask to resume that exact run. Never start a fresh job just because an earlier request timed out.

| Result | Next action |
| --- | --- |
| In progress | Resume the existing run. |
| Submission unknown | Reconcile the provider run; do not resubmit. |
| Provider error | Retain the report and ask Jim to review provider qualification; do not retry paid jobs. |
| Held | Resolve the named access, billing, authority, or schema issue. |
| Partial/capped | Review usable rows and acknowledge what is missing. |
| Unknown/empty | Treat as unverified; zero rows cannot establish that the search has no ads. |
| Failed/cancelled | Review the failure and any retained evidence. |
| Research collected | Export JSON/CSV and review the sources. |

Ask for an export when ready. Keep detailing and coating coverage visible and note shortfalls. Public ads do not disclose actual performance. Treat promising hooks, offers, and formats as hypotheses for original creative tests; do not copy another business's claims or footage.

Before calling this ready on your Mac, run setup, the public provider check, a scoped authorized collection, a restart/resume, and an export. Switch hosts and confirm the same run and allowance are visible. Jim must review billing and evidence. Local fixture tests on Jim's machine are not Tom acceptance. Creative briefs, scheduling, and Meta performance imports are later features.
