# Rhize Outreach

Internal Claude/Codex plugin for a local, review-gated prospecting and deliverables workflow. It helps find businesses with concrete website/search opportunities, review evidence, and prepare a website concept, public-facing audit, and outreach email draft.

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `reconcile-outreach-delivery` | Explain the current email delivery boundary for Rhize Outreach and identify when a reviewed draft is ready for a separately configured send… | data-consistency, outreach |
| `review-outreach-businesses` | Review researched candidate businesses or add a manually found business before selecting one for deliverables. | outreach, prospecting |
| `review-outreach-email` | Open, revise and accept the personalized outreach email bound to the accepted website and audit package. | content-authoring, outreach, review |
| `review-outreach-package` | Run and review the selected prospect's 2–3-page website concept and public audit, including skill-backed design, conversion, SEO and render… | outreach, review, seo-audit, visualization |
| `rhize-outreach-doctor` | Diagnose local Rhize Outreach setup, runtime pin, private data directories, Codex CLI sign-in, and operator UI health without changing stat… | automation, observability |
| `rhize-outreach-run` | Start the local Rhize Outreach operator and resume the selected-business agent graph. | automation, workflow-patterns |
| `rhize-outreach-setup` | Set up or resume the local Rhize Outreach selected-business workflow. | automation, workflow-patterns |
<!-- SKILL-MAP:END -->

## Setup

Install the plugin from the Rhize Plugins marketplace, then run `/rhize-outreach:setup`. The three-step loopback wizard checks macOS, Node.js 24.12+, Git, npm, local PostgreSQL binaries, and a signed-in Codex CLI. It fetches the exact runtime commit pinned in `setup/manifest.json`, runs `npm ci`, and stores local state under `~/Library/Application Support/Rhize Outreach/`. Setup does not ask for or store provider credentials.

The runtime revision currently pinned is `c8778dda0bba65380bee5d8a7bf99e214a8b22fa`. Setup uses a private local PostgreSQL cluster and artifacts outside the source checkout. This app does not use Rhize-Scan's Supabase project.

## Use

- `/rhize-outreach:doctor` checks the runtime pin, prerequisites, private data directories, and loopback UI.
- `/rhize-outreach:run` starts the local server in the foreground and opens its authenticated UI in the default browser. Keep the terminal open; Ctrl-C stops the service.
- Select a candidate in the UI to start or resume the selected-business graph. Human review holds remain in place before email drafting and before final email acceptance.

## Workflow and limits

The local Codex graph handles research, brief, 2–3 connected website pages, a review/repair loop (maximum two automatic repairs), public audit, and—after package acceptance—an email draft. It stops at the package-review and email-review checkpoints. Candidate selection and paid discovery remain explicit operator actions. It never sends email or publishes a website.

The current background Codex executor has no browser, MCP, shell, or installed external skill-command access. It cannot run the UI/UX Pro Max design-system CLI or provide rendered-page browser evidence; that limitation stays visible and requires an actual human/tool-equipped review before claiming the site was visually verified. The current runtime has no GHL, Gmail/Workspace, Resend, Vercel publishing, or shared Supabase adapter. Do not provide credentials for these services to this plugin.

## Files and support

- `assets/setup-wizard.html` is served only on loopback with a random, per-run token and same-origin checks.
- `setup/manifest.json` is the dependency, source-pin, wizard, doctor, and local artifact inventory.
- `scripts/rhize-outreach.mjs` serves the setup wizard, performs pinned setup, read-only health checks, and safe foreground launch.
- `skills/` contains the host-invocable setup, doctor, and run instructions.

No setup or doctor output includes the authenticated session URL or provider credentials. The local session URL is opened in the default browser and should be treated as sensitive.
