# Task: three independent read-only findings

Inspect the three independent evidence surfaces under `workspace/` and write
`workspace/submission.json` with exactly these keys:

- `active_accounts`: count active accounts in `data/accounts.json`;
- `production_endpoint`: the production endpoint in `config/runtime.json`;
- `fourth_retry_seconds`: the delay returned by the fourth call to the retry schedule in
  `src/retry.py`.

Do not modify any existing workspace file. Parallel agents are explicitly authorized when useful.
At most two nested agents may run concurrently; the coordinator may handle a third lane.
