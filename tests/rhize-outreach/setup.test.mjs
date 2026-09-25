import test from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdtempSync, mkdirSync, rmSync, writeFileSync, readFileSync, statSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync, spawn } from 'node:child_process';
import { compareVersions, configFor, validateConfig, installSource, ensurePrivateDirectory, parse } from '../../rhize-outreach/scripts/rhize-outreach.mjs';

function temp() { return mkdtempSync(join(tmpdir(), 'rhize-outreach-test-')); }
function git(cwd, ...args) { execFileSync('git', args, { cwd, stdio: 'ignore' }); }

test('version comparison enforces the documented Node minimum', () => {
  assert.equal(compareVersions('v24.12.0', '24.12.0'), 0);
  assert.ok(compareVersions('24.11.99', '24.12.0') < 0);
  assert.ok(compareVersions('25.0.0', '24.12.0') > 0);
});

test('config is path-only and rejects malformed pins or ports', () => {
  const config = configFor({ dataRoot: '/tmp/outreach-data', port: 8877, pgBin: '/opt/pgsql/bin' });
  assert.equal(validateConfig(config), true);
  assert.equal(Object.keys(config).some(key => /token|password|secret|key/i.test(key)), false);
  assert.equal(validateConfig({ ...config, runtime_commit: 'main' }), false);
  assert.equal(validateConfig({ ...config, port: 80 }), false);
  assert.equal(validateConfig({ ...config, source_path: '/tmp/untrusted-source' }), false);
  assert.equal(config.artifact_path, join(config.data_path, 'artifacts'));
  assert.deepEqual(parse(['setup', '--check']), { action: 'setup', check: true, apply: false, json: false });
  assert.throws(() => parse(['setup', '--check', '--apply']), /Choose either/);
  assert.throws(() => parse(['setup', '--apply', '--data-dir', 'relative/path']), /absolute path/);
});

test('private directories are mode 700 and symbolic links are rejected', () => {
  const root = temp();
  try {
    const privatePath = join(root, 'private'); ensurePrivateDirectory(privatePath);
    assert.equal(statSync(privatePath).mode & 0o777, 0o700);
    const link = join(root, 'link'); symlinkSync(privatePath, link);
    assert.throws(() => ensurePrivateDirectory(link), /unsafe or foreign-owned/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('runtime install pins exact commit, reuses clean source, and refuses modified source', () => {
  const root = temp();
  try {
    const source = join(root, 'upstream'); mkdirSync(source);
    git(source, 'init', '-b', 'main'); git(source, 'config', 'user.email', 'test@example.invalid'); git(source, 'config', 'user.name', 'Test');
    writeFileSync(join(source, 'tracked.txt'), 'source'); git(source, 'add', 'tracked.txt'); git(source, 'commit', '-m', 'fixture');
    const pin = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' }).trim();
    const remote = join(root, 'origin.git'); git(root, 'clone', '--bare', source, remote);
    const spec = { source: remote, pin };
    const installed = installSource({ sourceRoot: join(root, 'source'), runtimeSpec: spec, installDependencies: false });
    assert.equal(execFileSync('git', ['-C', installed, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), pin);
    assert.equal(installSource({ sourceRoot: join(root, 'source'), runtimeSpec: spec, installDependencies: false }), installed);
    writeFileSync(join(installed, 'tracked.txt'), 'operator edit');
    assert.throws(() => installSource({ sourceRoot: join(root, 'source'), runtimeSpec: spec, installDependencies: false }), /not safe to reuse/);
    assert.equal(readFileSync(join(installed, 'tracked.txt'), 'utf8'), 'operator edit');
  } finally { rmSync(root, { recursive: true, force: true }); }
});


test('setup wizard stays on loopback and rejects bad session tokens and origins', async () => {
  const root = temp();
  try {
    const home = join(root, 'home'); const bin = join(root, 'bin'); const urlFile = join(root, 'wizard-url');
    mkdirSync(home); mkdirSync(bin);
    const fakeOpen = join(bin, 'open');
    writeFileSync(fakeOpen, `#!/bin/sh\nprintf '%s' "$1" > "$OUTREACH_TEST_URL_FILE"\n`);
    chmodSync(fakeOpen, 0o700);
    const env = { ...process.env, HOME: home, PATH: `${bin}:/opt/homebrew/bin:/usr/bin:/bin`, OUTREACH_TEST_URL_FILE: urlFile };
    const script = new URL('../../rhize-outreach/scripts/rhize-outreach.mjs', import.meta.url).pathname;
    const child = spawn(process.execPath, [script, 'wizard'], { env, stdio: 'ignore' });
    try {
      let started = false;
      for (let i = 0; i < 100; i++) {
        if (existsSync(urlFile)) { started = true; break; }
        await new Promise(resolve => setTimeout(resolve, 25));
      }
      assert.equal(started, true, 'wizard browser launch did not complete');
      const browserUrl = new URL(readFileSync(urlFile, 'utf8'));
      assert.equal(browserUrl.hostname, '127.0.0.1');
      const good = await fetch(browserUrl);
      assert.equal(good.status, 200);
      assert.match(await good.text(), /Install pinned workflow/);
      const statusUrl = new URL('/api/status', browserUrl.origin);
      statusUrl.searchParams.set('token', browserUrl.searchParams.get('token'));
      const status = await fetch(statusUrl, { headers: { Origin: browserUrl.origin } });
      assert.equal(status.status, 200);
      assert.equal((await status.json()).configured, false);
      const badToken = new URL(statusUrl); badToken.searchParams.set('token', 'wrong');
      assert.equal((await fetch(badToken, { headers: { Origin: browserUrl.origin } })).status, 403);
      const blockedOrigin = await fetch(statusUrl, { method: 'POST', headers: { Origin: 'https://attacker.example', 'Content-Type': 'application/json' }, body: '{}' });
      assert.equal(blockedOrigin.status, 403);
    } finally {
      child.kill('SIGTERM');
      await new Promise(resolve => { child.once('exit', resolve); setTimeout(() => { child.kill('SIGKILL'); resolve(); }, 1000); });
    }
  } finally { rmSync(root, { recursive: true, force: true }); }
});
