# Optional doctor coverage review — November 12, 2026

Owner: context-manager-maintainers. Reviewed under Jim's instruction of November 12 to fix the
recurring sign-in expiry failure and work through the remaining Weekly Context Doctor issues
(Sentry SEO-HEALTH-INFRA-8). Next review: February 15, 2027, 00:00 UTC. This supersedes the
October 15 review deadlines in `scripts/context-doctor.config.json`.

## Optional probes

Run `788a1f3c-26ef-4764-9bb7-ec294e324eea` (November 12) reports the same three reasons as the
October 15 review. Nothing was installed or initialized to change them.

| Probe | Evidence and decision |
|---|---|
| OpenWolf | `NOT_RUN / not_configured`. The canonical plugins checkout still has no `.wolf` configuration. Retain. |
| Memory adapters | `NOT_RUN / supported_read_contract_unavailable`. The doctor still has no supported combined health measurement. Retain. |
| Harness audit | `NOT_RUN / host_skill_not_exercised`. The deterministic read-only doctor still does not invoke a host skill. Retain. |

The review window is three months, not one. The one-month window expired between two weekly
runs twice (October 15, and November 15 if left alone) and failed the monitor on a date, not on
a change in the probes. Expired optional reviews still reject configuration.

## Sign-in expiry

The October 15 review preserved an eight-day warning as `PROBLEM`. That is changed here.

- Evidence: eleven doctor reports from September 11 to November 12 show
  `refreshTokenExpiresAt` fixed across access-token refreshes. It moves only after a new
  sign-in. The longest remaining time recorded is 675 hours. The lifetime is set by the
  provider; it is not documented and cannot be configured or extended locally.
- Effect of the old rule: with a weekly run, every sign-in cycle produced at least one failed
  check-in although nothing was broken. November 12 failed for this reason alone, with
  170 hours left.
- New rule: within eight days of the end is `OK / refresh_expiry_soon`. The reason and the
  hours remaining stay in the report and its delta. After the end it is
  `PROBLEM / refresh_credential_expired`. The probe stays required.
- What still detects a real fault: an ended sign-in fails this probe, and a capture writer that
  cannot authenticate fails `claude_mem` with `capture_auth_invalid`.

## November 5 missed check-in

Not a credential expiry. The claude-mem worker log records
`macOS keychain lookup failed {service=Claude Code-credentials}` from 11:39 UTC, and the
13:06 UTC doctor run could read neither the Claude credential nor the monitor credential.
The Keychain was unreadable to background processes on the host for that period. The cause on
the host is not established. No Keychain access setting was changed.

Source review and test success are distinct from a new captured doctor run and the Sentry
check-in readback.
