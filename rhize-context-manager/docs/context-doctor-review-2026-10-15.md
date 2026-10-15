# Optional doctor coverage review — October 15, 2026

Owner: context-manager-maintainers. Reviewed under Jim's explicit instruction to
repair Weekly Context Doctor, including expired probe reviews. Next review:
November 15, 2026, 00:00 UTC. This supersedes the October 11 review deadlines in
`scripts/context-doctor.config.json`; it does not change required coverage.

| Probe | Evidence and decision |
|---|---|
| OpenWolf | The canonical plugins checkout has no `.wolf` configuration. Retain optional `NOT_RUN / not_configured`; do not install or initialize another tool to make a health check pass. |
| Memory adapters | The existing adapters expose bounded recall/preview contracts. The deterministic doctor has no supported combined health measurement for them. Retain explicit `NOT_RUN / supported_read_contract_unavailable`; adapter availability is not measured recall quality or end-to-end health. |
| Harness audit | A host-invoked audit is not exercised by the deterministic read-only doctor. Retain `NOT_RUN / host_skill_not_exercised`; no model execution or delegation is added to the weekly check. |

All five required checks stay required with unchanged freshness, expiry and
runtime limits. Expired optional reviews still reject configuration. The new
configuration regression reproduces that rejection before this review renewal;
the existing expired-config test remains in place.

The previous `claude_mem / capture_errors_recorded` finding was separately
investigated from current observer health, read-only SQLite aggregate counts and
timestamped worker logs. October 8–9 failures were provider `seven_day` quota
exhaustion; buffered work was preserved. On October 15, the observer reports zero
consecutive failures and a successful capture on October 14. The last seven days
contain persisted observations, and the current capture probe returns OK. No
telemetry reset, database edit, provider fallback or threshold change is needed.
A fixture verifies recovery while retaining the historical quota error, and
verifies that an active failure still returns PROBLEM.

The same diagnostic found an independently expiring Claude refresh credential.
Supported sign-in completed October15; the unchanged expiry check now passes,
with refresh expiry November12. The existing eight-day warning is preserved.
Source review/test success is distinct from the new captured doctor run and
exact Sentry check-in readback.
