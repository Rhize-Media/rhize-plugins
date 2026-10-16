# Check relaxation (S4)

`scripts/check_plan.py` lets `/rhize-devflow:check` run fewer routine checks on a low-risk diff. The
decision is deterministic and fails closed; Laya (decision `check-relaxation`) can only keep the full list.
Plan: `docs/superpowers/specs/2026-10-16-laya-advise-everywhere-plan.md` section 7.

```sh
check_plan.py plan    --repo ROOT [--base REF] --stage check --checks CHECKS.json [--out PLAN.json]
check_plan.py verify  --plan-file PLAN.json [--stage check]     # exit 3 = expired, run full[]
check_plan.py outcome --decision-id ID --chosen full|relaxed
```

`CHECKS.json` is a list of `{"id", "kind"}`: the checks the repository normally requires (chosen from
repository instructions and known-safe package scripts, as `check.md` Phase 3 says). Unknown kinds count as
`other` and are mandatory. A missing or malformed file is exit 2: run the full list.

## Change set

The script reads git itself and never trusts a caller-supplied file list: `git diff --raw -z -M --find-copies`
against the base (default: merge-base with `origin/main`, else `HEAD~`) covers committed, staged and
unstaged work, renames and copies (both paths), deletions and mode changes; untracked files come from
`git ls-files --others`. `diffSha256` hashes the sorted status lines, a sha256 of every changed file (or a
deletion marker), the stage and the checks file.

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

Protected never qualifies: CI/build/deploy config (`.github`, Dockerfile, Makefile, vercel/netlify, yml in
ci/deploy dirs), auth-shaped names (auth, session, permission, rbac, middleware, login, token, secret,
credential, security, ...), env files, dependency manifests and lockfiles (package.json, `*.lock`,
requirements, pyproject, go.mod/sum, Cargo, Gemfile), migrations and `.sql`, infra (terraform, k8s, helm,
ansible), hooks and settings (`.claude`, `hooks/`, `hooks.json`, `settings*.json`, plugin manifests), and
key/credential-shaped files. These patterns are deliberately broad; a false positive costs only a full run.

## Rules and the never-relaxable set

| Rule | Effect |
|---|---|
| Every path is `docs` | `test-full` becomes `test-affected` |
| No `ui` path | `browser-qa` is skipped |
| No `logic` path | `mutation` is skipped |
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
to the full list. The output's `advice` block carries `decisionId` for `outcome`.

## Binding

`verify` recomputes the diff, the checks file hash and the stage. A changed `diffSha256`, a different or
release-like stage, an unreadable file, a git failure or a plan that is not exactly the deterministic full or
relaxed list is expired (exit 3, `plan` in the output is the full list). Run it right before reporting the verdict.
