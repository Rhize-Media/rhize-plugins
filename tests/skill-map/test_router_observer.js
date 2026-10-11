#!/usr/bin/env node
// The skill router skips ECC's homunculus background-observer sessions (machine
// traffic: 83% of replayed router fires on 2026-10-11), identified by cwd: no suggestion, no Laya
// call, no decision record, no silence sample. Control: an ordinary session
// still emits the incumbent and is co-signed in shadow. Standalone script.
'use strict';
const assert = require('assert');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const ROUTER = path.join(REPO, 'rhize-context-manager', 'hooks', 'skill-router.js');
const SKILL = 'skill:alpha/git-helper';
const OTHER = 'skill:alpha/context-pack';
const INDEX = {
  schemaVersion: '1.1.0', disclosure: {}, remediation: {}, succession: {},
  router: {
    extendsBases: {},
    signals: {
      [SKILL]: [{ kind: 'name', weight: 1, label: 'git-helper' }, { kind: 'tag', weight: 2, label: 'git' }, { kind: 'tag', weight: 2, label: 'rebase' }],
      [OTHER]: [{ kind: 'name', weight: 1, label: 'context-pack' }, { kind: 'tag', weight: 2, label: 'git' }],
    },
  },
};
const MAP = { nodes: [SKILL, OTHER].map((id) => ({ id, kind: 'skill', name: id.split('/').pop(), description: `${id} description` })), edges: [] };
const PROMPT = 'help me rebase this git branch onto main';

let requests = 0;
const server = http.createServer((req, res) => {
  requests += 1;
  let body = '';
  req.on('data', (c) => { body += c; });
  req.on('end', () => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/health') { res.end(JSON.stringify({ status: 'ok', loaded: ['typed-decisions'] })); return; }
    const request = JSON.parse(body);
    const keys = Object.keys(request.questions.skill.criteria);
    const probabilities = Object.fromEntries(keys.map((k) => [k, k === 's0' ? 0.9 : 0.1 / (keys.length - 1)]));
    res.end(JSON.stringify({ routing: { model: 'typed-decisions' }, usage: { input_tokens: 1, output_tokens: 1 },
      answers: { skill: { type: 'choice', choice: 's0', probabilities } } }));
  });
});

function scenario(port, extraEnv = {}) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'router-observer-'));
  const ctx = path.join(home, '.claude', 'context-manager');
  fs.mkdirSync(ctx, { recursive: true });
  fs.writeFileSync(path.join(ctx, 'skill-map.indexes.json'), JSON.stringify(INDEX));
  fs.writeFileSync(path.join(ctx, 'skill-map.static.json'), JSON.stringify(MAP));
  const env = { ...process.env, HOME: home, XDG_DATA_HOME: path.join(home, 'xdg'),
    RHIZE_TYPED_DECISIONS_ROOT: path.join(home, 'typed'), RHIZE_SUGGESTION_LOG: path.join(home, 'log.jsonl'),
    RHIZE_LAYA_ENDPOINT: `http://127.0.0.1:${port}`, ...extraEnv };
  delete env.ECC_SKIP_OBSERVE; delete env.ECC_HOOK_PROFILE;
  Object.assign(env, extraEnv);
  return { home, env };
}

function runHook(sc, cwd) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [ROUTER], { env: sc.env, stdio: ['pipe', 'pipe', 'pipe'] });
    let stdout = '';
    child.stdout.on('data', (c) => { stdout += c; });
    child.on('close', (code) => resolve({ code, stdout }));
    child.stdin.end(JSON.stringify({ prompt: PROMPT, session_id: 'sess-1', cwd, hook_event_name: 'UserPromptSubmit' }));
  });
}

function recordCount(sc) {
  const dir = path.join(sc.home, 'typed', 'skill-fit', 'records');
  if (!fs.existsSync(dir)) return 0;
  return fs.readdirSync(dir).reduce((n, f) => n + fs.readFileSync(path.join(dir, f), 'utf8').split('\n').filter(Boolean).length, 0);
}

async function main() {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  let failures = 0;
  const check = async (name, fn) => {
    try { await fn(); console.log(`PASS ${name}`); } catch (err) { failures += 1; console.error(`FAIL ${name}\n${err.stack}`); }
  };

  await check('control: ordinary session emits and is co-signed in shadow', async () => {
    const sc = scenario(port);
    const before = requests;
    const res = await runHook(sc, path.join(sc.home, 'dev', 'project'));
    assert.strictEqual(res.code, 0);
    assert.match(res.stdout, /alpha:git-helper/);
    assert.ok(requests > before, 'Laya contacted');
    assert.strictEqual(recordCount(sc), 1);
  });

  for (const [name, cwdOf, env] of [
    ['observer root cwd', (h) => path.join(h, '.local', 'share', 'ecc-homunculus'), {}],
    ['observer project cwd', (h) => path.join(h, '.local', 'share', 'ecc-homunculus', 'projects', '0123456789ab'), {}],
  ]) {
    await check(`background observer skipped: ${name}`, async () => {
      const sc = scenario(port, env);
      const before = requests;
      const res = await runHook(sc, cwdOf(sc.home));
      assert.strictEqual(res.code, 0);
      assert.strictEqual(res.stdout, '');
      assert.strictEqual(requests, before, 'no Laya request');
      assert.strictEqual(recordCount(sc), 0);
      assert.ok(!fs.existsSync(path.join(sc.home, 'log.jsonl')), 'no legacy row');
    });
  }

  await check('ECC launcher env alone does not silence an interactive session', async () => {
    const sc = scenario(port, { ECC_SKIP_OBSERVE: '1', ECC_HOOK_PROFILE: 'minimal' });
    const res = await runHook(sc, path.join(sc.home, 'dev', 'project'));
    assert.match(res.stdout, /alpha:git-helper/);
  });

  await check('a non-hex projects child is an ordinary session', async () => {
    const sc = scenario(port);
    const res = await runHook(sc, path.join(sc.home, '.local', 'share', 'ecc-homunculus', 'projects', 'my-notes'));
    assert.match(res.stdout, /alpha:git-helper/);
  });

  server.close();
  if (failures) { console.error(`test_router_observer.js: ${failures} failure(s)`); process.exit(1); }
  console.log('test_router_observer.js: all checks passed');
}

main().catch((err) => { console.error(err); process.exit(1); });
