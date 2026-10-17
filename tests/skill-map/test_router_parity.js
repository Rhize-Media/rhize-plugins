#!/usr/bin/env node
// Claude/Codex parity for rhize-context-manager/hooks/skill-router.js (plan 2026-10-11, section 7,
// rows F1, F2, F4, F5, F6): host detection precedence, the opt-in `--packaged` entry (config file,
// deference to a manual Claude registration), the Codex user-thread gate and session identity, the
// COSIGN_HOSTS cap, and the hooks.json / manifest shape. Every spawned case runs the REAL hook with a
// throw-away HOME, XDG_DATA_HOME (so no real workflow bridge state is touched), typed-decisions root,
// suggestion log and a stub Laya server on 127.0.0.1. Standalone: exits non-zero on any failure.
'use strict';
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const PLUGIN = path.join(REPO, 'rhize-context-manager');
const ROUTER = path.join(PLUGIN, 'hooks', 'skill-router.js');
const LIB = path.join(PLUGIN, 'hooks', 'lib');
const router = require(ROUTER); // exports the pure helpers; requiring does not run the hook
const instrument = require(path.join(LIB, 'laya-instrument.js'));
const td = require(path.join(LIB, 'typed-decisions.js'));

const MODEL = 'typed-decisions';
const SKILL = {
  ctx: 'skill:alpha/context-pack',
  git: 'skill:alpha/git-helper',
  setup: 'skill:beta/tool-setup',
  review: 'skill:beta/code-review',
};
const DESCRIPTIONS = {
  [SKILL.ctx]: 'Pack project context for handoff.',
  [SKILL.git]: 'Git history and rebase help.',
  [SKILL.setup]: 'Install and configure dev tooling.',
  [SKILL.review]: 'Review a diff.',
};
const INDEX = {
  schemaVersion: '1.1.0', disclosure: {}, remediation: {}, succession: {},
  router: {
    extendsBases: {},
    signals: {
      [SKILL.ctx]: [{ kind: 'name', weight: 1, label: 'context-pack' }, { kind: 'tag', weight: 2, label: 'context' }, { kind: 'tag', weight: 2, label: 'git' }],
      [SKILL.git]: [{ kind: 'name', weight: 1, label: 'git-helper' }, { kind: 'tag', weight: 2, label: 'git' }, { kind: 'tag', weight: 2, label: 'rebase' }],
      [SKILL.setup]: [{ kind: 'name', weight: 1, label: 'tool-setup' }, { kind: 'tag', weight: 2, label: 'tooling' }],
      [SKILL.review]: [{ kind: 'name', weight: 1, label: 'code-review' }, { kind: 'tag', weight: 2, label: 'diff' }],
    },
  },
};
const MAP = {
  nodes: Object.keys(DESCRIPTIONS).map((id) => ({ id, kind: 'skill', name: id.split('/').pop(), description: DESCRIPTIONS[id] })),
  edges: [],
};
const PROMPT = 'help me get git and context tooling set up';
const INCUMBENT_MESSAGE = 'Consider the alpha:context-pack skill (matches context, git)';
const lineFor = (message) => JSON.stringify({ hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: message } }) + '\n';
const INCUMBENT_LINE = lineFor(INCUMBENT_MESSAGE);
const sha = (text) => crypto.createHash('sha256').update(text, 'utf8').digest('hex');
const MANUAL_COMMAND = 'node "/opt/rhize-plugins/rhize-context-manager/hooks/skill-router.js"';
const PACKAGED_COMMAND = 'node "${CLAUDE_PLUGIN_ROOT}/hooks/skill-router.js" --packaged';

// ---------------------------------------------------------------- harness

let failures = 0;
async function check(name, fn) {
  try {
    await fn();
    console.log(`PASS ${name}`);
  } catch (err) {
    failures += 1;
    console.error(`FAIL ${name}`);
    console.error(err && err.stack ? err.stack : err);
  }
}

const cleanup = [];
function stateDoc(mode) {
  return {
    schemaVersion: 1, revision: 3, updatedAt: '2026-10-11T12:00:00Z',
    decisions: {
      'skill-fit': {
        mode, pinned: false, since: '2026-10-11T12:00:00Z', reason: 'test_setup',
        policySha256: mode === 'cosign' ? td.policySha256() : null,
        instrumentSha256: mode === 'cosign' ? instrument.instrumentSha256() : null,
        layaRevision: null, cohortId: null,
      },
    },
  };
}

// opts: mode (writes registry-state.json) | endpoint | optin (true | raw string | false) | workflow | env
function scenario(opts = {}) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'router-parity-'));
  cleanup.push(home);
  const root = path.join(home, 'typed');
  const xdg = path.join(home, 'xdg');
  const ctxDir = path.join(home, '.claude', 'context-manager');
  fs.mkdirSync(ctxDir, { recursive: true });
  fs.mkdirSync(xdg, { recursive: true });
  fs.writeFileSync(path.join(ctxDir, 'skill-map.indexes.json'), JSON.stringify(INDEX));
  fs.writeFileSync(path.join(ctxDir, 'skill-map.static.json'), JSON.stringify(MAP));
  if (opts.mode) {
    fs.mkdirSync(root, { recursive: true });
    fs.writeFileSync(path.join(root, 'registry-state.json'), JSON.stringify(stateDoc(opts.mode)));
  }
  if (opts.optin !== undefined && opts.optin !== false) {
    const cfg = path.join(xdg, 'rhize', 'skill-router', 'config.json');
    fs.mkdirSync(path.dirname(cfg), { recursive: true });
    fs.writeFileSync(cfg, typeof opts.optin === 'string' ? opts.optin : JSON.stringify({ schemaVersion: 1, enabled: true }));
  }
  if (opts.workflow) {
    const cfg = path.join(xdg, 'rhize', 'workflow-selection', 'config.json');
    fs.mkdirSync(path.dirname(cfg), { recursive: true });
    fs.writeFileSync(cfg, JSON.stringify({ schemaVersion: 1, enabled: true }));
  }
  const env = {
    ...process.env, HOME: home, XDG_DATA_HOME: xdg, RHIZE_TYPED_DECISIONS_ROOT: root,
    RHIZE_SUGGESTION_LOG: path.join(home, 'suggestion-log.jsonl'), PYTHONDONTWRITEBYTECODE: '1', ...(opts.env || {}),
  };
  // The host environment (this suite may itself run under Claude Code or Codex) must not leak host evidence.
  for (const name of ['RHIZE_HOST', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME']) {
    if (!(opts.env && Object.prototype.hasOwnProperty.call(opts.env, name))) delete env[name];
  }
  if (opts.endpoint) { env.RHIZE_LAYA_ENDPOINT = opts.endpoint; env.RHIZE_LAYA_ENDPOINT_AUTHORITY = '1'; }
  else { delete env.RHIZE_LAYA_ENDPOINT; delete env.RHIZE_LAYA_ENDPOINT_AUTHORITY; }
  return { home, root, xdg, logPath: env.RHIZE_SUGGESTION_LOG, env };
}

function runHook(sc, payload, { packaged = false } = {}) {
  return new Promise((resolve) => {
    const args = packaged ? [ROUTER, '--packaged'] : [ROUTER];
    const child = spawn(process.execPath, args, { env: sc.env, stdio: ['pipe', 'pipe', 'pipe'], cwd: sc.home });
    let stdout = ''; let stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    const killer = setTimeout(() => child.kill('SIGKILL'), 15000);
    child.on('close', (code) => { clearTimeout(killer); resolve({ code, stdout, stderr }); });
    child.stdin.end(typeof payload === 'string' ? payload : JSON.stringify({ prompt: PROMPT, ...payload }));
  });
}

function readRecords(sc) {
  const dir = path.join(sc.root, 'skill-fit', 'records');
  let names = [];
  try { names = fs.readdirSync(dir).filter((n) => n.endsWith('.jsonl')); } catch (_e) { return []; }
  return names.flatMap((n) => fs.readFileSync(path.join(dir, n), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)));
}
function readLog(sc) {
  try { return fs.readFileSync(sc.logPath, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)); } catch (_e) { return []; }
}
function validate(sc) {
  const dir = path.join(sc.root, 'skill-fit', 'records');
  const code = 'import sys,json; sys.path.insert(0,"rhize-context-manager/scripts"); from typed_decisions import contract; '
    + '[contract.validate_record(json.loads(l)) for l in open(sys.argv[1])]';
  for (const name of fs.readdirSync(dir)) {
    const r = spawnSync('python3', ['-c', code, path.join(dir, name)], { cwd: REPO, encoding: 'utf8' });
    assert.strictEqual(r.status, 0, `contract.validate_record rejected a record:\n${r.stderr}`);
  }
}
function assertSilent(sc, res, server, requestsBefore) {
  assert.strictEqual(res.code, 0, res.stderr);
  assert.strictEqual(res.stdout, '');
  assert.strictEqual(res.stderr, '');
  assert.strictEqual(server.hits.health + server.hits.post, requestsBefore, 'no Laya request');
  assert.strictEqual(readRecords(sc).length, 0, 'no decision record');
  assert.ok(!fs.existsSync(sc.logPath), 'no legacy suggestion-log row');
}

// ---- Codex rollouts
function writeRollout(sc, firstLine, { dir = 'sessions', name = null, padBytes = 0 } = {}) {
  const day = path.join(sc.home, '.codex', dir, '2026', '10', '11');
  fs.mkdirSync(day, { recursive: true });
  const file = path.join(day, name || `rollout-2026-10-11T00-00-00-${crypto.randomUUID()}.jsonl`);
  const first = typeof firstLine === 'string' ? firstLine : JSON.stringify(firstLine);
  fs.writeFileSync(file, `${first}\n${padBytes ? `${JSON.stringify({ type: 'event_msg', pad: 'x'.repeat(padBytes) })}\n` : ''}`);
  return file;
}
const meta = (source, extra = {}) => ({ type: 'session_meta', payload: { id: `meta-${source}`, thread_source: source, ...extra } });

// ---- stub Laya
function keyFor(request, skillName) {
  for (const [key, text] of Object.entries(request.questions.skill.criteria)) {
    if (key !== 'none' && (text === skillName || text.startsWith(`${skillName}:`))) return key;
  }
  return 'none';
}
function layaServer(choose = () => 'context-pack') {
  const hits = { health: 0, post: 0, requests: [] };
  const sockets = new Set();
  const server = http.createServer((req, res) => {
    if (req.method === 'GET' && req.url === '/health') {
      hits.health += 1;
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify({ status: 'ok', loaded: [MODEL] }));
    }
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      hits.post += 1;
      const request = JSON.parse(body);
      hits.requests.push(request);
      const skillName = choose(request);
      const key = skillName === 'none' ? 'none' : keyFor(request, skillName);
      const keys = Object.keys(request.questions.skill.criteria);
      const probabilities = {};
      for (const k of keys) probabilities[k] = k === key ? 0.7 : 0.3 / (keys.length - 1);
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ routing: { model: MODEL }, answers: { skill: { type: 'choice', choice: key, probabilities } } }));
    });
    return undefined;
  });
  server.on('connection', (s) => { sockets.add(s); s.on('close', () => sockets.delete(s)); });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => {
    const { port } = server.address();
    resolve({
      endpoint: `http://127.0.0.1:${port}`, hits,
      close: () => new Promise((done) => { for (const s of sockets) s.destroy(); server.close(() => done()); }),
    });
  }));
}
function sessionForArm(arm, holdback = 0.1) {
  for (let i = 0; i < 5000; i += 1) {
    const id = `parity-${arm}-${i}`;
    if (td.armFor(sha(id), sha(PROMPT), holdback) === arm) return id;
  }
  throw new Error('no session found');
}
const TREATMENT = sessionForArm('treatment');

// ---------------------------------------------------------------- tests

(async () => {
  // ------------------------------------------------ host detection (pure)
  const HOME = '/home/tester';
  const codexRollout = `${HOME}/.codex/sessions/2026/10/11/rollout-2026-10-11T00-00-00-abc.jsonl`;
  const archivedRollout = `${HOME}/.codex/archived_sessions/rollout-2026-10-11T00-00-00-abc.jsonl`;
  const claudeTranscript = `${HOME}/.claude/projects/-work-app/0b1c.jsonl`;
  const detect = (payload, env = {}) => router.detectHost(payload, env, HOME);
  const detectionCases = [
    ['no evidence defaults to claude (legacy)', {}, {}, 'claude'],
    ['non-object payload defaults to claude', null, {}, 'claude'],
    ['explicit RHIZE_HOST=codex wins', { transcript_path: claudeTranscript }, { RHIZE_HOST: 'codex', CLAUDE_CODE_ENTRYPOINT: 'cli' }, 'codex'],
    ['explicit RHIZE_HOST=claude wins', { transcript_path: codexRollout, thread_id: 't' }, { RHIZE_HOST: 'claude' }, 'claude'],
    ['an invalid RHIZE_HOST is ignored (falls to transcript_path)', { transcript_path: codexRollout }, { RHIZE_HOST: 'CODEX' }, 'codex'],
    ['an invalid RHIZE_HOST is ignored (no evidence -> claude)', {}, { RHIZE_HOST: 'something-else' }, 'claude'],
    ['an empty RHIZE_HOST is ignored', { thread_id: 'th' }, { RHIZE_HOST: '' }, 'codex'],
    ['transcript under ~/.codex/sessions rollout-*.jsonl -> codex', { transcript_path: codexRollout }, {}, 'codex'],
    ['transcript under ~/.codex/archived_sessions -> codex', { transcript_path: archivedRollout }, {}, 'codex'],
    ['codex transcript outranks CLAUDE_CODE_ENTRYPOINT leaking into a child process', { transcript_path: codexRollout }, { CLAUDE_CODE_ENTRYPOINT: 'cli' }, 'codex'],
    ['codex transcript outranks a missing thread_id', { transcript_path: codexRollout, thread_id: 7 }, {}, 'codex'],
    ['transcript under ~/.claude/projects -> claude', { transcript_path: claudeTranscript }, {}, 'claude'],
    ['claude transcript outranks a stray thread_id', { transcript_path: claudeTranscript, thread_id: 'th' }, {}, 'claude'],
    ['a ~/.codex/sessions file that is not rollout-*.jsonl is no codex evidence', { transcript_path: `${HOME}/.codex/sessions/x/notes.jsonl` }, { CLAUDE_CODE_ENTRYPOINT: 'cli' }, 'claude'],
    ['..-traversal out of the codex root is no codex evidence', { transcript_path: `${HOME}/.codex/sessions/../../x/rollout-a.jsonl` }, {}, 'claude'],
    ['another home\'s codex root is no evidence', { transcript_path: '/home/other/.codex/sessions/rollout-a.jsonl' }, {}, 'claude'],
    ['a relative transcript_path is no evidence', { transcript_path: '.codex/sessions/rollout-a.jsonl' }, {}, 'claude'],
    ['an unknown transcript location falls through to thread_id', { transcript_path: '/tmp/t.jsonl', thread_id: 'th-1' }, {}, 'codex'],
    ['thread_id alone -> codex', { thread_id: 'th-1' }, {}, 'codex'],
    ['CLAUDE_CODE_ENTRYPOINT alone -> claude', {}, { CLAUDE_CODE_ENTRYPOINT: 'cli' }, 'claude'],
    ['thread_id and CLAUDE_CODE_ENTRYPOINT conflict -> unknown', { thread_id: 'th-1' }, { CLAUDE_CODE_ENTRYPOINT: 'cli' }, 'unknown'],
    ['an empty thread_id is no evidence', { thread_id: '' }, { CLAUDE_CODE_ENTRYPOINT: 'cli' }, 'claude'],
    ['an empty CLAUDE_CODE_ENTRYPOINT is no evidence', { thread_id: 'th-1' }, { CLAUDE_CODE_ENTRYPOINT: '' }, 'codex'],
  ];
  for (const [name, payload, env, expected] of detectionCases) {
    await check(`host detection: ${name}`, async () => assert.strictEqual(detect(payload, env), expected));
  }
  await check('host detection: COSIGN_HOSTS is claude only', async () => assert.deepStrictEqual(router.COSIGN_HOSTS, ['claude']));

  // ------------------------------------------------ manual-registration recognition (pure)
  const manualCommandCases = [
    [MANUAL_COMMAND, true],
    ['node "${CLAUDE_PLUGIN_ROOT}/hooks/skill-router.js"', true],
    ['/opt/homebrew/bin/node "$HOME/dev/rhize-context-manager/hooks/skill-router.js"', true],
    ['FOO=1 exec node --no-warnings /x/hooks/skill-router.js --quiet', true],
    ['node --require ./preload.js /x/skill-router.js', true],
    ['node -- /x/skill-router.js', true],
    ['cd /x && node hooks/skill-router.js', true],
    ['node /x/skill-router.js 2>/dev/null; true', true],
    ['node /x/skill-router.js && echo --packaged', true],
    ["bash -lc 'node /x/skill-router.js'", true],
    ["/bin/bash -o pipefail -c 'node /x/skill-router.js | cat'", true],
    ["zsh +o nomatch -lc \"node '/x/skill-router.js'\"", true],
    ['$(node /x/skill-router.js)', true],
    ['# node /x/skill-router.js', false],
    ['# Disabled: cd /x && node hooks/skill-router.js', false],
    ['/usr/bin/env node /x/skill-router.js', true],
    ['env -u NODE_OPTIONS node /x/skill-router.js', true],
    ['/usr/bin/env -C /tmp -i node /x/skill-router.js', true],
    ['nice -n 5 node /x/skill-router.js', true],
    ['exec -a router node /x/skill-router.js', true],
    ['command -v node /x/skill-router.js', false],
    ['node 2>/dev/null /x/skill-router.js', true],
    ['node 2>&1 /x/skill-router.js', true],
    ['node /x/skill-router.js > /dev/null 2>&1', true],
    ['>/dev/null node /x/skill-router.js', true],
    ['node /x/skill-router.js &>/dev/null --packaged', false],
    ['node /x/skill-router.js 2> /tmp/err.log --packaged', false],
    // Fable final review: glued redirections, more wrappers, compound commands.
    ['node /x/skill-router.js>/dev/null', true],
    ['node /x/skill-router.js&>/dev/null', true],
    ['node /x/skill-router.js 2>&1>/dev/null', true],
    ['node /x/skill-router.js>/dev/null --packaged', false],
    ['node "/x/a>b/skill-router.js"', true],
    ['timeout 10 node /x/skill-router.js', true],
    ['timeout -k 2 10s node /x/skill-router.js', true],
    ['mise exec -- node /x/skill-router.js', true],
    ['mise x -C /tmp -- node /x/skill-router.js', true],
    ['arch -arm64 node /x/skill-router.js', true],
    ['nice --adjustment 5 node /x/skill-router.js', true],
    ['if [ -f /x/skill-router.js ]; then node /x/skill-router.js; fi', true],
    ['{ node /x/skill-router.js; }', true],
    ['nohup echo node /x/skill-router.js', false],
    ['timeout 10 cat /x/skill-router.js', false],
    ['timeout 10 123 node /x/skill-router.js', false],      // timeout runs `123`, not node
    ['timeout 10 nice 5 node /x/skill-router.js', true],
    ['if true; then echo /x/skill-router.js; fi', false],
    // Codex round 4: a quoted -c string that starts with a redirection is still parsed.
    ["bash -c '>/dev/null node /x/skill-router.js'", true],
    ["bash -c '2>&1 node /x/skill-router.js --packaged'", false],
    ['node /x/skill-router.js ">"', true],
    ['node /x/skill-router.js ">" --packaged', false],
    ['node 2 > /dev/null /x/skill-router.js', false],     // `2` is node's script argument here, not an fd
    ['node /x/skill-router.js # --packaged', true],          // a comment is not an argument
    ['node /x/skill-router.js a#--packaged', true],          // # inside a word is not a comment
    ['true # comment\nnode /x/skill-router.js', true],
    ['echo hi # node /x/skill-router.js', false],
    ["sh -c 'sh -c \"sh -c \\'node /x/skill-router.js\\'\"'", false],
    ['env -i PATH=/usr/bin node /x/skill-router.js', true],
    // The live manual entry shape on the pilot Mac (PATH assignment prefix, unquoted $HOME script path).
    ['PATH="$HOME/.local/share/mise/shims:/opt/homebrew/bin:$PATH" node $HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-context-manager/hooks/skill-router.js', true],
    [PACKAGED_COMMAND, false],
    ['node /x/skill-router.js --quiet --packaged', false],
    ['node /x/other.js /x/skill-router.js', false],
    ['node --require /x/skill-router.js /x/other.js', false],
    ['node -e "require(1)" /x/skill-router.js', false],
    ['echo node /x/skill-router.js', false],
    ['echo skill-router.js', false],
    ['grep -c skill-router.js ~/.claude/context-manager/suggestion-log.jsonl', false],
    ['node /x/skill-router.jsx', false],
    ['node /x/session-disclosure.js', false],
    ["bash -lc 'node /x/skill-router.js --packaged'", false],
    ['bash /x/skill-router.js', false],
    ['', false],
    [null, false],
    [`node /x/skill-router.js ${'a'.repeat(9000)}`, false],
  ];
  for (const [command, expected] of manualCommandCases) {
    const label = typeof command === 'string' ? command.slice(0, 80) : String(command);
    await check(`manual command recognition: ${label} -> ${expected}`, async () => {
      assert.strictEqual(router.isManualRouterCommand(command), expected);
    });
  }

  // ------------------------------------------------ hooks.json and manifest
  await check('hooks.json: existing entries unchanged, packaged router opt-in, exactly two bounded credential entries', async () => {
    const current = JSON.parse(fs.readFileSync(path.join(PLUGIN, 'hooks', 'hooks.json'), 'utf8'));
    const git = spawnSync('git', ['show', 'HEAD:rhize-context-manager/hooks/hooks.json'], { cwd: REPO, encoding: 'utf8' });
    assert.strictEqual(git.status, 0, git.stderr);
    const head = JSON.parse(git.stdout);
    const credential = (group) => group.hooks.some((hook) => /\/hooks\/credential-workflow(?:-prompt)?\.js/.test(hook.command));
    const entries = current.hooks.UserPromptSubmit.filter((group) => !credential(group));
    assert.strictEqual(entries.length, 4);
    assert.deepStrictEqual(entries.slice(0, 3), head.hooks.UserPromptSubmit.filter((group) => !credential(group)).slice(0, 3));
    assert.deepStrictEqual(entries[3], { hooks: [{ type: 'command', command: PACKAGED_COMMAND, timeout: 10 }] });
    for (const event of Object.keys(head.hooks)) {
      if (event !== 'UserPromptSubmit') assert.deepStrictEqual(current.hooks[event].filter((group) => !credential(group)),
        head.hooks[event].filter((group) => !credential(group)), event);
    }
    assert.strictEqual(current.hooks.UserPromptSubmit.filter(credential).length, 1);
    assert.strictEqual(current.hooks.PreToolUse.filter(credential).length, 1);
    assert.strictEqual(current.hooks.PreToolUse.find(credential).matcher, '*');
    assert.deepStrictEqual(Object.keys(current.hooks), Object.keys(head.hooks));
    assert.strictEqual(current.description, head.description);
  });
  await check('setup manifest: skill-router keeps its keys and describes the packaged, opt-in wiring', async () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(PLUGIN, 'setup', 'manifest.json'), 'utf8'));
    const entry = manifest.items.find((h) => h.id === 'skill-router');
    assert.ok(entry, 'skill-router entry');
    assert.deepStrictEqual(Object.keys(entry), ['id', 'title', 'tier', 'event', 'command', 'description', 'default']);
    assert.strictEqual(entry.default, false);
    assert.strictEqual(entry.command, 'node "${CLAUDE_PLUGIN_ROOT}/hooks/skill-router.js"');
    for (const needle of ['hooks/hooks.json', 'packaged', 'opt-in', 'skill-router/config.json', 'legacy', 'defers']) {
      assert.ok(entry.description.includes(needle), `description mentions ${needle}`);
    }
  });

  // ------------------------------------------------ packaged gating
  const server = await layaServer();
  const sessionFor = (label) => ({ session_id: `${label}-${crypto.randomUUID()}` });
  const settingsWith = (command) => JSON.stringify({ hooks: { UserPromptSubmit: [{ hooks: [{ type: 'command', command }] }] } });
  const put = (file, text) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, text); };

  await check('packaged, config absent -> silent (no bridge, Laya, record or legacy row)', async () => {
    const sc = scenario({ endpoint: server.endpoint, workflow: true });
    const before = server.hits.health + server.hits.post;
    assertSilent(sc, await runHook(sc, sessionFor('p'), { packaged: true }), server, before);
    assert.ok(!fs.existsSync(path.join(sc.xdg, 'rhize', 'workflow-selection', 'receipts')), 'workflow bridge did not run');
  });

  const badConfigs = {
    'enabled false': () => JSON.stringify({ schemaVersion: 1, enabled: false }),
    'enabled is the string "true"': () => JSON.stringify({ schemaVersion: 1, enabled: 'true' }),
    'schemaVersion 2': () => JSON.stringify({ schemaVersion: 2, enabled: true }),
    'schemaVersion missing': () => JSON.stringify({ enabled: true }),
    'invalid JSON': () => '{broken',
    'a JSON array': () => '[{"schemaVersion":1,"enabled":true}]',
    'larger than 16 KiB': () => JSON.stringify({ schemaVersion: 1, enabled: true, pad: 'x'.repeat(17 * 1024) }),
  };
  for (const [label, body] of Object.entries(badConfigs)) {
    await check(`packaged, config ${label} -> silent`, async () => {
      const sc = scenario({ endpoint: server.endpoint, optin: body() });
      const before = server.hits.health + server.hits.post;
      assertSilent(sc, await runHook(sc, sessionFor('p'), { packaged: true }), server, before);
    });
  }
  await check('packaged, config.json is a symlink or a directory -> silent', async () => {
    for (const kind of ['symlink', 'directory']) {
      const sc = scenario({ endpoint: server.endpoint });
      const cfg = path.join(sc.xdg, 'rhize', 'skill-router', 'config.json');
      fs.mkdirSync(path.dirname(cfg), { recursive: true });
      if (kind === 'symlink') {
        const real = path.join(sc.home, 'real-config.json');
        fs.writeFileSync(real, JSON.stringify({ schemaVersion: 1, enabled: true }));
        fs.symlinkSync(real, cfg);
      } else {
        fs.mkdirSync(cfg);
      }
      const before = server.hits.health + server.hits.post;
      assertSilent(sc, await runHook(sc, sessionFor('p'), { packaged: true }), server, before);
    }
  });
  await check('packaged, config at the 16 KiB limit with extra keys still enables', async () => {
    const body = JSON.stringify({ schemaVersion: 1, enabled: true, note: 'x'.repeat(100) });
    const sc = scenario({ endpoint: server.endpoint, optin: body });
    const res = await runHook(sc, sessionFor('p'), { packaged: true });
    assert.strictEqual(res.stdout, INCUMBENT_LINE);
  });

  await check('packaged, config on, no manual entry -> runs: incumbent emitted, Laya co-signed, one claude record', async () => {
    const sc = scenario({ endpoint: server.endpoint, optin: true });
    const before = server.hits.post;
    const sid = sessionFor('p');
    const res = await runHook(sc, sid, { packaged: true });
    assert.strictEqual(res.code, 0, res.stderr);
    assert.strictEqual(res.stdout, INCUMBENT_LINE);
    assert.strictEqual(server.hits.post, before + 1);
    const [rec] = readRecords(sc);
    assert.strictEqual(readRecords(sc).length, 1);
    assert.strictEqual(rec.host, 'claude');
    assert.strictEqual(rec.sessionHash, sha(sid.session_id));
    validate(sc);
    const [row] = readLog(sc);
    assert.strictEqual(row.host, 'claude');
    assert.strictEqual(row.session_id, sid.session_id);
  });

  const manualPlaces = [
    ['~/.claude/settings.json', (sc) => path.join(sc.home, '.claude', 'settings.json'), {}],
    ['~/.claude/settings.local.json', (sc) => path.join(sc.home, '.claude', 'settings.local.json'), {}],
    ['<cwd>/.claude/settings.json', (sc) => path.join(sc.home, 'proj', '.claude', 'settings.json'), { cwd: true }],
    ['<cwd>/.claude/settings.local.json', (sc) => path.join(sc.home, 'proj', '.claude', 'settings.local.json'), { cwd: true }],
  ];
  for (const [label, where, { cwd }] of manualPlaces) {
    await check(`packaged (claude) defers to a manual registration in ${label}: silent, no Laya request`, async () => {
      const sc = scenario({ endpoint: server.endpoint, optin: true });
      put(where(sc), settingsWith(MANUAL_COMMAND));
      const payload = { ...sessionFor('p'), ...(cwd ? { cwd: path.join(sc.home, 'proj') } : {}) };
      const before = server.hits.health + server.hits.post;
      assertSilent(sc, await runHook(sc, payload, { packaged: true }), server, before);
    });
  }
  await check('packaged (claude) defers to a manual UserPromptSubmit entry through a symlinked settings.json', async () => {
    const sc = scenario({ endpoint: server.endpoint, optin: true });
    const real = path.join(sc.home, 'dotfiles-settings.json');
    fs.writeFileSync(real, JSON.stringify({ theme: 'dark', hooks: { UserPromptSubmit: [{ matcher: '', hooks: [{ type: 'command', command: `FOO=1 ${MANUAL_COMMAND} --quiet` }] }] } }));
    fs.symlinkSync(real, path.join(sc.home, '.claude', 'settings.json'));
    const before = server.hits.health + server.hits.post;
    assertSilent(sc, await runHook(sc, sessionFor('p'), { packaged: true }), server, before);
  });
  await check('packaged (claude) does NOT defer to a router command under another event or a mere mention (no zero-run)', async () => {
    const cases = {
      'Stop event': JSON.stringify({ hooks: { Stop: [{ hooks: [{ type: 'command', command: MANUAL_COMMAND }] }] } }),
      'SessionStart event': JSON.stringify({ hooks: { SessionStart: [{ hooks: [{ type: 'command', command: MANUAL_COMMAND }] }] } }),
      'echo mention': settingsWith('echo skill-router.js'),
      'grep mention': settingsWith('grep -c skill-router.js ~/.claude/context-manager/suggestion-log.jsonl'),
    };
    for (const [label, text] of Object.entries(cases)) {
      const sc = scenario({ endpoint: server.endpoint, optin: true });
      put(path.join(sc.home, '.claude', 'settings.json'), text);
      const res = await runHook(sc, sessionFor('p'), { packaged: true });
      assert.strictEqual(res.stdout, INCUMBENT_LINE, label);
      assert.strictEqual(readRecords(sc).length, 1, label);
    }
  });
  await check('packaged (claude) defers to a manual entry in a project root ABOVE cwd (no double run)', async () => {
    const sc = scenario({ endpoint: server.endpoint, optin: true });
    put(path.join(sc.home, 'proj', '.claude', 'settings.json'), settingsWith(MANUAL_COMMAND));
    fs.mkdirSync(path.join(sc.home, 'proj', 'src', 'deep'), { recursive: true });
    const payload = { ...sessionFor('p'), cwd: path.join(sc.home, 'proj', 'src', 'deep') };
    const before = server.hits.health + server.hits.post;
    assertSilent(sc, await runHook(sc, payload, { packaged: true }), server, before);
  });
  await check('packaged (claude) ignores settings it cannot use: invalid JSON, oversize, packaged-only command, unrelated hooks, wrong key', async () => {
    const cases = {
      'invalid JSON': '{not json',
      oversize: JSON.stringify({ pad: 'x'.repeat(1100 * 1024), hooks: { UserPromptSubmit: [{ hooks: [{ command: MANUAL_COMMAND }] }] } }),
      'packaged-only command': settingsWith(PACKAGED_COMMAND),
      'unrelated hook': settingsWith('node "/x/hooks/session-disclosure.js"'),
      'not under hooks': JSON.stringify({ permissions: { allow: [`Bash(${MANUAL_COMMAND})`] }, command: MANUAL_COMMAND }),
    };
    for (const [label, text] of Object.entries(cases)) {
      const sc = scenario({ endpoint: server.endpoint, optin: true });
      put(path.join(sc.home, '.claude', 'settings.json'), text);
      const res = await runHook(sc, sessionFor('p'), { packaged: true });
      assert.strictEqual(res.stdout, INCUMBENT_LINE, label);
      assert.strictEqual(readRecords(sc).length, 1, label);
    }
  });
  await check('manual (non-packaged) run is unchanged: runs without the opt-in config, ignores settings.json', async () => {
    const sc = scenario({ endpoint: server.endpoint });
    put(path.join(sc.home, '.claude', 'settings.json'), settingsWith(MANUAL_COMMAND));
    const before = server.hits.post;
    const res = await runHook(sc, sessionFor('m'));
    assert.strictEqual(res.stdout, INCUMBENT_LINE);
    assert.strictEqual(server.hits.post, before + 1);
    assert.strictEqual(readRecords(sc).length, 1);
  });
  await check('packaged in codex ignores settings.json: a user thread still runs', async () => {
    const sc = scenario({ endpoint: server.endpoint, optin: true });
    put(path.join(sc.home, '.claude', 'settings.json'), settingsWith(MANUAL_COMMAND));
    const rollout = writeRollout(sc, meta('user', { id: 'codex-thread-1' }));
    const res = await runHook(sc, { transcript_path: rollout, thread_id: 'codex-thread-1' }, { packaged: true });
    assert.strictEqual(res.stdout, INCUMBENT_LINE);
    const [rec] = readRecords(sc);
    assert.strictEqual(readRecords(sc).length, 1);
    assert.strictEqual(rec.host, 'codex');
  });
  await check('packaged in codex still needs the opt-in config', async () => {
    const sc = scenario({ endpoint: server.endpoint });
    const rollout = writeRollout(sc, meta('user'));
    const before = server.hits.health + server.hits.post;
    assertSilent(sc, await runHook(sc, { transcript_path: rollout }, { packaged: true }), server, before);
  });

  // ------------------------------------------------ codex user-thread gate and identity
  await check('codex user thread: record host codex, sessionHash = sha256(session_meta.id), shadow, incumbent emitted', async () => {
    const sc = scenario({ endpoint: server.endpoint });
    const rollout = writeRollout(sc, meta('user', { id: '019e-meta-id', session_id: 'ignored-meta-session' }));
    const before = server.hits.post;
    const res = await runHook(sc, { transcript_path: rollout, session_id: 'hook-session', thread_id: 'hook-thread' });
    assert.strictEqual(res.code, 0, res.stderr);
    assert.strictEqual(res.stdout, INCUMBENT_LINE);
    assert.strictEqual(server.hits.post, before + 1);
    const recs = readRecords(sc);
    assert.strictEqual(recs.length, 1);
    const [rec] = recs;
    assert.strictEqual(rec.host, 'codex');
    assert.strictEqual(rec.sessionHash, sha('019e-meta-id'));
    assert.strictEqual(rec.promptHash, sha(PROMPT));
    assert.strictEqual(rec.occurrenceKey, td.occurrenceKey(rec.sessionHash, rec.promptHash, rec.ts));
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.emitted, SKILL.ctx);
    validate(sc);
    const [row] = readLog(sc);
    assert.strictEqual(row.host, 'codex');
    assert.strictEqual(row.session_id, '019e-meta-id');
  });
  await check('codex session identity falls back to payload session_id, then thread_id', async () => {
    const withSession = scenario({ endpoint: server.endpoint });
    const noId = meta('user'); delete noId.payload.id;
    const r1 = writeRollout(withSession, noId);
    await runHook(withSession, { transcript_path: r1, session_id: 'hook-session', thread_id: 'hook-thread' });
    assert.strictEqual(readRecords(withSession)[0].sessionHash, sha('hook-session'));
    const withThread = scenario({ endpoint: server.endpoint });
    const r2 = writeRollout(withThread, { type: 'session_meta', payload: { id: '', thread_source: 'user' } });
    await runHook(withThread, { transcript_path: r2, thread_id: 'hook-thread' });
    assert.strictEqual(readRecords(withThread)[0].sessionHash, sha('hook-thread'));
    assert.strictEqual(readLog(withThread)[0].session_id, 'hook-thread');
  });
  await check('codex user thread in archived_sessions, a big rollout, and a payload-only thread_source all pass the gate', async () => {
    for (const [label, build] of [
      ['archived_sessions', (sc) => writeRollout(sc, meta('user'), { dir: 'archived_sessions' })],
      ['rollout far larger than 512 KiB with a short first line', (sc) => writeRollout(sc, meta('user'), { padBytes: 1024 * 1024 })],
      ['first line without type but payload.thread_source', (sc) => writeRollout(sc, { payload: { id: 'x', thread_source: 'user' } })],
    ]) {
      const sc = scenario({ endpoint: server.endpoint });
      const res = await runHook(sc, { transcript_path: build(sc) });
      assert.strictEqual(res.stdout, INCUMBENT_LINE, label);
      assert.strictEqual(readRecords(sc)[0].host, 'codex', label);
    }
  });

  for (const source of ['guardian_review', 'subagent', 'automation', 'agent_created_thread', 'USER', '', null]) {
    await check(`codex thread_source ${JSON.stringify(source)} -> no suggestion, no Laya call, no record, no legacy row`, async () => {
      const sc = scenario({ endpoint: server.endpoint });
      const rollout = writeRollout(sc, meta(source));
      const before = server.hits.health + server.hits.post;
      assertSilent(sc, await runHook(sc, { transcript_path: rollout, session_id: 'x' }), server, before);
    });
  }
  // Each case: build(sc) writes its artefacts under the scenario HOME and returns the hook payload.
  const unusable = {
    'no transcript_path (explicit RHIZE_HOST=codex)': { env: { RHIZE_HOST: 'codex' }, build: () => ({}) },
    'missing file': { build: (sc) => ({ transcript_path: path.join(sc.home, '.codex', 'sessions', 'rollout-gone.jsonl') }) },
    'empty file': { build: (sc) => ({ transcript_path: writeRollout(sc, '') }) },
    'first line is not JSON': { build: (sc) => ({ transcript_path: writeRollout(sc, '{"type":"session_meta"') }) },
    'first line is not an object': { build: (sc) => ({ transcript_path: writeRollout(sc, '"user"') }) },
    'first line is another event': { build: (sc) => ({ transcript_path: writeRollout(sc, { type: 'event_msg', payload: { type: 'user_message' } }) }) },
    'session_meta without thread_source': { build: (sc) => ({ transcript_path: writeRollout(sc, { type: 'session_meta', payload: { id: 'x' } }) }) },
    'session_meta without payload': { build: (sc) => ({ transcript_path: writeRollout(sc, { type: 'session_meta' }) }) },
    'first line over 512 KiB': { build: (sc) => ({ transcript_path: writeRollout(sc, JSON.stringify({ ...meta('user'), pad: 'x'.repeat(520 * 1024) })) }) },
    'rollout is a symlink to a user thread': {
      build: (sc) => {
        const real = path.join(sc.home, 'elsewhere.jsonl');
        fs.writeFileSync(real, `${JSON.stringify(meta('user'))}\n`);
        const link = path.join(sc.home, '.codex', 'sessions', 'rollout-link.jsonl');
        fs.mkdirSync(path.dirname(link), { recursive: true });
        fs.symlinkSync(real, link);
        return { transcript_path: link };
      },
    },
    'rollout outside the Codex roots (explicit RHIZE_HOST=codex)': {
      env: { RHIZE_HOST: 'codex' },
      build: (sc) => {
        const file = path.join(sc.home, 'rollouts', 'rollout-2026-10-11T00-00-00-x.jsonl');
        put(file, `${JSON.stringify(meta('user'))}\n`);
        return { transcript_path: file };
      },
    },
    'transcript_path is a directory': {
      build: (sc) => {
        const dir = path.join(sc.home, '.codex', 'sessions', 'rollout-dir.jsonl');
        fs.mkdirSync(dir, { recursive: true });
        return { transcript_path: dir };
      },
    },
  };
  for (const [label, { env, build }] of Object.entries(unusable)) {
    await check(`codex gate fails closed: ${label} -> silent`, async () => {
      const sc = scenario({ endpoint: server.endpoint, env });
      const payload = { session_id: 'x', thread_id: 't', ...build(sc) };
      const before = server.hits.health + server.hits.post;
      assertSilent(sc, await runHook(sc, payload), server, before);
    });
  }
  await check('codex non-user thread with the workflow bridge on: no router suggestion, no Laya call, no record', async () => {
    const sc = scenario({ endpoint: server.endpoint, workflow: true });
    const rollout = writeRollout(sc, meta('guardian_review'));
    const before = server.hits.health + server.hits.post;
    const res = await runHook(sc, { transcript_path: rollout, session_id: 'x' });
    assert.strictEqual(res.code, 0, res.stderr);
    assert.ok(!res.stdout.includes('Consider the'), 'the router suggestion is never emitted for machine traffic');
    if (res.stdout) assert.ok(JSON.parse(res.stdout).hookSpecificOutput.additionalContext.startsWith('Workflow selection checkpoint'));
    assert.strictEqual(server.hits.health + server.hits.post, before);
    assert.strictEqual(readRecords(sc).length, 0);
    assert.strictEqual(readLog(sc).length, 0, 'a machine thread leaves no legacy row (a null row would read as a silence sample)');
  });
  await check('codex non-user thread behaves exactly like the background observer (same silent outcome)', async () => {
    const observer = scenario({ endpoint: server.endpoint });
    const machine = scenario({ endpoint: server.endpoint });
    const before = server.hits.health + server.hits.post;
    const a = await runHook(observer, { session_id: 'x', cwd: path.join(observer.home, '.local', 'share', 'ecc-homunculus') });
    const b = await runHook(machine, { transcript_path: writeRollout(machine, meta('subagent')), session_id: 'x' });
    assert.deepStrictEqual([a.code, a.stdout, a.stderr], [b.code, b.stdout, b.stderr]);
    assertSilent(observer, a, server, before);
    assertSilent(machine, b, server, before);
  });

  // ------------------------------------------------ COSIGN_HOSTS cap
  await check('cosign state + codex thread: record mode shadow, incumbent emitted despite Laya disagreeing, state untouched', async () => {
    const disagree = await layaServer(() => 'git-helper');
    const sc = scenario({ endpoint: disagree.endpoint, mode: 'cosign' });
    const stateFile = path.join(sc.root, 'registry-state.json');
    const stateBefore = fs.readFileSync(stateFile, 'utf8');
    const rollout = writeRollout(sc, meta('user', { id: 'codex-cosign-thread' }));
    const res = await runHook(sc, { transcript_path: rollout });
    assert.strictEqual(res.code, 0, res.stderr);
    assert.strictEqual(res.stdout, INCUMBENT_LINE, 'nothing is suppressed');
    const [rec] = readRecords(sc);
    assert.strictEqual(readRecords(sc).length, 1);
    assert.strictEqual(rec.host, 'codex');
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.registryRevision, 3);
    assert.strictEqual(rec.laya.status, 'ok');
    assert.strictEqual(rec.laya.choice, SKILL.git, 'Laya was asked and disagreed');
    assert.strictEqual(rec.emitted, SKILL.ctx);
    assert.strictEqual(readLog(sc)[0].typed_mode, 'shadow');
    assert.strictEqual(readLog(sc)[0].suggested, SKILL.ctx);
    assert.strictEqual(fs.readFileSync(stateFile, 'utf8'), stateBefore, 'registry state file untouched');
    validate(sc);
    await disagree.close();
  });
  await check('cosign state + claude thread: still cosign (the disagreeing suggestion is withheld)', async () => {
    const disagree = await layaServer(() => 'git-helper');
    for (const [label, payload] of [
      ['no host evidence', { session_id: TREATMENT }],
      ['claude transcript_path', null],
    ]) {
      const sc = scenario({ endpoint: disagree.endpoint, mode: 'cosign' });
      const body = payload || { session_id: TREATMENT, transcript_path: path.join(sc.home, '.claude', 'projects', '-work-app', 'abc.jsonl') };
      const res = await runHook(sc, body);
      assert.strictEqual(res.code, 0, res.stderr);
      assert.strictEqual(res.stdout, '', `${label}: suggestion withheld`);
      const [rec] = readRecords(sc);
      assert.strictEqual(rec.host, 'claude', label);
      assert.strictEqual(rec.mode, 'cosign', label);
      assert.strictEqual(rec.arm, 'treatment', label);
      assert.strictEqual(rec.emitted, null, label);
      validate(sc);
    }
    await disagree.close();
  });
  await check('cosign state + unknown host (conflicting signals): capped at shadow, host unknown', async () => {
    const disagree = await layaServer(() => 'git-helper');
    const sc = scenario({ endpoint: disagree.endpoint, mode: 'cosign', env: { CLAUDE_CODE_ENTRYPOINT: 'cli' } });
    const res = await runHook(sc, { session_id: TREATMENT, thread_id: 'th-1' });
    assert.strictEqual(res.stdout, INCUMBENT_LINE);
    const [rec] = readRecords(sc);
    assert.strictEqual(rec.host, 'unknown');
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.sessionHash, sha(TREATMENT));
    validate(sc);
    await disagree.close();
  });
  await check('capModeForHost only lowers cosign for hosts outside COSIGN_HOSTS', async () => {
    const cfg = { mode: 'cosign', registryRevision: 4 };
    assert.strictEqual(router.capModeForHost(cfg, 'claude'), cfg);
    assert.deepStrictEqual(router.capModeForHost(cfg, 'codex'), { mode: 'shadow', registryRevision: 4 });
    assert.deepStrictEqual(router.capModeForHost(cfg, 'unknown'), { mode: 'shadow', registryRevision: 4 });
    assert.strictEqual(router.capModeForHost({ mode: 'off' }, 'codex').mode, 'off');
    assert.strictEqual(router.capModeForHost({ mode: 'shadow' }, 'codex').mode, 'shadow');
  });

  await server.close();
  for (const dir of cleanup) { try { fs.rmSync(dir, { recursive: true, force: true }); } catch (_e) { /* best effort */ } }
  if (failures) { console.error(`test_router_parity.js: ${failures} failure(s)`); process.exit(1); }
  console.log('test_router_parity.js: all checks passed');
})().catch((err) => { console.error(err); process.exit(1); });
