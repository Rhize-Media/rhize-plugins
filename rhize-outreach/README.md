# Rhize Outreach

Internal Rhize plugin for running the researched prospect workflow from Claude Code or Codex.

The plugin controls the separate `Rhize-Media/rhize-outreach` runtime. It does not duplicate the runtime's database, research, report, website or delivery logic.

## Operator flow

1. Run setup once. The loopback wizard installs the pinned runtime, stores non-secret configuration under `~/Library/Application Support/Rhize Outreach/`, and writes secrets directly to macOS Keychain.
2. Choose an area and industry.
3. Review the researched candidate list or add a manually found business.
4. Select a business and review its 2–3-page website concept and public audit.
5. Review the personalized email.
6. Create a Gmail draft or prepare a GHL delivery intent. Sending remains a separate exact-message action.

## Commands

- `/rhize-outreach:setup`
- `/rhize-outreach:doctor`
- `/rhize-outreach:campaign`
- `/rhize-outreach:businesses`
- `/rhize-outreach:package`
- `/rhize-outreach:email`
- `/rhize-outreach:reconcile`

## Secret handling

The setup wizard accepts secret values only through its loopback form and stores them in Keychain. Config, doctor receipts, templates and generated handoff files contain secret names and readiness states only. The Supabase service-role key is never required on an operator workstation.

## Runtime pin and templates

`setup/manifest.json` is the runtime pin authority. `assets/templates/manifest.json` records the reviewed bundled template digests. Doctor refuses a mismatched runtime/template pair rather than silently running stale deliverables.

## Skill inventory

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `reconcile-outreach-delivery` | Reconcile Gmail or GHL draft/delivery intent state after an ambiguous, failed or manually completed action without duplicate contact. | automation, data-consistency, outreach |
| `review-outreach-businesses` | Review researched candidate businesses or add a manually found business before selecting one for deliverables. | outreach, prospecting |
| `review-outreach-email` | Open, revise and accept the personalized outreach email bound to the accepted website and audit package. | content-authoring, outreach, review |
| `review-outreach-package` | Run and review the selected prospect's 2–3-page website concept and public audit, including skill-backed design, conversion, SEO and render… | outreach, review, seo-audit, visualization |
| `rhize-outreach-doctor` | Diagnose the Rhize Outreach plugin, pinned runtime, templates, shared workspace and connector readiness without running discovery, publishi… | observability, outreach, postgresql, supabase |
| `rhize-outreach-setup` | Install or resume the seven-stage Rhize Outreach setup wizard on a Mac. | automation, outreach, postgresql, supabase, workflow-patterns |
| `run-outreach-campaign` | Start or resume the Rhize Outreach graph from market selection through a researched shortlist. | automation, outreach, postgresql, prospecting, supabase |
<!-- SKILL-MAP:END -->
