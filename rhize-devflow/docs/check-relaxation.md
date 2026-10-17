# Check relaxation (S4)

`scripts/check_plan.py` lets `/rhize-devflow:check` run fewer routine checks on a low-risk diff. The
decision is deterministic and fails closed: Laya (decision `check-relaxation`) chooses between the full list and
the deterministic relaxed list, and nothing else. It cannot add, widen or reorder anything.
Plan: `docs/superpowers/specs/2026-10-16-laya-advise-everywhere-plan.md` section 7.

```sh
check_plan.py plan    --repo ROOT [--trunk REF] [--base REF] --stage check --checks CHECKS.json [--out NEW.json]
check_plan.py verify  --plan-file PLAN.json --repo ROOT --stage check --checks CHECKS.json [--trunk REF]
                                                                 # exit 3 = expired, run full[]
check_plan.py outcome --decision-id ID --chosen full|relaxed
```

`--out` is created exclusively (`O_EXCL|O_NOFOLLOW`, mode 0600): an existing file or symlink is exit 2, never
overwritten. `verify` requires `--repo`, `--stage` and `--checks` (a missing flag is a usage error, exit 2) and
they must match the plan file. Pass the same `--trunk` to `verify` as to `plan`.

`CHECKS.json` is a list of `{"id", "kind"}`: the checks the repository normally requires (chosen from
repository instructions and known-safe package scripts, as `check.md` Phase 3 says). Unknown kinds count as
`other` and are mandatory. A missing or malformed file is exit 2: run the full list.

## Change set

The script reads git itself and never trusts a caller-supplied file list. It runs git with every `GIT_*`
variable removed, `GIT_CONFIG_NOSYSTEM=1`, `GIT_OPTIONAL_LOCKS=0`, `core.fsmonitor=false`,
`core.hooksPath=/dev/null` and the user's global config ignored, and refuses unless `rev-parse --show-toplevel`
is the real path of `--repo`.

- **Base.** `base = merge-base(trunk, HEAD)`, where `--trunk` defaults to `origin/main`. A missing trunk is the
  full plan (there is no `HEAD~` fallback). `--base` can only widen the window: it must be an ancestor of that
  merge-base, otherwise the full plan.
- **Changes.** The union of `git diff --raw -z -M --find-copies <base>` (worktree) and the same with `--cached`
  (so a staged change hidden by a restored worktree is still seen), plus untracked files from
  `git ls-files --others`. Renames and copies report both paths; deletions, mode changes, type changes,
  symlinks and submodules are blockers.
- **Hidden edits.** Any `assume-unchanged` or `skip-worktree` entry (`ls-files -v` lower-case or `S`) anywhere in
  the repository is a blocker, because it hides edits from `diff`.
- **Binding.** `diffSha256` hashes the sorted status lines, the sha256 of every changed file's bytes (or a
  deletion marker), the sha256 of `ls-files -s` (staged blobs and modes), the base commit, the stage and the
  checks file. Staging after planning therefore expires the plan.

## Eligibility

All of these must hold, otherwise `eligible` is false and `plan` equals `full`:

- The stage is routine (`implement`, `check`, `impact-map`, `test-evidence`). `review`, `release`,
  `production`, anything else or empty is a full-checks stage.
- Git succeeded, the diff is non-empty and has at most 2000 paths; no symlink, submodule, special file,
  mode change or type change.
- Every path is classified, and none is `protected`, `unknown` or `config`.
- At least one relaxation rule applies to the listed checks.

Classes: `docs` (`.md/.mdx/.rst/.txt` under `docs/`, top-level `*.md`, README/CHANGELOG-style names; not
SKILL.md, CLAUDE.md, commands, agents, skills or prompts, which are behavior and count as `logic`), `ui`
(components, styles, templates, routes, pages, app dirs, `.tsx/.jsx/.vue/.svelte`, e2e tests; UI code also
counts as logic), `logic` (source code), `test`, `config` (tsconfig, eslint, generic json/yaml/toml),
`protected`, `unknown`.

Protected never qualifies: CI/build/deploy config (`.github`, Dockerfile, Makefile, vercel/netlify, any file in a
`ci`, `cd`, `pipelines`, `workflows` or `release` directory, `*.config.*`, `.*rc` files, `conftest.py`,
`Package.swift`, `build.rs`, `alembic/`, names starting `deploy`, `release` or `publish`, and `.sh`/`.bash`
files under `scripts/`), auth-shaped names (the squashed path, camelCase and acronyms included, contains auth,
passw, jwt, oauth, secret, credential, token, login, logout, signin, signup, session, crypt, csrf, permission,
rbac, apikey or privatekey; or a name token such as middleware, security, policy, sso), env files, dependency manifests and lockfiles (package.json, `*.lock`,
requirements, pyproject, go.mod/sum, Cargo, Gemfile), migrations and `.sql`, infra (terraform, k8s, helm,
ansible), hooks and settings (`.claude`, `hooks/`, `hooks.json`, `settings*.json`, plugin manifests), and
key/credential-shaped files. These patterns are deliberately broad; a false positive costs only a full run.

## Rules and the never-relaxable set

| Rule | Effect |
|---|---|
| Every path is `docs` | `test-full` becomes `test-affected` |
| No `ui` path | `browser-qa` is skipped |
| No `logic` or `test` path | `mutation` is skipped (a test-only diff keeps it) |
| Any eligible diff | `lint` becomes `lint-changed` |

Only `test-full`, `lint`, `browser-qa` and `mutation` can ever be relaxed. `security-review`, `required-ci`,
`deploy`, `publish`, `credentials`, `approval`, `production-merge-review`, `typecheck`, `build` and `other`
always stay in `plan[]`. A replacement item is `{"id": "<id>:affected|changed", "kind", "relaxedFrom"}`; run it
with the repository's own convention, not a command from this output.

## Laya

When eligible the script calls `typed_advice.advise('check-relaxation', ...)` with a counts-only summary
(stage, class counts, relaxable kinds) and the changed paths, `critical_if_wrong=True`, key `diffSha256`.
`plan` is the relaxed list only when the registry mode is an earned `advise`, the diff is not in the
holdback arm and Laya recommends `relaxed`. Shadow, off, holdback, timeout, an invalid answer or any error
gives the full list. Before use the relaxed list is checked against the mandatory set; a violation falls back
to the full list. The output's `advice` block carries `decisionId` and `policySha256`; `decisionId` is also what
`outcome` takes.

The earned policy binds the candidate text and a sha256 of the classifier tables (`POLICY.classifierSha256`), so
rewording a candidate or editing a table resets the decision to `shadow` until it is earned again. Every
decision ships in `shadow`, which still asks Laya and records the answer by default; the kill switch is the
registry pin (`set-mode --pin off`), which stops the Laya call and returns the full list.

## Binding

`verify` recomputes the diff, the index, the base, the checks file hash and the stage. A changed `diffSha256`, a
different or release-like stage, a different repo or checks file, an unreadable file, a git failure or a plan
that is not exactly the deterministic full or relaxed list is expired (exit 3, `plan` in the output is the full
list). A relaxed list is additionally honoured only while all of these hold, read from the advice record on
disk and not from the plan file: the plan's `decisionId` derives from the current `diffSha256`, the record exists
with arm `treatment`, Laya status `ok` and choice `relaxed`, the plan's `policySha256` equals the current
policy and the record's, and `effective_mode` for that policy is still `advise`. A demoted or pinned registry, a
holdback record or a hand-edited plan therefore yields the full list. Run it right before reporting the verdict.
