---
name: credential-access
description: >-
  Use when authenticating a CLI or retrieving a stored credential, password, token,
  or API key from macOS Keychain. Choose CLI-first access and private child-process
  consumption; never open Keychain Access or expose secrets in tool output.
metadata:
  rhize:
    topics: [security, automation]
    stacks: []
    router:
      phrases: [keychain access, keychain credentials, stored credentials]
---

# Credential access

1. Use the service's already authenticated CLI/API when it meets the task. Check only account/project metadata needed for the authorized action. Do not retrieve a credential just to inspect it.
2. If a stored credential is necessary, identify its exact service/account from existing instructions. Use macOS `security` CLI; never open Keychain Access, read a secret from GUI/accessibility/screenshot, or copy it through the clipboard. Do not enumerate all stored items.
3. Capture lookup output privately inside the consuming subprocess. Pass only to its authorized child through stdin or a process-local environment. Use the installed `mcp-secret-launcher VAR -- command` for stdio children using its `claude-code:VAR` convention; do not assume unrelated account items follow that convention. A direct `security find-generic-password ... -w` in recorded terminal output exposes the credential and is prohibited. Do not put secret values in argv, files, logs, model inputs, persistent shell exports, or tool-to-tool text.
4. Report metadata-only success/failure. Missing credentials or OS access denial stop the dependent step. Do not fall back to the GUI, change Keychain ACLs, reset accounts, or retrieve broader secrets. When macOS requires human consent, explain the exact blocked action and leave consent to the user.

The auto-wired PreToolUse credential guard blocks explicit Keychain GUI targets in execution and computer-use tool requests, including requests inside an ongoing task. Its fixed denial links here. It never reads credentials and does not grant permissions. Code-mode orchestration passes through; each nested executable/MCP call must receive its own hook. The guard checks visible action text; it does not sandbox arbitrary encoded code, an existing opaque app handle, or host tool paths that omit hooks. A source edit or a local test does not establish that a running host has loaded the guard: use fresh native-session proof.

The current decision contract retains deterministic credential policy and Laya shadow assessment. A model score, disagreement, timeout, missing workflow match, or prebound routine cannot clear the GUI block.
