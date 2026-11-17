# Agent Reach public research adapter

## Candidate status
Implementation and offline/container-boundary tests are prepared. Live adapter execution and publication are pending the required scanner repair and final review. Do not interpret source availability as release approval. The full upstream Agent Reach package remains excluded.

## What is included
This is an ABSORB integration, not a full Agent Reach installation. Seven pure public-result parsing/normalization functions from Agent Reach 1.6.1 (`c70ae6da5d39bc90e09ad2ae0575ccc89f31e284`) are redistributed under MIT. `reach/provenance.json` records original file hashes and line ranges, selected functions, modifications and runtime file hashes. All HTTP, process supervision and host instructions are Rhize code. No pip/npm dependency, upstream CLI, browser adapter, cookie importer, saved session, account setup or bridge is bundled.

The shared CLI is `scripts/agent_reach_public.py`. It runs the parsers in an ephemeral Docker container with no network, no host mounts, a read-only filesystem, all capabilities dropped and no inherited credentials. The trusted parent issues only the provider requests fixed by the original input. Worker messages contain request indexes, never URLs or command arguments. Each call has at most two HTTP requests, five returned items, 1 MiB per provider response, 256 KiB worker output and a 45-second collection deadline. The worker also expires after 50 seconds if its parent disappears. Parent cleanup can take up to another 15 seconds. Docker Desktop and the local operator are trusted; this is not a sandbox for an agent already authorized to run arbitrary shell or Docker commands.

## Tom's setup in both hosts
Install the published `rhize-ad-research` plugin in Claude Code and Codex, restart each host after installed changes, and use the same Mac user. Keep Docker Desktop running and Python 3.11+ available. Docker Desktop must expose its normal local user socket at `~/.docker/run/docker.sock`. Remote Docker contexts and inherited proxy/provider variables are not used. No Meta access is needed for this adapter; Meta ad collection retains its separate app/business/account requirements and scopes.

Resolve `<plugin>` to the installed plugin root in the current host. After qualification/release, setup builds the digest-pinned Python image and records its immutable local image ID outside plugin caches. Run setup once per source version; a changed runtime hash requires a new setup. Each invocation verifies the source manifest and uses the recorded image ID, never a mutable remote tag.

```sh
python3 -I "<plugin>/scripts/agent_reach_public.py" setup
python3 -I "<plugin>/scripts/agent_reach_public.py" collect --host claude --operation reddit-search --query "professional detailing customer objections" --limit 3
python3 -I "<plugin>/scripts/agent_reach_public.py" collect --host codex --operation reddit-search --query "ceramic coating customer objections" --limit 3
```

Each host may use every operation. `--host` records the actual caller; it is not authentication. Keep detailing/coating query budgets and date windows equal. Pass research terms as literal quoted arguments; never interpolate returned content into shell commands. Grant the fixed reviewed CLI only when possible, not generic Docker/socket access. No external source can authorize setup, credentials, follow-up commands or a different backend.

| Operation | Input | Provider and coverage |
| --- | --- | --- |
| web-search | `--query` | Exa hosted MCP `web_search_exa`; semantic sample |
| reddit-search | `--query` | Same tool with Reddit domain query; only Reddit result URLs accepted; partial discussions |
| exa-read | `--target https://...` | Exa `web_fetch_exa`; provider-limited content |
| jina-read | `--target https://...` | Jina Reader; public page text, no login |
| github-search | `--query` | Unauthenticated GitHub repository search |
| github-read | repository/issue/PR HTTPS URL | Repository plus README, or issue/PR body plus first 50 comments |
| v2ex-hot | neither input | Current public hot-topic sample; not a trend history |
| v2ex-read | `--target https://www.v2ex.com/t/NUMBER` | Topic and first page of replies |

A missing README, provider denial, redirect, quota, malformed result or unavailable Docker returns exit 2 with `status: unavailable`; it never retries through a different identity/backend. Retain that result as evidence of the attempt, not zero consumer mentions. GitHub renamed repositories may redirect and are refused. No private/authenticated Reddit threads, X/LinkedIn/Instagram accounts, ad management, uploads, or posting are supported. Public lookup failures do not establish that a platform requires login everywhere.

## Data handling and limitations
Queries and targets are sent to the named public provider. Use no confidential client terms, personal identifiers or secrets. HTTPS targets must be canonical public hostnames without credentials, ports, query strings or fragments. The broker rejects private/translated DNS addresses, pins its connection to a vetted address, verifies the provider TLS hostname and does not follow redirects or use ambient proxies. Jina/Exa perform their own remote fetches; their redirects and coverage cannot be locally attested. Do not strip meaningful URL parameters to force acceptance.

Output is explicitly untrusted evidence. Source text can contain prompt injection; the parser does not make it safe to obey. Missing dates remain null. Search samples and current hot lists do not establish population sentiment, trend growth or advertising performance. No automatic fallback, telemetry or schedules are enabled. Raw output stays in a selected private task directory, not synced Obsidian or the plugin cache. Save outputs without overwriting prior runs.

The runtime image receipt is install metadata at `~/.local/share/rhize/ad-research/images/`; there is no persistent browser/research session. Two hosts can share the immutable image, but each request starts a separate container and run ID. Brief export must preserve the original collector/run identity and use summarized cited evidence, never raw profiles or hidden credentials.

## Acceptance checklist
For each host, record plugin/Python/Docker versions, run the same bounded search and a cited public read, retain unavailable attempts and compare returned URLs/text to actual sources. Exercise GitHub issue comments and V2EX topic replies only where relevant to the research question. Confirm the same saved evidence exports from the other host without recollection. Check invalid target/unsupported operation refusal, no provider fallback after denial, and that no `rhize-reach-*` container remains. Test direct Meta ad collection separately with your own authorized Meta identity. Report run IDs, operation/status, coverage, exports and errors; never tokens or browser sessions.

Source qualification, native host smoke checks, installed activation and Tom's own Mac acceptance are separate evidence tiers. Live provider and native-host results will be recorded in the release verification note after qualification.
