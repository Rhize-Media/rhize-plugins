# CI proposals

These workflow changes have task-specific user approval for CI hardening.
Existing protected-file hooks and general repository instructions remain unchanged.
This directory retains historical proposal context; no proposal is pending.

`validate.yml` preserves the repository release contracts, including the PR version check,
with one dependency setup. It runs for main pushes and PRs targeting main. Narrative docs
skip all push/PR workflows; shipped skill/command/agent instructions and operational
reference/template directories still trigger validation. `tag-release.yml` runs only when
main changes `.claude-plugin/marketplace.json`, and queues up to100 pending publishers without cancelling active publication.
