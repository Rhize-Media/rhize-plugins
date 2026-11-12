# Context doctor: login-expiry notice and optional review renewal

Authorized 2026-11-12 by Jim: the recurring sign-in expiry failure is not his design choice;
"work through any other issues that need it". Sentry issue SEO-HEALTH-INFRA-8.

## Current behavior and evidence

- `credential_expiry` returns `PROBLEM / refresh_credential_expiring` when the Claude Code
  sign-in ends within 8 days (`context_doctor_probes.py:63`). Any PROBLEM sends an `error`
  Sentry check-in. Run `788a1f3c` (2026-11-12) failed for this reason alone, with 170 h left.
- The sign-in lifetime is fixed by the provider from the moment of sign-in. Eleven doctor
  reports since September show `refreshTokenExpiresAt` constant across access-token refreshes;
  the longest remaining time seen is 675 h. It is not documented and not configurable.
  With an 8-day rule and a weekly run, the monitor fails in every sign-in cycle.
- The three optional probes have `review_by: 2026-11-15T00:00:00Z`. `validate_config` refuses
  an expired review, so the 2026-11-19 run would fail as it did on 2026-10-15 (run `7a9d9536`).
- The 2026-11-12 run shows the same three optional reasons as the October 15 review:
  `not_configured`, `supported_read_contract_unavailable`, `host_skill_not_exercised`.
- CodeGraph was not consulted; `rg` over scripts, tests and docs covers these edges.

## Intended semantic delta

- A sign-in that ends within 8 days is `OK / refresh_expiry_soon`: visible in the report table
  and delta, not a failed check-in.
- A sign-in that has already ended is `PROBLEM / refresh_credential_expired`.
- The same split for a non-refreshable credential: `expiry_soon` / `credential_expired`.
- Optional reviews renewed to 2027-02-15T00:00:00Z on unchanged evidence.

## Invariants and must-not-change boundaries

- All five required probes stay required. Blocked Keychain access stays `NOT_RUN /
  blocked_credential`. Unknown refresh expiry stays `NOT_RUN / refresh_expiry_unknown`.
- Facts stay timestamps and hours only; no token material.
- Expired optional reviews still refuse configuration. No change to `context_doctor.py`,
  `context_doctor_monitor.py`, capture probes, thresholds for other probes, or check-in logic.
- The doctor never refreshes or stores credentials.

## Current structural touchpoints

| Path | Role |
|---|---|
| `rhize-context-manager/scripts/context_doctor_probes.py` | `credential_expiry` |
| `rhize-context-manager/scripts/context-doctor.config.json` | optional `review_by` |
| `tests/rhize-context-manager/test_context_doctor.py` | regression tests (pinned by claude-routines) |
| `rhize-context-manager/docs/context-doctor.md` | behavior contract |

## Planned additions and deletions

- Add `rhize-context-manager/docs/context-doctor-review-2026-11-12.md`.
- Add tests for soon, expired and distant expiry, and for the November review window.
- Version bump (patch) through `scripts/bump_version.py`; rendered docs regenerated.
- No deletions.

## External and operational effects

- `claude-routines/scheduled/context-doctor-release.json` must pin the new hashes before the
  next weekly run; until then the launcher refuses with `release_digest_mismatch`.
- A later run with all required probes OK sends an `ok` check-in, which resolves the Sentry
  issue. The sign-in still ends 2026-11-19 15:11:57 UTC; Claude Code asks for `/login` then.

## Acceptance tests

- Probe unit tests: 7 days left gives `OK / refresh_expiry_soon`; past gives
  `PROBLEM / refresh_credential_expired`; 20 days gives `OK / refresh_expiry_measured`.
- Default config validates on 2026-11-19 and refuses on 2027-02-15.
- Full `tests/rhize-context-manager/test_context_doctor.py`, config lint, version checks.
- `run-context-doctor.py --check` passes with the new pin.

## Explicitly unaffected paths

Other plugins, hooks, workflow files, monitor configuration, Sentry monitor settings,
claude-mem, Keychain items and ACLs.

## Unknowns and confidence

High for the code change. The provider lifetime is inferred from local reports, not from
documentation. Whether a one-year `claude setup-token` token should feed claude-mem is a
separate decision for Jim and is not part of this change.

## Implemented touchpoints

- `rhize-context-manager/scripts/context_doctor_probes.py`: `credential_expiry` split into soon / ended.
- `rhize-context-manager/scripts/context-doctor.config.json`: three `review_by` dates to 2027-02-15.
- `tests/rhize-context-manager/test_context_doctor.py`: two tests added (36 pass).
- `rhize-context-manager/docs/context-doctor.md`, `rhize-context-manager/docs/context-doctor-review-2026-11-12.md` (new),
  `rhize-context-manager/README.md`, `rhize-context-manager/GUIDE.md`.
- Version 0.50.4 to 0.50.5 by `scripts/bump_version.py`: `.claude-plugin/marketplace.json`, `CHANGELOG.md`,
  `rhize-context-manager/CHANGELOG.md`, `rhize-context-manager/.claude-plugin/plugin.json`,
  `rhize-context-manager/.codex-plugin/plugin.json`; rendered `README.md`, `docs/README.md`.
- Checks: `bump_version.py --check` passed under Python 3.14 (938 Dev Flow tests, config lint, skill-map freshness).
  The default `python3` (3.15) has no pytest or PyYAML; that is a host fault, not part of this change.
- Not touched: `context_doctor.py`, `context_doctor_monitor.py`.

## Implementation order

1. Prepare receipt. 2. Probe and tests. 3. Config and review doc. 4. Docs, bump, render.
5. Tests and lint. 6. Reconcile, commit, push. 7. Re-pin in claude-routines and `--check`.
