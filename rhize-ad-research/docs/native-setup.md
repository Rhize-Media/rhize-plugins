# Native Meta setup

Use Meta's official HTTP MCP endpoint `https://mcp.facebook.com/ads`, server name `meta-ads`. No plugin-owned token or OAuth proxy is needed. Use Rhize's existing approved app and each person's authorized login. The app needs the ADS_AGENTIC use case, `ads_mcp_management` and `ads_read`; MCP requires the management-named scope even for this read-only use. Do not add scopes or publish the app to clear access errors. Internal development-mode access requires the user's app/business role and at least one active ad account.

## Claude Code

Register through native `claude mcp add --scope user --transport http --client-id APP_ID --callback-port 8081 meta-ads https://mcp.facebook.com/ads`, then `claude mcp login meta-ads` in an interactive terminal. Preserve the generated OAuth state/PKCE/callback. Inspect requested scopes and approve only the two above; if the host requests more, stop authorization and correct its supported flow. Never copy OAuth tokens into configuration or chat.

The installed plugin's PreToolUse hook restricts tools on the dedicated `meta-ads` server to `ads_library_search`. Confirm the hook is trusted/active in `/hooks` before collection, then attempt a harmless non-search read such as ads_get_ad_accounts and verify the Rhize deny reason. Do not test with an actual mutation. A listed hook alone is not proof that its process can run. It does not grant permission to any call or restrict other unrelated servers. For bounded headless verification also use `--strict-mcp-config`, the existing native server entry, and `--allowedTools mcp__meta-ads__ads_library_search`; do not use bypass-permissions. The hook is needed because allowedTools grants preapproval, not an exclusive tool filter.

## Codex

Use native `codex mcp add meta-ads --url https://mcp.facebook.com/ads`. Merge the following into the existing server section in `~/.codex/config.toml`, preserving unrelated settings:

```toml
[mcp_servers.meta-ads]
url = "https://mcp.facebook.com/ads"
scopes = ["ads_mcp_management", "ads_read"]
enabled_tools = ["ads_library_search"]

[mcp_servers.meta-ads.oauth]
client_id = "APP_ID"
callback_url = "http://localhost:8080/callback/EXISTING_NATIVE_PATH"
```

Use the host-generated callback path and the app's registered redirect URI; the example is not a runnable callback. On the verified setup Meta rejected 127.0.0.1 but accepted localhost. Keep strict redirect/security settings enabled. Use `codex mcp login meta-ads --scopes ads_mcp_management,ads_read` after confirming your installed CLI help. Restart/reconnect to load the tool allowlist. Do not alter global ports or other server entries unnecessarily.

The native allowlist is the Codex boundary, including code-mode calls; do not rely solely on skill prose or a direct-tool hook. Confirm only library search is exposed in the fresh host. Claude's plugin guard applies only to the dedicated server names `meta-ads`/`meta_ads`; never create an alias to evade it.

## Shared workspace permissions

In Codex, open the chosen research workspace and also grant the registry directory as writable: `codex --add-dir "$HOME/Library/Application Support/Rhize Ad Research" -C "/absolute/private/research"`. For `codex exec`, use the same `--add-dir` with workspace-write. Create the registry through setup first if it does not exist. The first native acceptance retrieved/saved four ads but hit PermissionError at import because this directory was outside writable roots; resolve that permission and resume the SAME inbox/run without another query. Do not disable the sandbox. Claude can use `--add-dir` or its normal scoped file approval for the same directories.

## Acceptance and access failures

Run a small known-page search with the operator's own login; save actual tool evidence and compare it with the CLI export. An active account, app role, OAuth success and retrieval are separate checks. No raw credential is printed or stored by this plugin. If access fails, record the failure and diagnose the native connection; do not switch to a scraper or expand authorization. Tom's acceptance remains pending until performed on his own Mac/login.

Host references: [Claude MCP permissions](https://code.claude.com/docs/en/permissions#mcp), [Claude hooks](https://code.claude.com/docs/en/hooks#match-mcp-tools), [Codex MCP configuration](https://github.com/openai/codex/blob/main/codex-rs/config/src/types.rs).
