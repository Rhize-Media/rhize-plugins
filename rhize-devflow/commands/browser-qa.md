---
description: Scenario-driven browser acceptance check — functional path, console/network errors, accessibility smoke, responsive layout, and performance on request — against whichever browser tool is actually available
---
<!-- canonical: rhize-devflow:browser-qa -->

# Browser QA

`scripts/typed_selection.py --mode advise` can recommend one already legal, approved
test-surface scenario (or `none`) from bounded metadata and current evidence. The registry
decides whether the line is shown (shadow until earned); the scenario and browser authority
stay in this command, and the advisory line never changes obligations, approvals or required
checks. See [the typed selection contract](../docs/typed-checkpoint.md).

One scenario-driven acceptance workflow, replacing the former `browser-help` /
`browser-debug` / `browser-perf` / `browser-test` split. It sequences *what* to verify;
the mechanics of *how* to drive a browser belong to whichever browser tool is actually
connected in this session.

## Core Contract

- **Detect, don't assume.** Before running any scenario, determine which browser
  capability is actually available in this session — do not assume a specific named MCP
  implementation is installed. Candidates, in no fixed preference order: the Claude Browser
  pane MCP, a `chrome-devtools` MCP server, `claude-in-chrome`, a Playwright MCP server, or
  an equivalent already connected. Also discover an enabled `playwright-cli` skill and its
  CLI when an isolated CLI browser suits the task. Prefer a sufficient available native
  connector when appropriate. Check actual tools/CLI help, not guessed package dependencies.
  Capability may be partial: report unavailable console, network or performance scenarios.
  Never install a browser, enable a disabled skill or bypass native trust as a probe.
- **Degrade explicitly.** If no browser capability is available, say so plainly and stop —
  never fabricate results, never silently skip scenarios while reporting success. Report
  exactly which scenarios could and could not run.
- **Defer mechanics to the active tool's own skill.** Once a capability is identified, use
  that tool's own navigation/click/screenshot/network/console primitives (see its skill,
  e.g. `chrome-devtools-mcp` in this plugin, or the browser tool's own documentation) —
  this command does not re-specify tool-call syntax.
- **Rhize acceptance sequencing stays fixed** regardless of which tool is driving it: the
  scenario list and pass/fail criteria below are the contract; the tool is an implementation
  detail.

## Scenarios

Run in order. Skip a scenario only when it is genuinely not relevant to the change under
test (e.g. no layout change → responsive layout is optional, not skipped by default), and
say so explicitly rather than omitting it silently.

### 1. Functional path

Navigate the primary user flow under test end to end (page load, key interaction, expected
result). Report what was exercised and whether it reached the expected end state.
Exercise affected loading, empty, error, success and permission states. For async controls,
check handler re-entry protection, visible pending feedback on a mounted control, guard cleanup
and failure recovery; a disabled attribute alone does not establish duplicate-request protection.

### 2. Console and network errors

Capture console messages and network requests during the functional path. Flag:
- Any console error or uncaught exception.
- Any failed request (4xx/5xx) relevant to the flow.
- CORS failures.

A clean run reports "no errors observed," not silence.

### 3. Accessibility smoke

Take an accessibility snapshot (or equivalent structural read) of the primary view and
check for the basics: interactive elements have accessible names, form inputs have
associated labels, and there is no obviously broken heading/landmark structure. This is a
smoke check, not a full WCAG audit — name it as such. Exercise affected keyboard navigation,
visible focus, focus restoration and reduced-motion behavior (`prefers-reduced-motion`).
Use a deeper accessibility specialist when the task requires it; record checks that cannot run.

### 4. Responsive layout

Check the primary view at mobile, tablet, and desktop breakpoints (see viewport presets
below). Flag horizontal overflow, truncated/overlapping content, or unusable touch targets.
For visible changes, capture and inspect screenshots of the affected views/states. Compare
against the established design direction and real content, not a generic aesthetic. Use the
`frontend-development` skill for conditional craft/motion review; keep the existing brand authoritative.

### 5. Performance (on request or when relevant)

Only run when the user asks for it, or the change plausibly affects load/render
performance (new heavy asset, new client-side data fetch, layout change on a
performance-sensitive page). Do not run this scenario by default. Report LCP, INP and CLS
only when the active tool actually measures them; do not substitute FID for INP. Good field
thresholds are LCP ≤2.5s, INP ≤200ms and CLS ≤0.1 at the 75th percentile, segmented by device.
Label local traces as lab observations, not field compliance. Missing metrics stay unmeasured.
See [Web Vitals](https://web.dev/articles/vitals) for current definitions.

## Viewport Presets

| Device | Width | Height |
|--------|-------|--------|
| Mobile | 375 | 667 |
| Tablet | 768 | 1024 |
| Desktop | 1440 | 900 |

## Reporting

Report one result per scenario that actually ran (pass / issues found / skipped-with-reason),
then one overall summary. Never report a scenario as passed if it could not run for lack of
browser capability — report it as unavailable instead.

Bind each observed result to the URL/build, viewport, state and action, with the expected and
observed outcome and a screenshot/trace reference where relevant. Name screenshots actually
inspected. Separate static checks, browser observations and remaining human acceptance.

## Safety

- No commit, push, PR, or deploy. This command only observes and reports.
- Never submit a form to a real service, click a destructive action, or enter real credentials
  without established task authorization. Use repository test-account conventions. Test data
  alone is not permission for external writes; an authorized inert local fixture is suitable
  for submission/re-entry checks.

## Related Workflows

- `chrome-devtools-mcp` (this plugin) — DevTools-protocol mechanics when that server is the
  active capability.
- `/rhize-devflow:check` — non-browser test/lint/typecheck gate; run alongside this command
  for full mid-implementation coverage.
- `/rhize-devflow:review` — production merge/release gate.
