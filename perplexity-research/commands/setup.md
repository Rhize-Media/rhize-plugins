---
description: Configure the private Perplexity runtime and session without submitting a query
argument-hint: "[--from-rhize-setup]"
---

Parse `$ARGUMENTS` and strip `--from-rhize-setup` first. Follow `perplexity-research:perplexity-research`
Setup and the plugin README. Preserve an existing private JSON configuration/authorization file,
Keychain session and jobs. Never invent authorization, print credentials, or submit a query
as a test. When invoked with `--from-rhize-setup`, stop after setup and health so the hub resumes;
otherwise finish with the health result and configuration location. The marketplace hub is optional;
standalone setup uses the same JSON and requires no organization-specific services.
