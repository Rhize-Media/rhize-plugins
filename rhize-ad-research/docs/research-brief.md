# Shared research briefs

Invoke `/rhize-ad-research:brief` in Claude Code or `$rhize-research-brief` in Codex. Ask the assistant for a bounded cited brief, e.g. customer objections, content planning, competitor positioning, product questions, technical comparisons or emerging-topic investigation. The host uses its existing approved retrieval tools; Meta ad collection still uses the original protocol. This is a shared evidence workflow, not an Agent Reach integration.

No new account or credentials are needed for public sources. Access failures remain unavailable; there is no browser, bridge, cookie, login or fallback provider in the validator. An arbitrary host with shell/MCP access is not sandboxed by this skill. Keep privileges minimal. The command's tool list is a host convenience, not an OS security boundary.

## Evidence contract

The assistant prepares JSON, validates it and saves the selected output in your chosen private directory. The input is capped at 256 KiB; at most 20 sources, 10 findings and 10 queries. No dependency install is required: Python 3.11+ standard library only.

```json
{
  "schema": 1,
  "run_id": "ab1b7ea2-df19-42d3-b544-b810e5653fc7",
  "host": "codex",
  "purpose": "customer",
  "question": "What concerns should our detailing FAQ address?",
  "queries": ["professional detailing customer concerns"],
  "window": {"start": "2025-11-16", "end": "2026-11-16"},
  "captured_at": "2026-11-17T01:00:00Z",
  "capture_method": "host_transcribed",
  "sources": [{
    "id": "source1",
    "provider": "native-web",
    "url": "https://example.com/discussion",
    "title": "Replace with the observed source title",
    "published_at": null,
    "status": "unavailable",
    "summary": null,
    "coverage": "Illustrative schema only; not collected evidence."
  }],
  "findings": [],
  "limitations": ["Illustrative envelope. Collect real evidence before drawing conclusions."]
}
```

Allowed purpose: customer/content/competitive/product/technical/topics. Providers: native-web/public-http/official-mcp/agent-reach-public. These identify the host-asserted acquisition path; they do not authenticate it. Full upstream agent-reach, browser/opencli and all unknown providers are rejected; agent-reach-public refers only to the shipped qualified adapter. A host cannot make unqualified execution safe by relabeling a provider.

Each retrieved source needs a summary and coverage explanation. An unavailable source has null summary and cannot support a finding. A finding has exactly claim and source_ids; each reference must resolve to retrieved evidence. Published dates may be null. The requested window does not assert that all results fall inside it: exclude clearly out-of-window consumer observations, disclose uncertain dates and separate timeless primary references. Do not infer a date from an unreliable relative label. Never interpret timestamps in this envelope as proof of retrieval.

URLs must be canonical HTTPS without userinfo, query strings, fragments or explicit ports. Known private IPs/local hostnames are rejected. This is lexical validation, not DNS or SSRF enforcement: the CLI never fetches URLs. For existing web tools, use only public source URLs and never transmit confidential client identifiers. Proxy redirect behavior is not locally attested.

```sh
python3 -I "/absolute/plugin/scripts/research_brief.py" "/private/task/evidence.json" --format markdown
python3 -I "/absolute/plugin/scripts/research_brief.py" "/private/task/evidence.json" --format json
python3 -I "/absolute/plugin/scripts/research_brief.py" "/private/task/evidence.json" --format csv
```

Output goes to stdout, errors are controlled JSON on stderr with exit 2. No files are created or updated by the CLI; the host saves output only to the selected task directory. Never place source text in a shell command. JSON preserves the full envelope; CSV exports source rows only; Markdown is a cited brief with limitations. The renderer neutralizes spreadsheet formula prefixes and escapes Markdown content, but is not a prompt-injection firewall. Common token patterns are refused; this is not comprehensive secret detection. Minimize content before capture.

Both hosts may render the same immutable input concurrently: no shared mutable state, credentials, sockets or session selection exist. The collector host/run ID stays unchanged when the other host exports. Use fresh UUIDs for new research; never merge different tasks silently. Keep raw research outside the synced vault; summaries/citations may go to Obsidian. Proposed retention is seven days for raw pilot material, subject to explicit task requirements; this CLI does not delete files automatically.

## Tom's acceptance

Update/install the marketplace plugin in each host and restart after installed changes. Use the two invocations above; no Meta access is required for a public research brief. Meta ad collection still needs its documented roles/scopes. Ask the assistant to collect two public sources, keep one intentionally unavailable source, and export all three formats. Check citations against actual tool results, verify missing dates stay null, and render the same file from the other host without recollection. Verify agent-reach-public evidence renders, while arbitrary agent-reach/opencli provider labels still fail. Follow the separate public adapter qualification/setup guide before collecting; never install the full upstream package. Report host/plugin/Python versions, question, run ID, statuses, export results and any missing tool/access. Never send secrets or raw private sessions.

Offline CLI parity, a bounded native-host instruction check and Tom's own Mac acceptance are different evidence tiers. No telemetry or recurring collection is enabled.

Use canonical lowercase hosts without trailing dots, explicit ports or bare query/fragment delimiters. Numeric shorthand private addresses and Unicode control/format characters are rejected. Offline URL checks cannot detect DNS names that resolve privately. Do not strip a meaningful query from a source URL to force validation; obtain an equivalent canonical public permalink or record the limitation. Common credential-pattern detection can reject harmless technical prose: summarize without including credential-like examples, never weaken the validator to pass a secret. To save CLI output from a shell without clobbering an existing file, use a subshell with `set -o noclobber` and a literal, explicitly selected output path.

## Optional usage counters

Add `--host claude|codex` to identify the invoking renderer independently of the evidence collector. See [local usage telemetry](telemetry.md); capture is default-off, and a `rendered` outcome only verifies validation and stdout flush, not a saved file or accepted answer.
