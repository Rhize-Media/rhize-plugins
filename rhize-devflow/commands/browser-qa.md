---
description: Scenario-driven browser acceptance check — functional path, console/network errors, accessibility smoke, responsive layout, and performance on request — against whichever browser tool is actually available
---
<!-- canonical: rhize-devflow:browser-qa -->

# Browser QA

One scenario-driven acceptance workflow, replacing the former `browser-help` /
`browser-debug` / `browser-perf` / `browser-test` split. It sequences *what* to verify;
the mechanics of *how* to drive a browser belong to whichever browser tool is actually
connected in this session.

## Core Contract

- **Detect, don't assume.** Before running any scenario, determine which browser
  capability is actually available in this session — do not assume a specific named MCP
  implementation is installed. Candidates, in no fixed preference order: the Claude Browser
  pane MCP, a `chrome-devtools` MCP server, `claude-in-chrome`, a Playwright MCP server, or
  an equivalent already connected. Probe by checking which of that family's tools are
  present, not by guessing from the project's `package.json`.
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
smoke check, not a full WCAG audit — name it as such.

### 4. Responsive layout

Check the primary view at mobile, tablet, and desktop breakpoints (see viewport presets
below). Flag horizontal overflow, truncated/overlapping content, or unusable touch targets.

### 5. Performance (on request or when relevant)

Only run when the user asks for it, or the change plausibly affects load/render
performance (new heavy asset, new client-side data fetch, layout change on a
performance-sensitive page). Capture Core Web Vitals (LCP, INP/FID, CLS) via the active
tool's performance-trace primitives and flag anything past standard thresholds (LCP >
2.5s, CLS > 0.1). Do not run this scenario by default — it is the slowest and least
frequently relevant.

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

## Safety

- No commit, push, PR, or deploy. This command only observes and reports.
- Never submit a form, click a destructive action, or enter real credentials while
  exercising a flow — use test data only, per the repository's own test-account
  conventions.

## Related Workflows

- `chrome-devtools-mcp` (this plugin) — DevTools-protocol mechanics when that server is the
  active capability.
- `/rhize-devflow:check` — non-browser test/lint/typecheck gate; run alongside this command
  for full mid-implementation coverage.
- `/rhize-devflow:review` — production merge/release gate.
