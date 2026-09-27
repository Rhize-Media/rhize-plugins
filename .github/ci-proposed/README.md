# CI proposals

Workflow changes may be edited directly under the user-approved CI hardening scope.
The global protect-files policy lifted its CI path gate on September 4, 2026.
This directory retains historical proposal context; no proposal is pending.

`validate.yml` preserves the repository release contracts, including the PR version check,
with one dependency setup. It runs for main pushes and PRs targeting main. Narrative docs
skip all push/PR workflows; shipped skill/command/agent instructions and operational
reference/template directories still trigger validation. `tag-release.yml` runs only when
main changes `.claude-plugin/marketplace.json`, and serializes stateful publishing.
