# Skill sources

Original Rhize workflow. Meta's official MCP supplies public search; native hosts own authentication. This plugin adds bounded capture instructions, a shared local evidence journal, integrity/recovery checks and exports. No provider scraper, OAuth client or upstream skill is redistributed.

**External assessment: Agent Reach — WATCH (2026-11-16)**

- Source: https://github.com/Panniantong/Agent-Reach
- Inspected: 1.6.1, commit c70ae6da5d39bc90e09ad2ae0575ccc89f31e284; MIT verified at repository root.
- Decision: optional external dependency only after qualification; no copied code, absorbed skill or fork.
- SkillForge: BLOCK because skillspector-unavailable; incomplete scan, not evidence of malware. Lexical overlap control passed; manual review found possible bounded social-comment gap.
- Rationale and pilot criteria: [assessment](../docs/agent-reach-assessment.md). No native inclusion or installation. Reassess at an explicitly approved pilot or relevant upstream change; no scheduled watcher created.

**Broader research workflow (2026-11-16):** original Rhize evidence validation, failure accounting and host-portable instructions. It complements existing search and research tools; no upstream Agent Reach code or skill is copied. Its skill-only scan is now CAUTION after rebuilding stale SkillForge dist; the full source scan remains DO_NOT_INSTALL with incomplete coverage. See [isolation disposition](../docs/agent-reach-isolation.md). No runtime adoption.

**Public adapter successor — ABSORB (candidate 2026-11-17)**

`metadata.rhize.extends`: https://github.com/Panniantong/Agent-Reach/tree/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284

Seven pure parsing/normalization functions are copied verbatim with reduced stdlib imports. Exact original file hashes, retained function line ranges and local runtime hashes are in `../reach/provenance.json`; upstream MIT notice is redistributed in `../reach/LICENSE`. Broker, dispatcher, process isolation and host packaging are original Rhize code. This supersedes the no-copy decision only for this extracted closure; it is not full-package clearance. See [candidate status and setup](../docs/agent-reach-public.md). No upstream installation or browser/session dependencies are included.
