# Setup artifacts

Every file or directory a Rhize plugin's setup wizard or day-to-day use can write is declared in that plugin's `setup/manifest.json` and rendered into the table below by `rhize-core/scripts/setup_artifacts.py --markdown`. Nothing here is written just by installing a plugin — a wizard, a hook, or a command has to actually run first.

<!-- SETUP-ARTIFACTS:BEGIN -->
| artifact | producer | path | how to view | lifetime | confidentiality | source | tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| compiled-knowledge | obsidian-second-brain | <vault>/.rhize/compiled-knowledge/ | ls <vault>/.rhize/compiled-knowledge/ | regenerated | personal | derived | outside-repo |
| vault-setup-log | obsidian-second-brain | <vault>/_vault-setup-log.md | open the note in Obsidian, or cat <vault>/_vault-setup-log.md | persistent | personal | authored | outside-repo |
| candidate-queue | procedural-memory | <home>/.claude/procedural-memory/candidate-queue.jsonl | cat ~/.claude/procedural-memory/candidate-queue.jsonl | append-only | personal | transcript-derived | outside-repo |
| procedural-memory-runs | procedural-memory | <home>/.rhize/procedural-memory/runs/ | ls ~/.rhize/procedural-memory/runs/ | per-run | none | derived | outside-repo |
| hookify-local-rules | project-launcher | <project>/.claude/hookify.*.local.md | cat .claude/hookify.<rule-id>.local.md | persistent | config | authored | ignored |
| planning-directory | project-launcher | <project>/.planning/ | cat .planning/STATE.md | persistent | none | authored | project |
| prd-directory | project-launcher | <project>/prd/ | cat prd/<name>.md | persistent | none | authored | project |
| context-experiments | rhize-context-manager | <home>/.claude/rhize-context-manager/context-experiments.json | cat ~/.claude/rhize-context-manager/context-experiments.json | persistent | config | derived | ignored |
| doctor-history | rhize-context-manager | <home>/.claude/context-manager/doctor/ | ls ~/.claude/context-manager/doctor/ | per-run | none | derived | outside-repo |
| harvest-logs | rhize-context-manager | <home>/.claude/context-manager/harvest-logs/ | cat ~/.claude/context-manager/harvest-logs/<date>-filter.txt | append-only | none | derived | outside-repo |
| refinement-queue | rhize-context-manager | <home>/.claude/context-manager/refinement-queue.jsonl | cat ~/.claude/context-manager/refinement-queue.jsonl | append-only | none | transcript-derived | outside-repo |
| skill-map-static | rhize-context-manager | <home>/.claude/context-manager/skill-map.static.json | cat ~/.claude/context-manager/skill-map.static.json | regenerated | none | derived | outside-repo |
| skill-refine-runs | rhize-context-manager | <home>/.claude/context-manager/runs/ | cat ~/.claude/context-manager/runs/<date>.md | per-run | none | derived | outside-repo |
| stack-config | rhize-context-manager | <home>/.claude/rhize-context-manager/stack.config.json | cat ~/.claude/rhize-context-manager/stack.config.json | persistent | config | authored | ignored |
| suggestion-log | rhize-context-manager | <home>/.claude/context-manager/suggestion-log.jsonl | cat ~/.claude/context-manager/suggestion-log.jsonl | append-only | none | derived | outside-repo |
| evals-config | rhize-core | <home>/.rhize/evals/config.json | cat ~/.rhize/evals/config.json | persistent | config | derived | outside-repo |
| evals-hmac-key | rhize-core | <home>/.rhize/evals/hmac.key | not human-readable — presence and 0600 permissions only | persistent | secret | derived | outside-repo |
| evals-receipts | rhize-core | <home>/.rhize/evals/receipts/ | cat ~/.rhize/evals/receipts/<month>.jsonl | append-only | none | derived | outside-repo |
| project-settings | rhize-core | <project>/.claude/settings.json | cat .claude/settings.json | persistent | config | authored | project |
| runtime-home | rhize-core | <home>/.rhize/evals/runtime-home/ | ls ~/.rhize/evals/runtime-home/ | persistent | none | derived | outside-repo |
| setup-runs | rhize-core | <home>/.rhize/setup/runs/ | python3 rhize-core/scripts/setup_orchestrator.py report --run <id> | per-run | config | derived | outside-repo |
| cowork-business-md | rhize-cowork | <project>/BUSINESS.md | cat BUSINESS.md | persistent | client | authored | project |
| cowork-claude-md | rhize-cowork | <project>/CLAUDE.md | cat CLAUDE.md | persistent | client | authored | project |
| cowork-info-md | rhize-cowork | <project>/INFO.md | cat INFO.md | persistent | client | authored | project |
| cowork-personality-md | rhize-cowork | <project>/PERSONALITY.md | cat PERSONALITY.md | persistent | client | authored | project |
| error-patterns-local | rhize-devflow | <project>/.claude/error-patterns.local.md | cat .claude/error-patterns.local.md | persistent | client | authored | ignored |
| refactor-gate-state | rhize-devflow | <home>/.claude/rhize-devflow/refactor-gate/ | ls ~/.claude/rhize-devflow/refactor-gate/ | per-run | none | derived | outside-repo |
| test-evidence-leases | rhize-devflow | <home>/.rhize/test-evidence/leases | cat ~/.rhize/test-evidence/leases | regenerated | none | derived | outside-repo |
| test-evidence-packets | rhize-devflow | <home>/.rhize/test-evidence/packets/ | cat ~/.rhize/test-evidence/packets/<packet>.json | per-run | none | derived | outside-repo |
| delegate-config | rhize-ops | <home>/.claude/rhize-ops/delegate.config.json | cat ~/.claude/rhize-ops/delegate.config.json (redact identifiers before sharing) | persistent | personal | authored | ignored |
| parallel-agent-optimization-receipts | rhize-ops | <home>/.rhize/parallel-agent-optimization/ | /rhize-ops:parallel-optimize report all | append-only | none | derived | outside-repo |
| skill-monitor-data | rhize-ops | <home>/.rhize/skill-monitor/ | python3 "$(rhize-ops/scripts/skill_monitor_root.sh)/dashboard.py" | regenerated | none | derived | outside-repo |
| application-support | rhize-tasks | <home>/Library/Application Support/Rhize Tasks/ | cat "~/Library/Application Support/Rhize Tasks/installation.json" | persistent | personal | derived | outside-repo |
| helper-launch-agent | rhize-tasks | <home>/Library/LaunchAgents/media.rhize.tasks.reminders-helper.plist | launchctl print gui/$(id -u)/media.rhize.tasks.reminders-helper | persistent | config | derived | outside-repo |
| routine-launch-agent | rhize-tasks | <home>/Library/LaunchAgents/media.rhize.tasks.plist | launchctl print gui/$(id -u)/media.rhize.tasks | persistent | config | derived | outside-repo |
| runtime-source-checkout | rhize-tasks | <home>/Library/Application Support/Rhize Tasks/source/v0.5.2/ | git -C "~/Library/Application Support/Rhize Tasks/source/v0.5.2" describe --tags --exact-match | persistent | none | derived | home |
<!-- SETUP-ARTIFACTS:END -->
