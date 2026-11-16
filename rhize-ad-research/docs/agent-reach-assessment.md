# Agent Reach assessment — 2026-11-16

Decision: **WATCH; optional external dependency after qualification. Do not bundle or fork it into Rhize Ad Research.** No upstream code, platform login or cookie transfer was executed. The requested research is complete; adoption is a separate decision.

## Inspected source

[Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach), version 1.6.1, inspected commit `c70ae6da5d39bc90e09ad2ae0575ccc89f31e284`, Python >=3.10, MIT license. Use this repository identity: the similarly named PyPI package is not this project. Source inspection and SkillForge scans are not live platform qualification.

Agent Reach routes upstream CLIs/browser tools and normalizes results/errors. It is not a sentiment or trend-analysis engine. Current channels include GitHub, YouTube, web, V2EX and Bilibili by default; Reddit, LinkedIn jobs, Xiaohongshu, Xueqiu, Boss and Xiaoyuzhou are optional; X/Twitter, Facebook and Instagram are experimental. Older search summaries list a different channel count; this assessment follows the pinned source.

## Fit for TAG and Rhize

Reddit is the strongest potential addition: search discussions, read a post and a bounded set of comments, or inspect recent subreddit posts. This could surface detailing-price objections, coating expectations, maintenance concerns and customer vocabulary. The source reads up to 20 comments in its post-read path; it does not promise the full reply tree, a historical time series or representative consumer coverage. Public page fallback and browser-authenticated access differ and must be tested separately.

YouTube supplies transcripts/subtitles, not a general comments dataset. Facebook exposes search/profile rather than full post/comment collection; Instagram exposes profiles/posts without a comment-research guarantee. These are not replacements for the verified official Meta Ads Library MCP.

A useful later Rhize workflow would preserve source URLs/IDs, captured times, query and time scope, missing/rejected samples, and concise attributed observations. Keep observed customer statements separate from inferred themes. A rising-topic claim requires comparable repeated time windows and denominators; engagement and a convenience sample alone do not establish population-level sentiment or behavior. Avoid retaining unnecessary author identifiers or sensitive personal details.

## Access, installation and maintenance

The dedicated browser can automatically copy site-scoped cookies from a connected Chrome/OpenCLI session, including session cookies. It does not need the password to transfer an authenticated session. This does not match our default on-demand macOS Keychain credential workflow and must not run implicitly during plugin setup. Its own saved state/configuration is filesystem-based under ~/.agent-reach, with protective permissions and symlink checks in the inspected implementation.

Setup/add/update can install or update multiple dependencies and skills. The guide includes latest-release installation and shell bootstrap instructions. Several runtimes are pinned, but dependencies are not a fully locked single binary. Some channels require accounts or optional services/proxies/transcription providers; “zero API fees” is not a guarantee of zero total cost. Platform automation restrictions and maintenance remain operational risks. Upstream read-only instructions prohibit posting/liking/messaging and tell agents to stop at access or verification blocks; retain those boundaries if piloting.

## SkillForge result

The installed SkillForge 0.22.0 CLI scanned the packaged skill in quarantine against the existing 72-skill marketplace map. Candidate map overlap was low (top 0.06); the control scan self-matched the existing research skill at 0.976. The candidate entrypoint is Chinese and overlap is lexical, so the score alone is not evidence of a unique capability. Manual comparison found substantial overlap with existing web/GitHub retrieval, with bounded social-comment access as the main potential gap.

Safety verdict: **BLOCK**, one high `skillspector-unavailable` finding. The external scanner did not produce a complete accepted report. This is not a malware finding and not a clean safety result. The skill-subdirectory scan reported no license; the ancestor repository's MIT license was separately verified. No override or adoption occurred.

## Qualification before any adoption

1. Resolve the incomplete scanner report and review a pinned release/dependency set; do not install an unverified latest ZIP or the unrelated PyPI package.
2. Use an explicitly authorized isolated login/profile; prevent automatic copying of an existing main browser session. No credentials in prompts or shared plugin config.
3. Pilot one public Reddit query/post with a small cap. Verify body/comment distinction, URLs, timestamps, limits, access failures and no silent fallback around restrictions.
4. Repeat in Claude Code and Codex on an operator's Mac; verify the same command/output contract without claiming Tom acceptance from Jim's machine.
5. Compare the evidence gained with existing search tools. Add only a thin, read-only Rhize consumer-research skill if the gap and benefit are demonstrated. Keep upstream dependency maintenance upstream; do not replicate its platform/browser implementations.

Pinned references: [English README](https://github.com/Panniantong/Agent-Reach/blob/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284/docs/README_en.md), [Reddit adapter](https://github.com/Panniantong/Agent-Reach/blob/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284/agent_reach/channels/reddit.py), [session reuse](https://github.com/Panniantong/Agent-Reach/blob/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284/agent_reach/runtime/session_reuse.py), [package metadata](https://github.com/Panniantong/Agent-Reach/blob/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284/pyproject.toml), [license](https://github.com/Panniantong/Agent-Reach/blob/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284/LICENSE).
