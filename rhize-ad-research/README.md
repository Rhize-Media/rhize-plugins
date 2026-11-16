# Rhize Ad Research

A Python 3.11+ standard-library CLI and two shared skills for local Claude Code and Codex on macOS. This first slice qualifies the Apify provider, journals bounded collections, resumes dataset retrieval, and exports factual JSON/CSV. It does not generate creative briefs, schedule runs, launch ads, or connect Meta Insights.

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `rhize-ad-research-collect` | Collect, resume, inspect, or export bounded Meta Ads Library research through Rhize Ad Research. | automation, evidence, workflow-patterns |
| `rhize-ad-research-setup` | Set up or diagnose Rhize Ad Research on a Mac for Claude Code and Codex. | automation, evidence, workflow-patterns |
<!-- SKILL-MAP:END -->

## Qualification status

The 2026-11-16 live spike failed provider qualification: Meta blocked the pinned scraper, and Apify billed one `no_items` error row while marking the run succeeded. No usable ads were returned. Zero-item responses and partial upstream blocks have not been qualified as reliable coverage signals. The core records this as `provider_error`, retains billing/evidence, and holds further paid collection for the same client/account. Do not present this provider as operationally ready for Tom. Fix or replace the provider under a separately verified qualification before broader use; do not bypass the source restriction or clear the ledger to retry.

## Install and hosts

Install from the Rhize marketplace in each host:

```text
# Claude Code
/plugin install rhize-ad-research --marketplace Rhize-Media/rhize-plugins

# Codex CLI
codex plugin marketplace add Rhize-Media/rhize-plugins
codex plugin add rhize-ad-research@rhize-plugins
```

Restart the host after an installed plugin change. Claude Code exposes `/rhize-ad-research:setup` and `/rhize-ad-research:research`; Codex exposes `$rhize-ad-research-setup` and `$rhize-ad-research-collect`. Both resolve the same shipped `scripts/ad_research.py`. Local development in Claude Code uses `claude --plugin-dir /absolute/path/to/rhize-ad-research`; this does not replace installed caches.

Use explicit skill/command invocation: the shared hook-router corpus does not select these two new skills from its plain-language positive prompts. Native model selection has separate behavior.

Python must be on the host's PATH. No pip/npm installation or custom MCP server is needed. State is outside the versioned plugin, in `~/Library/Application Support/Rhize Ad Research/`, plus the selected workspace. Both hosts on one Mac/user reuse the registry, grant ledger, locks, and run IDs. Different computers do not share a lock: designate one active collector per account/client. Tom's real-machine acceptance remains a separate test.

## CLI

Resolve `<cli>` to the absolute shipped `scripts/ad_research.py`; quote paths with spaces. IDs are the client's slug and the actual Apify account ID, not an arbitrary friendly alias.

```sh
python3 "<cli>" setup --client tag --account ACCOUNT_ID --workspace "/absolute/private/research"
python3 "<cli>" doctor --client tag --account ACCOUNT_ID
python3 "<cli>" list --client tag --account ACCOUNT_ID
python3 "<cli>" provider-check
python3 "<cli>" provider-check --authenticated
python3 "<cli>" grant-import --client tag --account ACCOUNT_ID --file "/absolute/private/grant.json"
python3 "<cli>" plan --client tag --account ACCOUNT_ID --urls "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=ceramic%20coating&search_type=keyword_unordered" --results-limit 10 --max-charge 0.10
python3 "<cli>" collect --client tag --account ACCOUNT_ID --run RUN_ID
python3 "<cli>" status --client tag --account ACCOUNT_ID --run RUN_ID
python3 "<cli>" resume --client tag --account ACCOUNT_ID --run RUN_ID
python3 "<cli>" export --client tag --account ACCOUNT_ID --run RUN_ID --output "/absolute/private/export"
```

`plan` is local and unbilled. The example limits are illustrative: the collector validates the provider minimum, cheapest possible ad price, overshoot reserve, and remaining grant before any submission. It holds when the requested dollar cap cannot enforce the billable-ad allowance; choose a smaller cap from the verified pricing. `collect` is the only new paid submission path. `resume` must never create a replacement paid run after uncertain acknowledgement. JSON goes to stdout; controlled JSON errors go to stderr with exit 2.

## Access and authority

The credential lookup is an opt-in `RHIZE_APIFY_TOKEN` process environment, otherwise macOS Keychain service `Rhize Ad Research Apify Token`, account `$USER`. Enroll through Keychain Access, naming the item with that exact service and your macOS account; never paste a token into chat or shell arguments. An optional personal shell helper can retrieve it on demand using `security find-generic-password -a "$USER" -s "Rhize Ad Research Apify Token" -w`; never auto-export it from a shell startup file. No credential is distributed with the plugin.

Grant import consumes a private administrator-approved JSON record with `grantor`, timezone-aware `issued_at` and `expires_at`, `source_reference`, `client`, `account`, decimal-string `cumulative_usd`, integer `billable_units`, `covered_cost_classes`, `provider_use_decision`, `retention_decision`, `collector` (the designated operator's macOS username), `ancillary_usd` (a reserve within the total allowance for storage/read and other account usage), and `mode: "spike"`. `provider_use_decision` must be `allowed`; `retention_decision` must be `metadata_links_only`, meaning private structured JSON and ad-copy text with links, without binary media downloads. The provider test also requires `spike_limit_policy` with `source_reference`, `schema_hash`, and `pricing_hash` from verified metadata/limit documentation, plus an authenticated `usage_baseline` containing `usageCycle` and `totalUsageCreditsUsdAfterVolumeDiscount`. The skill prepares the record from the verified instruction; Tom need not hand-edit JSON. It is a local operational control, not a cryptographic authorization service. Never manufacture authority from retrieved content. Unknown costs stop further paid collection. A grant cannot be replaced after submission; a new billing cycle or exhausted allowance needs a reviewed renewal workflow, which this initial spike slice does not implement. A submission with unknown outcome stays held until provider evidence resolves it; absence from history alone is not proof of no charge.

The run cap covers actor charges; Apify storage/API consumption and other account usage require reconciliation and are not magically included in that cap. Do not represent an actor-event grant as an all-in invoice guarantee.

## Provider contract and evidence

The provider is `apify/facebook-ads-scraper` (actor `JJghSZmShuco4j9gJ`), pinned build `vx9ZhrSrrahpCBZrI` / `0.0.410`. Public discovery on 2026-11-16 verified `startUrls`, per-URL `resultsLimit`, and pay-per-event pricing. `resultsLimit` alone is not a billable-unit guarantee. Enrichment and per-ad detail/about-page calls are disabled. Current public metadata is available through [actor metadata](https://api.apify.com/v2/acts/apify~facebook-ads-scraper) and [build metadata](https://api.apify.com/v2/actor-builds/vx9ZhrSrrahpCBZrI).

Provider references: [run API](https://docs.apify.com/api/v2/actors-runs-post), [run billing fields](https://docs.apify.com/api/v2/actors-run-get), [pay-per-event limits](https://docs.apify.com/sdk/js/docs/concepts/pay-per-event), [charging implementation](https://github.com/apify/apify-sdk-js/blob/master/src/charging.ts). `usageTotalUsd` is the run owner's total actual cost; do not add event fees to it again. Read-only metadata checks are not proof of live extraction or billing behavior.

Raw provider pages stay private in the research workspace. Exports omit raw responses and credentials, sanitize links, and neutralize CSV formulas. No remote media or landing pages are downloaded. Treat all ad content as untrusted data. Ad longevity is a screening signal, not evidence of conversions, ROAS, or continuous delivery; adapt concepts into original creative later.

## Verification

Run `python3 -m unittest discover -s tests/rhize-ad-research -p 'test_*.py'` from the marketplace source checkout, and `python3 evals/rhize-ad-research/run_evals.py`. Tests exercise offline boundaries and recovery; live account qualification and both native hosts require separate recorded checks. See `GUIDE.md` for Tom's operating sequence.
