#!/usr/bin/env node
'use strict';

// skill-router.js — map-driven skill suggestion hook (UserPromptSubmit).
//
// Replaces the keyword-grep skill-suggester.sh (retired 2026-08-09, see
// SOURCES.md / CHANGELOG). Ranks the submitted prompt against the compiled
// skill-map artifact's topic-tag/stack-tag edges and skill names instead of a
// fixed regex keyword list, so new skills route automatically once tagged —
// no hook edit required.
//
// TIER: T3 (advisory). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt input — a missing map, a plugin installed
// without this repo's `generated/` dir, or a malformed prompt must never
// surface an error to the user or to Claude.
//
// CONTRACT: reads hook JSON from stdin, field "prompt" (not "user_prompt" —
// see skill-suggester.sh's history in git blame for why that distinction
// matters). additionalContext must be nested inside
// hookSpecificOutput.additionalContext to reach Claude; a top-level field or
// systemMessage alone would not.
//
// INDEX RESOLUTION (relationships v2, section 7 of the design doc): the
// primary data source is now the materialized `router` index, precomputed
// by build_skill_map.py/build_local_skill_map.py so this hook never walks
// doc.edges itself. Preference order, all under
// ~/.claude/context-manager/:
//   1. skill-map.indexes.resolved.json (static + local-overlay follows merge)
//   2. skill-map.indexes.json          (installed by `build_skill_map.py --install`)
// Neither present/parseable/missing a `router` section -> FALL BACK to the
// original map-scanning path below (readMap/route), so an older install that
// only shipped skill-map.{resolved,static}.json (no indexes file yet)
// degrades gracefully instead of going silent. Behavior is identical either
// way — the index only saves re-deriving signals from doc.edges per call.
//
// MAP RESOLUTION (fallback only):
//   1. skill-map.resolved.json (static + local overlay, once Phase 3 lands)
//   2. skill-map.static.json   (installed by `build_skill_map.py --install`)
// Neither present or parseable -> exit 0, no output.
//
// RANKING: tokenize the prompt into lowercase alnum words, plural-folded
// (route-core's normalizeWord(): `-ies` -> `-y`, trailing non-`ss` `-s`
// dropped; labels fold the same way). For every `skill` node, a
// topic-tag/stack-tag edge is a "tag signal" (weight 2) if every word of the
// tag's name is present among the prompt's tokens; the skill's own name is a
// "name signal" (weight 1) under the same all-words-present rule. A 3+-word
// name missing exactly one word adds a "name-partial" signal (weight 0.5),
// suppressed for the whole prompt whenever any skill's full name matched.
// Tag signals outweigh name signals, per the plan's "tag match > name match"
// rule. At least 2 DISTINCT signals must match for a skill to be considered
// at all, at least one of weight >= 1 — a single weak match must never emit
// (see plan's "Router noise" risk). Among qualifying skills, the highest
// total weight wins; ties break on skill id (deterministic, no randomness).
// All of this lives in route-core's shared matcher (scoreCandidates()).
//
// SKILL-FIT CO-SIGN (Laya earned authority, plan v3 §4.3): for a fired,
// non-explicit router suggestion the hook asks the local Laya server (literal
// loopback only, see lib/laya-client.js) which of the lexical top-5 skills (or
// none) fits the prompt. In mode `cosign`, in the treatment arm, a suggestion
// Laya does not independently choose is withheld; in every other case (mode
// `shadow`, the holdback arm, any Laya failure or deadline expiry, any
// exception) the precomputed incumbent payload is emitted unchanged. The
// payload is settled exactly once and flushed before any logging or exit, and
// one decision record (no prompt text) is appended per eligible prompt.
//
// HOSTS AND PACKAGING (plan 2026-10-11 section 7): the host (claude|codex|unknown) is detected from
// RHIZE_HOST, then the transcript_path location, then thread_id / CLAUDE_CODE_ENTRYPOINT; records and
// legacy rows carry it. For codex the hook proceeds only for a user thread (first rollout line is a
// session_meta whose thread_source is "user") and identifies the session by session_meta.payload.id;
// guardian reviews, subagents and automations behave like the background observer. Only hosts in
// COSIGN_HOSTS may co-sign; any other host is capped at shadow for the invocation. hooks.json registers
// this file once as `skill-router.js --packaged`: that run is silent unless the opt-in config
// ($XDG_DATA_HOME|~/.local/share/rhize/skill-router/config.json = {"schemaVersion":1,"enabled":true})
// exists and, in Claude, no manual (non-packaged) router hook is registered in settings.json /
// settings.local.json (user or project). A manual run behaves as before.
//
// BUDGET: <150ms warm without workflow opt-in or a reachable Laya; opt-in
// bridge deadline 4.5s; Laya probe + POST share one 800ms deadline (registry
// latencyBudgetMs). The host hook timeout must be >= 8s. The map is read
// synchronously once per invocation (and only for eligible prompts, for skill
// descriptions).

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');
const { performance } = require('perf_hooks');

// Shared primitives (index/map reading, tokenize, scoring, logging) live in
// hooks/lib/route-core.js so agent-brief-router.js can reuse them without
// duplicating the ranking logic. Policy — thresholds, the one-suggestion
// cap, and message shaping (formatMatch below) — stays in this hook.
const {
  readIndexes,
  readMap,
  tokenize,
  formatSkillRef,
  formatSignalLabel,
  routeFromIndex,
  route,
  contextHash,
  logSuggestion,
  lexicalShortlist,
} = require(path.join(__dirname, 'lib', 'route-core.js'));
// The skill-fit layer is optional: if any of its modules cannot be loaded (a
// partially updated checkout, version skew) the hook behaves exactly like the
// legacy router instead of crashing.
let L = null;
try {
  const instrument = require(path.join(__dirname, 'lib', 'laya-instrument.js'));
  L = {
    buildChoiceRequest: instrument.buildChoiceRequest,
    canonicalJson: instrument.canonicalJson,
    sha256Hex: instrument.sha256Hex,
    INSTRUMENT: instrument.INSTRUMENT,
    td: require(path.join(__dirname, 'lib', 'typed-decisions.js')),
    readDecisionConfig: require(path.join(__dirname, 'lib', 'decision-registry.js')).readDecisionConfig,
    // Kept as a module object so callChoice is late-bound (a test preload can substitute the transport).
    client: require(path.join(__dirname, 'lib', 'laya-client.js')),
  };
} catch (_) { L = null; }

const DECISION = 'skill-fit';
// Hosts whose skill-fit decision may run in `cosign`. Every other host (codex, unknown) is capped at
// `shadow` for the invocation, whatever the registry or machine state says: Codex has no co-sign
// evidence yet, and it must not be pooled into the promotion/demotion gate (plan section 7, F6).
const COSIGN_HOSTS = ['claude'];
const PACKAGED = process.argv.includes('--packaged');
const MAX_CONFIG_BYTES = 16 * 1024;
const MAX_SETTINGS_BYTES = 1024 * 1024;
const MAX_ROLLOUT_LINE_BYTES = 512 * 1024;
const SKILL_ID = /^skill:[A-Za-z0-9_.\-/]+$/;
const MAX_RECORD_BYTES = 4096;
const SETTLE_MARGIN_MS = 50; // settle-once backstop fires this long after the Laya deadline
const HARD_EXIT_MARGIN_MS = 2000; // last-resort exit if a flush or socket never completes
const NON_LAYA_HARD_EXIT_MS = 2000;
const LAYA_STATUSES = ['ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused'];

function formatMatch(match) {
  if (!match) return null;
  const ref = formatSkillRef(match.skillId);
  if (!ref) return null;
  const why = match.signals.map(formatSignalLabel).join(', ');
  return `Consider the ${ref} skill (matches ${why})`;
}

// ECC's homunculus background observer runs its own headless Claude sessions
// (cwd ~/.local/share/ecc-homunculus or its projects/<12 hex> children). That is
// machine traffic: replaying 2026-09-27..10-11 on the maintainer's Mac, it was
// 1,134 of 1,366 router fires (83%), every one parallel-agent-optimization.
// The workflow selector already excludes these sessions
// (workflow_context_packet.native_observer); the router now skips its own
// suggestion, the Laya call, the decision record and the silence sample for
// them. Only the cwd identifies them: the ECC launcher's env knobs
// (ECC_SKIP_OBSERVE/ECC_HOOK_PROFILE) are user-facing settings a person may
// export in an interactive shell, so they alone must not silence the router.
function isBackgroundObserver(data, home = os.homedir()) {
  if (!data || typeof data.cwd !== 'string' || !data.cwd) return false;
  const cwd = path.resolve(data.cwd);
  const root = path.join(home, '.local', 'share', 'ecc-homunculus');
  return cwd === root || (path.dirname(cwd) === path.join(root, 'projects') && /^[0-9a-f]{12}$/.test(path.basename(cwd)));
}

// ---------------------------------------------------------------- host, opt-in and thread gate

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isNonEmptyString = (value) => typeof value === 'string' && value.trim() !== '';

// Reads a regular file with a hard size bound. Never follows a symlink unless `follow` is set (the
// opt-in config and Codex rollouts refuse them; a user's settings.json is often a dotfiles symlink).
// `firstLine` returns only the first line (null when it exceeds maxBytes). null on any failure.
function readBounded(file, maxBytes, { follow = false, firstLine = false } = {}) {
  let fd = null;
  try {
    if (!follow) {
      const link = fs.lstatSync(file);
      if (link.isSymbolicLink() || !link.isFile()) return null;
    }
    const flags = fs.constants.O_RDONLY | (fs.constants.O_NONBLOCK || 0) | (follow ? 0 : (fs.constants.O_NOFOLLOW || 0));
    fd = fs.openSync(file, flags);
    const stat = fs.fstatSync(fd);
    if (!stat.isFile()) return null;
    if (!firstLine && stat.size > maxBytes) return null;
    const buf = Buffer.allocUnsafe(Math.min(stat.size, maxBytes));
    let filled = 0;
    while (filled < buf.length) {
      const n = fs.readSync(fd, buf, filled, buf.length - filled, null);
      if (n <= 0) break;
      filled += n;
    }
    if (!firstLine) return buf.toString('utf8', 0, filled);
    const newline = buf.indexOf(0x0a);
    if (newline === -1) return stat.size > maxBytes ? null : buf.toString('utf8', 0, filled).replace(/\r$/, '');
    return buf.toString('utf8', 0, newline).replace(/\r$/, '');
  } catch (_) {
    return null;
  } finally {
    if (fd !== null) { try { fs.closeSync(fd); } catch (_) { /* ignore */ } }
  }
}

const CODEX_ROOTS = ['sessions', 'archived_sessions'];
const codexRoot = (home, sub) => path.join(home, '.codex', sub);

// Absolute, normalized rollout path when `value` names ~/.codex/{sessions,archived_sessions}/**/rollout-*.jsonl.
function codexRolloutPath(value, home) {
  if (typeof value !== 'string' || !value || value.indexOf('\0') !== -1 || !path.isAbsolute(value)) return null;
  const abs = path.resolve(value);
  if (!/^rollout-.*\.jsonl$/.test(path.basename(abs))) return null;
  return CODEX_ROOTS.some((sub) => abs.startsWith(codexRoot(home, sub) + path.sep)) ? abs : null;
}

function claudeTranscriptPath(value, home) {
  if (typeof value !== 'string' || !value || value.indexOf('\0') !== -1 || !path.isAbsolute(value)) return false;
  return path.resolve(value).startsWith(path.join(home, '.claude', 'projects') + path.sep);
}

// Pure host detection (plan section 7, F4). Precedence:
//   1. a valid RHIZE_HOST override (claude|codex); an invalid value is ignored;
//   2. the transcript_path location (the host's own transcript is the strongest native evidence, and it
//      outranks session variables that can leak into a cross-host child process);
//   3. payload thread_id (codex) versus env CLAUDE_CODE_ENTRYPOINT (claude); both present -> 'unknown';
//   4. no evidence at all -> 'claude' (the legacy default).
function detectHost(payload, env = process.env, home = os.homedir()) {
  const explicit = env && env.RHIZE_HOST;
  if (explicit === 'claude' || explicit === 'codex') return explicit;
  const data = isObject(payload) ? payload : {};
  if (codexRolloutPath(data.transcript_path, home)) return 'codex';
  if (claudeTranscriptPath(data.transcript_path, home)) return 'claude';
  const codex = isNonEmptyString(data.thread_id);
  const claude = Boolean(env) && isNonEmptyString(env.CLAUDE_CODE_ENTRYPOINT);
  if (codex && claude) return 'unknown';
  if (codex) return 'codex';
  return 'claude';
}

// Codex user-thread gate (F1). Reads ONLY the first line of the rollout (bounded, no symlinks, regular
// file under the Codex roots) and returns { user, id }: user is true only for a session_meta whose
// payload.thread_source is exactly 'user'. null when the file is missing, unsafe, oversized or not JSON.
function readCodexThread(transcriptPath, home = os.homedir()) {
  const abs = codexRolloutPath(transcriptPath, home);
  if (!abs) return null;
  try {
    const real = fs.realpathSync(abs);
    const contained = CODEX_ROOTS.some((sub) => {
      try { return real.startsWith(fs.realpathSync(codexRoot(home, sub)) + path.sep); } catch (_) { return false; }
    });
    if (!contained) return null;
    const line = readBounded(abs, MAX_ROLLOUT_LINE_BYTES, { follow: false, firstLine: true });
    if (!line) return null;
    const meta = JSON.parse(line);
    const payload = isObject(meta) ? meta.payload : null;
    if (!isObject(payload)) return null;
    const isMeta = meta.type === 'session_meta' || Object.prototype.hasOwnProperty.call(payload, 'thread_source');
    if (!isMeta) return null;
    return { user: payload.thread_source === 'user', id: isNonEmptyString(payload.id) ? payload.id : null };
  } catch (_) {
    return null;
  }
}

// Session identity (F2): codex -> session_meta.payload.id, else session_id || thread_id; claude -> session_id.
function sessionIdentity(host, data, thread) {
  const strings = (...values) => values.find(isNonEmptyString) || null;
  if (host === 'claude') return typeof data.session_id === 'string' ? data.session_id : null;
  if (host === 'codex') return strings(thread && thread.id, data.session_id, data.thread_id);
  return strings(data.session_id, data.thread_id);
}

function packagedConfigEnabled(env = process.env, home = os.homedir()) {
  const root = (env && env.XDG_DATA_HOME) || path.join(home, '.local', 'share');
  const text = readBounded(path.join(root, 'rhize', 'skill-router', 'config.json'), MAX_CONFIG_BYTES);
  if (!text) return false;
  try {
    const cfg = JSON.parse(text);
    return isObject(cfg) && cfg.schemaVersion === 1 && cfg.enabled === true;
  } catch (_) {
    return false;
  }
}

// A command that actually runs this router manually: node … skill-router.js, without --packaged. A command that only
// mentions the file name (an echo, a grep, a different script) is not a registration (Codex final review).
const MAX_HOOK_COMMAND_CHARS = 8192;
// Splits a hook command into simple commands (arrays of {text, redirect} words), honouring quotes, backslashes and
// comments. `;`, `&`, `|`, parentheses and newlines end a simple command. `redirect` marks a word that starts with an
// UNQUOTED redirection operator, so a quoted argument such as a `bash -c '>/dev/null node ...'` string is never
// mistaken for one. Variables are kept literally. Enough to find the program and its script argument; not a full
// shell parser.
function shellSimpleCommands(command) {
  const commands = [];
  let words = [];
  let word = '';
  let inWord = false;
  let quote = null;
  let redirect = false;
  const endWord = () => {
    if (inWord) words.push({ text: word, redirect });
    word = '';
    inWord = false;
    redirect = false;
  };
  const endCommand = () => { endWord(); if (words.length) commands.push(words); words = []; };
  for (let i = 0; i < command.length; i += 1) {
    const ch = command[i];
    if (quote === "'") { if (ch === "'") quote = null; else word += ch; continue; }
    if (quote === '"') {
      if (ch === '"') quote = null;
      else if (ch === '\\' && i + 1 < command.length && '"\\$`'.includes(command[i + 1])) { i += 1; word += command[i]; }
      else word += ch;
      continue;
    }
    if (ch === "'" || ch === '"') { quote = ch; inWord = true; continue; }
    // Redirections are their own words, even when glued to the previous word (`x.js>/dev/null`): `>` / `<` start
    // a new word unless the current one is an fd number or an operator in progress; `>&`/`<&` (`2>&1`) and `&>`
    // (`&>/dev/null`) belong to the redirection word, not a command separator.
    if (ch === '&' && redirect && /[<>]$/.test(word)) { word += ch; continue; }
    if (ch === '&' && command[i + 1] === '>') { endWord(); word = '&'; inWord = true; redirect = true; continue; }
    if (ch === '>' || ch === '<') {
      if (inWord && !redirect && !/^\d+$/.test(word)) endWord();
      word += ch;
      inWord = true;
      redirect = true;
      continue;
    }
    if (ch === '#' && !inWord) { // a comment runs to the end of the line
      while (i + 1 < command.length && command[i + 1] !== '\n') i += 1;
      continue;
    }
    if (ch === '\\' && i + 1 < command.length) { i += 1; if (command[i] !== '\n') { word += command[i]; inWord = true; } continue; }
    if (ch === '\n' || ';&|()'.includes(ch)) { endCommand(); continue; }
    if (/\s/.test(ch)) { endWord(); continue; }
    word += ch;
    inWord = true;
  }
  endCommand();
  return commands;
}

// Wrappers that run a later word as the command, with the options that take a separate value.
const COMMAND_PREFIXES = {
  env: new Set(['-u', '--unset', '-C', '--chdir']),
  exec: new Set(['-a']),
  command: new Set(),
  nohup: new Set(),
  nice: new Set(['-n', '--adjustment']),
  time: new Set(),
  timeout: new Set(['-s', '--signal', '-k', '--kill-after']),
  mise: new Set(['-C', '--cd', '-E', '--env']),
  arch: new Set(),
  caffeinate: new Set(['-t', '-w']),
};
// Words a wrapper takes before the command: options, VAR=value, mise's `exec`/`x` subcommand and its `--`
// separator, and at most ONE number or duration per wrapper (`timeout 10`), so `timeout 10 123 node ...` runs `123`.
const WRAPPER_OPERAND = /^(?:-.*|[A-Za-z_][A-Za-z0-9_]*=.*|exec|x)$/;
const WRAPPER_NUMBER = /^\d+(?:\.\d+)?[smhd]?$/;
// Shell reserved words that may precede a command in a compound (`if ...; then node ...; fi`, `{ node ...; }`).
const RESERVED_WORDS = new Set(['if', 'then', 'else', 'elif', 'do', 'while', 'until', '{', '!']);
// A redirection word that is only the operator (`>`, `2>`, `>>`, `<<<`, `>&`): its target is the next word.
const BARE_REDIRECTION = /^(?:\d+|&)?(?:[<>]+&?|>\|)$/;

// The plain words of a simple command, without its redirections (`>f`, `2>&1`, `&>f`, `> f`, `<<< x`).
function withoutRedirections(words) {
  const kept = [];
  for (let i = 0; i < words.length; i += 1) {
    if (!words[i].redirect) kept.push(words[i].text);
    else if (BARE_REDIRECTION.test(words[i].text)) i += 1;
  }
  return kept;
}
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash']);
// Shell options that take the next word as their value (`bash -o pipefail -c ...`).
const SHELL_VALUE_OPTIONS = new Set(['-o', '+o', '-O', '+O', '--rcfile', '--init-file']);
// Node options that take the next word as their value; any other `-` word is a flag.
const NODE_VALUE_OPTIONS = new Set(['-r', '--require', '--import', '--loader', '--experimental-loader', '-C',
  '--conditions', '--env-file', '--input-type', '--title', '--inspect-port', '--redirect-warnings']);
// Node options after which no script file runs.
const NODE_NO_SCRIPT = new Set(['-e', '--eval', '-p', '--print', '-c', '--check', '-i', '--interactive', '-v',
  '--version', '-h', '--help']);

// True when this simple command (or a `sh -c` string it runs) executes `node <...>/skill-router.js` WITHOUT
// `--packaged` among that router's own arguments. Only the program word (after assignments and env/exec-style
// prefixes) counts, and only Node's actual script argument counts (Codex final review): a mention elsewhere,
// another script receiving the path as an argument, or `--packaged` belonging to another command decides nothing.
function runsManualRouter(rawWords, depth) {
  const words = withoutRedirections(rawWords);
  let i = 0;
  let prefix = null;
  let numberUsed = false;
  while (i < words.length) {
    const word = words[i];
    const base = path.basename(word);
    if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(word) || (!prefix && RESERVED_WORDS.has(word))) { i += 1; continue; }
    if (Object.prototype.hasOwnProperty.call(COMMAND_PREFIXES, base)) { prefix = base; numberUsed = false; i += 1; continue; }
    if (prefix && !numberUsed && WRAPPER_NUMBER.test(word)) { numberUsed = true; i += 1; continue; }
    if (prefix && WRAPPER_OPERAND.test(word)) {
      if (prefix === 'command' && (word === '-v' || word === '-V')) return false; // a lookup, not a run
      i += COMMAND_PREFIXES[prefix].has(word) ? 2 : 1;
      continue;
    }
    break;
  }
  if (i >= words.length) return false;
  const program = path.basename(words[i]);
  if (SHELLS.has(program)) {
    if (depth >= 2) return false;
    for (let k = i + 1; k < words.length; k += 1) {
      if (SHELL_VALUE_OPTIONS.has(words[k])) { k += 1; continue; }
      if (!/^[-+]/.test(words[k])) return false; // a script file, not a -c string
      if (/^-[A-Za-z]*c[A-Za-z]*$/.test(words[k])) {
        return k + 1 < words.length && isManualRouterCommandAt(words[k + 1], depth + 1);
      }
    }
    return false;
  }
  if (program !== 'node' && program !== 'nodejs') return false;
  let k = i + 1;
  for (; k < words.length; k += 1) {
    const w = words[k];
    if (w === '--') { k += 1; break; }
    if (!w.startsWith('-') || w === '-') break;
    if (NODE_NO_SCRIPT.has(w)) return false;
    if (NODE_VALUE_OPTIONS.has(w)) k += 1;
  }
  if (k >= words.length || path.basename(words[k]) !== 'skill-router.js') return false;
  return !words.slice(k + 1).includes('--packaged');
}

function isManualRouterCommandAt(command, depth) {
  if (typeof command !== 'string' || !command || command.length > MAX_HOOK_COMMAND_CHARS) return false;
  return shellSimpleCommands(command).some((words) => runsManualRouter(words, depth));
}

function isManualRouterCommand(command) {
  return isManualRouterCommandAt(command, 0);
}

// True when the settings' UserPromptSubmit hooks (the only event this router serves) run it manually. Registrations
// under other events never invoke it for a prompt, so they must not silence the packaged entry.
function hasManualRouterHook(hooks) {
  const groups = isObject(hooks) && Array.isArray(hooks.UserPromptSubmit) ? hooks.UserPromptSubmit : [];
  return groups.slice(0, 256).some((group) => isObject(group) && Array.isArray(group.hooks)
    && group.hooks.slice(0, 256).some((hook) => isObject(hook) && isManualRouterCommand(hook.command)));
}

// Project settings directories Claude may read for this session: <dir>/.claude for cwd and every parent, so a
// project root above cwd is covered (Codex final review). Bounded depth; the home directory's own .claude is
// always included.
function claudeSettingsDirs(cwd, home) {
  const dirs = [path.join(home, '.claude')];
  let dir = path.resolve(cwd);
  for (let i = 0; i < 32; i += 1) {
    const candidate = path.join(dir, '.claude');
    if (!dirs.includes(candidate)) dirs.push(candidate);
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return dirs;
}

// A manual (legacy) registration of this hook in Claude's user or project settings.
function hasManualRegistration(data, home = os.homedir()) {
  const cwd = isObject(data) && typeof data.cwd === 'string' && path.isAbsolute(data.cwd) ? data.cwd : process.cwd();
  for (const dir of claudeSettingsDirs(cwd, home)) {
    for (const name of ['settings.json', 'settings.local.json']) {
      const text = readBounded(path.join(dir, name), MAX_SETTINGS_BYTES, { follow: true });
      if (!text) continue;
      try {
        const settings = JSON.parse(text);
        if (isObject(settings) && hasManualRouterHook(settings.hooks)) return true;
      } catch (_) { /* invalid settings: no entry */ }
    }
  }
  return false;
}

// A packaged run proceeds only when the user opted in AND (in Claude) no manual registration already
// runs the router, so exactly one run produces output, Laya calls and records per prompt.
function packagedMayRun(data, env = process.env, home = os.homedir()) {
  if (!packagedConfigEnabled(env, home)) return false;
  if (detectHost(data, env, home) === 'claude' && hasManualRegistration(data, home)) return false;
  return true;
}

// Caps the effective mode at shadow for hosts outside COSIGN_HOSTS (state and registry stay untouched).
function capModeForHost(config, host) {
  if (config && config.mode === 'cosign' && !COSIGN_HOSTS.includes(host)) return { ...config, mode: 'shadow' };
  return config;
}

function payloadFor(message) {
  if (!message) return null;
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'UserPromptSubmit',
      additionalContext: message,
    },
  }) + '\n';
}

// Reads stdin, ranks the prompt against the map, and returns everything main()
// needs to settle exactly once: the COMPLETE incumbent payload (the bytes
// today's hook would write, or null), the payload without the router
// suggestion (used only by a cosign suppression), and the facts the Laya
// co-sign and the logs need. Returns null when there is nothing to do. Throws
// on any unreadable/corrupt input; main()'s try/catch turns that into the
// same silent no-op.
//
// Tries the materialized router index first (routeFromIndex); only when no
// indexes file is present/parseable does this fall back to the original
// map-scanning path (readMap/route) — see the INDEX RESOLUTION note above.
function prepare(raw, data) {
  const ts = new Date().toISOString();
  const prompt = typeof data.prompt === 'string' ? data.prompt : '';
  if (!prompt) return null;
  const host = detectHost(data);
  // Codex runs the router for every thread, including guardian reviews, subagents and automations:
  // only a user thread is router traffic. Anything else is treated exactly like the background observer.
  const thread = host === 'codex' ? readCodexThread(data.transcript_path) : null;
  const machineThread = host === 'codex' && !(thread && thread.user);
  const sessionId = sessionIdentity(host, data, thread);

  let workflowMessage = null;
  let workflowHandled = false;
  // One shared selector owns opted-in workflow decisions. Both the legacy
  // router and packaged hook use its atomic receipt; configuration alone
  // never suppresses advice. A failed bridge falls back to this router.
  try {
    const root = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
    const cfgPath = path.join(root, 'rhize', 'workflow-selection', 'config.json');
    const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    if (cfg.schemaVersion === 1 && cfg.enabled === true) {
      const output = execFileSync('python3', [path.join(__dirname, '..', 'scripts', 'workflow_selection.py'), 'hook', '--router-bridge'], {
        input: raw, encoding: 'utf8', timeout: 4500, maxBuffer: 16384, stdio: ['pipe','pipe','ignore'],
      });
      const bridge = JSON.parse(output);
      workflowHandled = bridge.handled === true;
      workflowMessage = bridge.hookOutput?.hookSpecificOutput?.additionalContext || null;
    }
  } catch (_) { /* missing/untrusted/unavailable selector: preserve old routing */ }

  const promptTokens = tokenize(prompt);
  const ctxHash = contextHash(prompt);

  const observer = isBackgroundObserver(data) || machineThread;
  if (observer && !workflowMessage) return null;
  const routerIndex = observer ? null : readIndexes();
  const match = observer ? null : routerIndex
    ? routeFromIndex(routerIndex, promptTokens, prompt)
    : (() => {
        const doc = readMap();
        return doc ? route(doc, promptTokens, prompt) : null;
      })();

  const overlaps = workflowHandled && match && /\/(?:rhize-content-engine|content-engine)$/.test(match.skillId) && !/\becc\b/i.test(prompt);
  const routerRef = overlaps ? null : formatMatch(match);
  const incumbentMessage = [workflowMessage, routerRef].filter(Boolean).join(' ') || null;
  const suppressedMessage = [workflowMessage].filter(Boolean).join(' ') || null;

  const explicit = Boolean(match) && match.signals.some((signal) => signal.label === 'explicit skill request');
  return {
    ts, prompt, sessionId, host, machineThread, promptTokens, contextHash: ctxHash, routerIndex, match, observer,
    incumbentPayload: payloadFor(incumbentMessage),
    incumbentShown: incumbentMessage && routerRef && match ? match.skillId : null,
    suppressedPayload: payloadFor(suppressedMessage),
    eligible: Boolean(match) && Boolean(routerIndex) && !explicit,
  };
}

// Builds the Laya request for an eligible prompt. Returns null (no Laya call,
// no record) when the mode is off, the incumbent id cannot be sent, or the
// request cannot be built; throws are caught by the caller with the same effect.
function planLaya(state) {
  if (!L) return null;
  const config = capModeForHost(L.readDecisionConfig(DECISION), state.host);
  if (config.mode === 'off' || !config.endpoint || !config.model) return null;
  const incumbentId = state.match.skillId;
  if (!SKILL_ID.test(incumbentId)) return null;
  const shortlist = lexicalShortlist(state.routerIndex, state.promptTokens, incumbentId, 5).filter((id) => SKILL_ID.test(id));
  if (!shortlist.includes(incumbentId)) return null;

  const wanted = new Set(shortlist);
  const descriptions = new Map();
  try {
    const doc = readMap();
    if (doc) {
      for (const node of doc.nodes) {
        if (node && node.kind === 'skill' && wanted.has(node.id) && typeof node.description === 'string') {
          descriptions.set(node.id, node.description);
        }
      }
    }
  } catch (_) { /* descriptions are optional */ }
  const built = L.buildChoiceRequest(state.prompt, shortlist.map((skillId) => ({
    skillId, description: descriptions.has(skillId) ? descriptions.get(skillId) : null,
  })));

  const sessionHash = L.sha256Hex(state.sessionId || '');
  const promptHash = L.sha256Hex(state.prompt);
  const arm = L.td.armFor(sessionHash, promptHash, config.holdback);
  const propensity = arm === 'holdback' ? config.holdback : 1 - config.holdback;
  return { config, shortlist, built, sessionHash, promptHash, arm, propensity };
}

// Coerces whatever the transport returned into a record-safe Laya outcome.
function normalizeLaya(raw, plan) {
  const out = { status: 'unavailable', choice: null, probabilities: null, latencyMs: null, truncated: plan.built.truncated };
  if (!raw || typeof raw !== 'object' || !LAYA_STATUSES.includes(raw.status)) return out;
  if (typeof raw.latencyMs === 'number' && Number.isFinite(raw.latencyMs) && raw.latencyMs >= 0) out.latencyMs = raw.latencyMs;
  if (raw.status !== 'ok') { out.status = raw.status; return out; }
  const probs = raw.probabilities;
  const choiceOk = raw.choice === 'none' || plan.shortlist.includes(raw.choice);
  const probsOk = Array.isArray(probs) && probs.length === plan.shortlist.length + 1
    && probs.every((p) => typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 1);
  if (!choiceOk || !probsOk) { out.status = 'invalid'; return out; }
  out.status = 'ok';
  out.choice = raw.choice;
  out.probabilities = probs.slice();
  return out;
}

// ---------------------------------------------------------------- persistence
// Everything below runs only AFTER the hook payload has been flushed, each part
// in its own try/catch: a persistence failure can never alter the output.

function ensurePrivateDir(dir) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let stat = null;
    try { stat = fs.lstatSync(dir); } catch (err) { if (!err || err.code !== 'ENOENT') throw err; }
    if (stat) {
      if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error('unsafe typed-decision directory');
      return;
    }
    try { fs.mkdirSync(dir, { mode: 0o700 }); return; } catch (err) { if (!err || err.code !== 'EEXIST') throw err; }
  }
  throw new Error('typed-decision directory race');
}

function appendRecord(record) {
  const json = L.canonicalJson(record);
  if (Buffer.byteLength(json, 'utf8') > MAX_RECORD_BYTES) return false; // contract: at most 4096 bytes
  const root = L.td.defaultRoot();
  const file = L.td.recordsPath(root, DECISION, record.ts);
  fs.mkdirSync(path.dirname(root), { recursive: true, mode: 0o700 });
  ensurePrivateDir(root);
  ensurePrivateDir(path.join(root, DECISION));
  ensurePrivateDir(path.dirname(file));
  let stat = null;
  try { stat = fs.lstatSync(file); } catch (err) { if (!err || err.code !== 'ENOENT') throw err; }
  if (stat && (stat.isSymbolicLink() || !stat.isFile())) throw new Error('unsafe typed-decision file');
  const flags = fs.constants.O_WRONLY | fs.constants.O_APPEND | fs.constants.O_CREAT
    | (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0); // never block on a swapped-in FIFO
  const fd = fs.openSync(file, flags, 0o600);
  try { fs.writeSync(fd, json + '\n'); } finally { fs.closeSync(fd); }
  return true;
}

function readLayaRevision() {
  try {
    const doc = JSON.parse(fs.readFileSync(path.join(L.td.defaultRoot(), 'laya-runtime.json'), 'utf8'));
    if (doc && typeof doc.revision === 'string' && /^[A-Za-z0-9._-]{1,80}$/.test(doc.revision)) return doc.revision;
  } catch (_) { /* optional */ }
  return 'unknown';
}

function routerSourceSha256() {
  const lib = path.join(__dirname, 'lib');
  const hash = crypto.createHash('sha256');
  for (const file of [path.join(lib, 'route-core.js'), __filename, path.join(lib, 'laya-instrument.js')]) {
    hash.update(fs.readFileSync(file));
  }
  return hash.digest('hex');
}

function buildRecord(state, plan, laya, shown) {
  return {
    schema: L.td.RECORD_SCHEMA,
    decision: DECISION,
    decisionId: crypto.randomBytes(16).toString('hex'),
    occurrenceKey: L.td.occurrenceKey(plan.sessionHash, plan.promptHash, state.ts),
    ts: state.ts,
    host: state.host,
    basis: 'live',
    sourceStratum: 'fired',
    sessionHash: plan.sessionHash,
    promptHash: plan.promptHash,
    promptLengthBucket: plan.built.promptLengthBucket,
    routerSourceSha256: routerSourceSha256(),
    indexSha256: L.sha256Hex(JSON.stringify(state.routerIndex)),
    registryRevision: plan.config.registryRevision,
    policy: L.td.POLICY_COSIGN,
    policySha256: L.td.policySha256(),
    instrument: L.INSTRUMENT,
    instrumentSha256: plan.built.instrumentSha256,
    criteriaSha256: plan.built.criteriaSha256,
    layaRevision: readLayaRevision(),
    mode: plan.config.mode,
    arm: plan.arm,
    propensity: plan.propensity,
    incumbent: { skillId: state.match.skillId, score: state.match.score },
    shortlist: plan.shortlist,
    laya: {
      status: laya.status, choice: laya.choice, probabilities: laya.probabilities,
      latencyMs: laya.latencyMs, truncated: laya.truncated,
    },
    emitted: shown,
  };
}

function persist(state, plan, laya, emitted, shown) {
  try {
    const typed = plan && laya ? {
      typed_mode: plan.config.mode,
      typed_arm: plan.arm,
      typed_status: laya.status,
      typed_agrees: laya.status === 'ok' ? laya.choice === state.match.skillId : null,
    } : { typed_mode: null, typed_arm: null, typed_status: null, typed_agrees: null };
    // A non-user Codex thread (guardian review, subagent, automation) leaves no legacy row either: a
    // `suggested: null` row reads as a silence sample, and this is machine traffic (workflow message only).
    if (state.machineThread) {
      // nothing to log
    } else if (emitted) {
      logSuggestion({
        ts: state.ts,
        session_id: state.sessionId,
        hook: 'router',
        suggested: shown,
        context_hash: state.contextHash,
        ...typed,
        host: state.host,
      });
    } else if (!state.observer && Math.random() < 1 / 20) {
      logSuggestion({
        ts: state.ts,
        session_id: state.sessionId,
        hook: 'router',
        suggested: null,
        context_hash: state.contextHash,
        ...(plan && laya ? typed : {}),
        host: state.host,
      });
    }
  } catch (_) { /* fail-silent */ }
  try {
    if (plan && laya) appendRecord(buildRecord(state, plan, laya, shown));
  } catch (_) { /* fail-silent */ }
}

// ---------------------------------------------------------------- settle once

function emit(payload) {
  return new Promise((resolve) => {
    if (!payload) { resolve(); return; }
    try { process.stdout.write(payload, () => resolve()); } catch (_) { resolve(); }
  });
}

async function finalize(state, plan, laya) {
  let payload = state.incumbentPayload;
  let shown = state.incumbentShown;
  try {
    if (plan && laya && plan.config.mode === 'cosign' && plan.arm === 'treatment'
        && laya.status === 'ok' && laya.choice !== state.match.skillId) {
      payload = state.suppressedPayload;
      shown = null;
    }
  } catch (_) { payload = state.incumbentPayload; shown = state.incumbentShown; }
  await emit(payload); // flush BEFORE any persistence or exit
  persist(state, plan, laya, Boolean(payload), shown);
  try { if (plan && plan.probeCache) L.client.commitProbeCache(plan.probeCache); } catch (_) { /* best effort */ }
}

let fatalHandler = null;
function onFatal() {
  try { if (fatalHandler) { fatalHandler(); return; } } catch (_) { /* fall through */ }
  process.exit(0);
}

async function main() {
  process.stdout.on('error', () => { /* EPIPE etc.: never crash the hook */ });
  process.on('uncaughtException', onFatal);
  process.on('unhandledRejection', onFatal);

  let state = null;
  try {
    const raw = fs.readFileSync(0, 'utf8');
    const data = JSON.parse(raw);
    // A packaged run is opt-in and defers to a manual registration: otherwise exit silently, before
    // the workflow bridge, Laya, any decision record or any legacy suggestion-log row.
    if (PACKAGED && !packagedMayRun(data)) { process.exit(0); return; }
    state = prepare(raw, data);
  } catch (_err) {
    state = null; // fail-silent contract: never surface an error to the user or Claude
  }
  if (!state) { process.exit(0); return; }

  // The Laya budget starts BEFORE the optional preparation (registry/state/map reads, request
  // building), so that work counts against it; the reads are small local files.
  const optionalStartedAt = performance.now();
  let plan = null;
  if (state.eligible) {
    try { plan = planLaya(state); } catch (_) { plan = null; }
  }

  let settled = false;
  let backstop = null;
  let hardExit = null;
  const settleOnce = (laya) => {
    if (settled) return; // a late Laya completion after settlement is ignored
    settled = true;
    if (backstop) clearTimeout(backstop);
    finalize(state, plan, laya)
      .catch(() => {})
      .then(() => { if (hardExit) clearTimeout(hardExit); process.exit(0); });
  };

  if (!plan) {
    // Nothing to ask Laya (ineligible prompt, mode off, or no buildable request): emit the incumbent.
    fatalHandler = () => settleOnce(null);
    hardExit = setTimeout(() => process.exit(0), NON_LAYA_HARD_EXIT_MS);
    settleOnce(null);
    return;
  }

  const budget = plan.config.latencyBudgetMs;
  const startedAt = optionalStartedAt;
  const deadlineAt = startedAt + budget;
  const elapsed = () => Math.max(0, Math.round((performance.now() - startedAt) * 10) / 10);
  const untilDeadline = () => Math.max(0, deadlineAt - performance.now());
  // Plain literals (no helper that could throw) for every fallback path.
  const failed = (status) => ({
    status, choice: null, probabilities: null, latencyMs: elapsed(), truncated: plan.built.truncated === true,
  });
  fatalHandler = () => settleOnce(failed('unavailable'));
  hardExit = setTimeout(() => process.exit(0), untilDeadline() + SETTLE_MARGIN_MS + HARD_EXIT_MARGIN_MS);
  backstop = setTimeout(() => settleOnce(failed('timeout')), untilDeadline() + SETTLE_MARGIN_MS);

  let outcome;
  try {
    const raw = await L.client.callChoice({
      endpoint: plan.config.endpoint,
      model: plan.config.model,
      request: plan.built.request,
      keyMap: plan.built.keyMap,
      deadlineAt,
      deferProbeCache: true, // the cache write is synchronous I/O: do it after the flush (finalize)
    });
    if (raw && raw.probeCache) plan.probeCache = raw.probeCache;
    outcome = normalizeLaya(raw, plan);
  } catch (_) {
    outcome = failed('unavailable');
  }
  settleOnce(outcome);
}

if (require.main === module) main();

module.exports = {
  COSIGN_HOSTS, detectHost, readCodexThread, sessionIdentity, packagedConfigEnabled, hasManualRegistration,
  packagedMayRun, capModeForHost, isManualRouterCommand, claudeSettingsDirs,
};
