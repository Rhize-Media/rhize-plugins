// Round 4 — Reminders TCC redesign, installer/native slice:
//   - helper bundle at a STABLE path (supportDir/native), outside the
//     versioned runtime tree
//   - helper socket path + a second LaunchAgent (media.rhize.tasks.reminders-helper)
//   - signing identity auto-detection (Developer ID Application, ad-hoc fallback)
//   - dual-agent install/uninstall/rollback wiring
//
// See tests/e2e/lifecycle-fix-round-3.test.mjs for the single-agent
// rollback machinery this builds on; this file only covers what's new.
import assert from 'node:assert/strict';
import {access, mkdir, mkdtemp, readFile, rm, stat, writeFile} from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

import {
  helperLabel,
  install as installRuntime,
  label,
  renderHelperLaunchAgent,
  resolveSigningIdentity,
  waitForHelperSocketReady,
} from '../../installer/install.mjs';
import {createTestPathPolicy, exactInstallPaths} from '../../installer/safe-paths.mjs';
import {uninstall as uninstallRuntime} from '../../installer/uninstall.mjs';

const existingKeychain = () => ({async get() { return 't'.repeat(43); }, async set() {}, async delete() {}});
// See the identical rationale on this default in
// tests/e2e/lifecycle-fix-round-3.test.mjs — production's real
// waitForHelperSocketReady would otherwise poll for up to 5s and fail every
// test here, since none of these fakes start a real listening helper.
const install = options => installRuntime({keychain: existingKeychain(), checkNodePathExecutable: async () => {}, verifyNodePathCapable: async () => true, probeHelperSocketReady: async () => {}, ...options});

// See the identical rationale on this helper in
// tests/connectors/reminders-process.test.mjs — os.tmpdir()'s long macOS
// per-user path, combined with the fixed Reminders-helper socket suffix,
// reliably exceeds sockaddr_un's 104-byte limit and trips install()'s
// helper_socket_path_too_long guard on every test in this file.
function shortTempHome(label) {
  return mkdtemp(path.join('/tmp', `rt-${label.slice(0, 15)}-`));
}

async function seedInstallSource(home, version = '0.1.0') {
  const sourceRoot = path.join(home, 'plugin');
  const packageRoot = path.join(sourceRoot, 'native', 'reminders-helper');
  await mkdir(path.join(packageRoot, '.build', 'release'), {recursive: true});
  await mkdir(path.join(packageRoot, 'Resources'), {recursive: true});
  await mkdir(path.join(sourceRoot, 'service', 'bin'), {recursive: true});
  await mkdir(path.join(sourceRoot, 'schemas'), {recursive: true});
  await writeFile(path.join(packageRoot, '.build', 'release', 'RhizeRemindersHelper'), '#!/bin/sh\n');
  await writeFile(path.join(packageRoot, 'Resources', 'Info.plist'), await readFile(new URL('../../native/reminders-helper/Resources/Info.plist', import.meta.url), 'utf8'));
  await writeFile(path.join(sourceRoot, 'package.json'), `${JSON.stringify({name: 'rhize-tasks', version})}\n`);
  await writeFile(path.join(sourceRoot, 'service', 'bin', 'rhize-tasks.mjs'), 'process.exit(0);\n');
  await writeFile(path.join(sourceRoot, 'schemas', 'task.schema.json'), '{}\n');
  return {sourceRoot, packageRoot};
}

// Tracks the routine and helper agents independently, matching real
// launchctl's per-label state — see the identical rationale in
// lifecycle-fix-round-3.test.mjs / reminders-process.test.mjs.
function dualAgentRun({calls = []} = {}) {
  let routineLoaded = false;
  let routinePlistPath = null;
  let helperLoaded = false;
  let helperPlistPath = null;
  return async (file, args) => {
    calls.push([file, args]);
    if (file === '/usr/bin/security' && args[0] === 'find-generic-password') return {code: 0, stdout: `${'t'.repeat(43)}\n`};
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    const isHelper = args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'));
    if (args[0] === 'print') {
      if (isHelper) return helperLoaded ? {code: 0, stdout: `path = ${helperPlistPath}\n`} : {code: 113, stderr: 'not loaded'};
      return routineLoaded ? {code: 0, stdout: `path = ${routinePlistPath}\n`} : {code: 113, stderr: 'not loaded'};
    }
    if (args[0] === 'bootout') { if (isHelper) helperLoaded = false; else routineLoaded = false; return {code: 0, stdout: ''}; }
    if (args[0] === 'bootstrap') {
      const plistArg = args.at(-1);
      if (isHelper) { helperLoaded = true; helperPlistPath = plistArg; } else { routineLoaded = true; routinePlistPath = plistArg; }
      return {code: 0, stdout: ''};
    }
    return {code: 0, stdout: ''};
  };
}

test('installer records the helper bundle at a stable path outside the versioned runtime tree (finding #3 deferred half)', async () => {
  const home = await shortTempHome('stable-bundle');
  const {sourceRoot} = await seedInstallSource(home, '0.3.0');
  const paths = exactInstallPaths(home);
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run: dualAgentRun(), uid: 501, validate: async () => ({})});
  assert.equal(result.appPath, paths.helperAppPath);
  assert.equal(path.dirname(result.appPath), path.join(paths.supportDir, 'native'));
  await access(path.join(result.appPath, 'Contents', 'MacOS', 'RhizeRemindersHelper'));

  // Reinstalling a NEW version must not create a second bundle at a
  // versioned path — the stable path is the only one that ever exists.
  const {sourceRoot: sourceRoot2} = await seedInstallSource(home, '0.4.0');
  const result2 = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot: sourceRoot2, run: dualAgentRun(), uid: 501, validate: async () => ({})});
  assert.equal(result2.appPath, paths.helperAppPath);
  assert.equal(result.appPath, result2.appPath);
});

test('installer bootstraps the helper agent before the routine agent and records both plist paths', async () => {
  const home = await shortTempHome('bootstrap-order');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const calls = [];
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run: dualAgentRun({calls}), uid: 501, validate: async () => ({})});
  const bootstraps = calls.filter(([file, args]) => file === '/bin/launchctl' && args[0] === 'bootstrap');
  assert.equal(bootstraps.length, 2);
  assert.match(bootstraps[0][1].at(-1), /reminders-helper\.plist$/, 'helper bootstraps first, per the pinned IPC contract');
  assert.match(bootstraps[1][1].at(-1), /media\.rhize\.tasks\.plist$/);
  assert.equal(result.helperLaunchAgentPath, paths.helperLaunchAgentPath);
  assert.equal(result.helperSocketPath, paths.helperSocketPath);
  assert.equal(result.label, label);
  assert.equal(result.helperLabel, helperLabel);

  const helperPlist = await readFile(paths.helperLaunchAgentPath, 'utf8');
  assert.match(helperPlist, /<key>KeepAlive<\/key>\s*<true\/>/);
  assert.match(helperPlist, /<key>RunAtLoad<\/key>\s*<true\/>/);
  assert.match(helperPlist, /<string>--serve<\/string>/);
  assert.match(helperPlist, new RegExp(paths.helperSocketPath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

// #2 (blocker) — the ROUTINE stops (and swaps) first, THEN the helper: the
// reverse of bootstrap order above, and deliberately so. The routine is the
// helper's consumer (it calls the socket from its catch-up job); stopping
// it first means there's never a live routine that could watch the
// helper's socket vanish mid-swap and fall back to a direct spawn against a
// half-renamed bundle.
test('a same-version reinstall stops the routine agent before the helper agent', async () => {
  const home = await shortTempHome('stop-order');
  const {sourceRoot} = await seedInstallSource(home, '0.5.0');
  const paths = exactInstallPaths(home);
  const priorRuntime = path.join(paths.runtimeDir, 'versions', '0.5.0');
  await mkdir(path.join(priorRuntime, 'service', 'bin'), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'old routine plist');
  await writeFile(paths.helperLaunchAgentPath, 'old helper plist');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, version: '0.5.0', runtimePath: priorRuntime, cliPath: path.join(priorRuntime, 'service', 'bin', 'rhize-tasks.mjs')})}\n`);

  const bootoutOrder = [];
  let routineLoaded = true;
  let helperLoaded = true;
  const run = async (file, args) => {
    if (file === '/usr/bin/security' && args[0] === 'find-generic-password') return {code: 0, stdout: `${'t'.repeat(43)}\n`};
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    const isHelper = args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'));
    if (args[0] === 'print') {
      if (isHelper) return helperLoaded ? {code: 0, stdout: `path = ${paths.helperLaunchAgentPath}\n`} : {code: 113, stderr: 'not loaded'};
      return routineLoaded ? {code: 0, stdout: `path = ${paths.launchAgentPath}\n`} : {code: 113, stderr: 'not loaded'};
    }
    if (args[0] === 'bootout') {
      bootoutOrder.push(isHelper ? 'helper' : 'routine');
      if (isHelper) helperLoaded = false; else routineLoaded = false;
      return {code: 0, stdout: ''};
    }
    if (args[0] === 'bootstrap') { if (isHelper) helperLoaded = true; else routineLoaded = true; return {code: 0, stdout: ''}; }
    return {code: 0, stdout: ''};
  };
  await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  assert.deepEqual(bootoutOrder, ['routine', 'helper']);
});

// #3 (major) — sun_path has a hard 104-byte limit. A socket path that
// doesn't fit must fail before ANY mutation (not partway through
// activation, after paying for the swift build).
test('install refuses a socket path that would not fit in sun_path before any mutation happens', async () => {
  // A deliberately long "home" — the natural way this guard fires: this is
  // exactly the shape os.tmpdir()-based test homes had before shortTempHome
  // existed (see its comment above), and what a real, deeply-nested
  // corporate home directory could still produce.
  const home = path.join('/tmp', `rt-deliberately-long-home-directory-name-${'x'.repeat(60)}`);
  await mkdir(home, {recursive: true});
  try {
    const {sourceRoot} = await seedInstallSource(home);
    const paths = exactInstallPaths(home);
    assert.ok(Buffer.byteLength(paths.helperSocketPath, 'utf8') >= 104, 'test setup must actually produce an over-limit path');
    let validateCalled = false;
    await assert.rejects(
      install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run: async () => ({code: 0, stdout: ''}), uid: 501, validate: async () => { validateCalled = true; return {}; }}),
      error => error.code === 'helper_socket_path_too_long',
    );
    assert.equal(validateCalled, false, 'the length guard must fire before validate() — before any mutation, including the swift build');
  } finally {
    await rm(home, {recursive: true, force: true});
  }
});

// #3 (major) — "LaunchAgent loaded" is not "the socket is actually
// answering". install() must confirm real socket readiness after
// bootstrapping the helper, and roll back (without ever bootstrapping the
// routine agent against a dead helper) if it never comes up.
test('install rolls back if the helper socket never becomes ready, without ever bootstrapping the routine agent', async () => {
  const home = await shortTempHome('socket-not-ready');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const calls = [];
  const run = dualAgentRun({calls});
  await assert.rejects(
    install({
      paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({}),
      probeHelperSocketReady: socketPath => waitForHelperSocketReady(socketPath, {
        timeoutMs: 50, intervalMs: 10, probeConnect: async () => { throw new Error('never_ready'); },
      }),
    }),
    error => error.activationState === 'helper_socket_not_ready',
  );
  const routineBootstraps = calls.filter(([file, args]) => file === '/bin/launchctl' && args[0] === 'bootstrap' && !args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper')));
  assert.equal(routineBootstraps.length, 0, 'the routine agent must never be bootstrapped against a helper whose socket never came up');
});

test('waitForHelperSocketReady resolves as soon as the injected probe succeeds, without exhausting the full timeout budget', async () => {
  let attempts = 0;
  const start = Date.now();
  await waitForHelperSocketReady('/tmp/irrelevant.sock', {
    timeoutMs: 5_000, intervalMs: 10,
    probeConnect: async () => { attempts += 1; if (attempts < 3) throw new Error('not_yet'); },
  });
  assert.equal(attempts, 3);
  assert.ok(Date.now() - start < 1_000, 'must return as soon as the probe succeeds, not wait out the full budget');
});

test('renderHelperLaunchAgent rejects an unresolved placeholder and never leaks secret-shaped text from a path', async () => {
  const dir = await shortTempHome('helper-plist');
  const templatePath = path.join(dir, 'helper.plist.template');
  await writeFile(templatePath, await readFile(new URL('../../installer/media.rhize.tasks.reminders-helper.plist.template', import.meta.url), 'utf8'));
  const output = await renderHelperLaunchAgent({
    helperBinaryPath: '/Users/tom/dev/secrets-tooling/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper',
    socketPath: '/Users/tom/Library/Application Support/Rhize Tasks/reminders-helper.sock',
    stdoutPath: '/tmp/helper-out', stderrPath: '/tmp/helper-err', templatePath,
  });
  assert.doesNotMatch(output, /bearer|password/i);
  assert.match(output, /secrets-tooling/);

  const incompleteTemplatePath = path.join(dir, 'incomplete.plist.template');
  await writeFile(incompleteTemplatePath, '<plist>{{HELPER_BINARY_PATH}}{{SOCKET_PATH}}{{STDOUT_PATH}}{{STDERR_PATH}}{{UNKNOWN_PLACEHOLDER}}</plist>');
  await assert.rejects(renderHelperLaunchAgent({helperBinaryPath: '/x', socketPath: '/y', stdoutPath: '/tmp/o', stderrPath: '/tmp/e', templatePath: incompleteTemplatePath}), /unresolved_launch_agent_placeholder/);
});

test('signing identity auto-detects a single Developer ID Application identity and records the classification, not the raw string', async () => {
  const home = await shortTempHome('sign-auto');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const codesignArgs = [];
  const base = dualAgentRun();
  const run = async (file, args) => {
    if (file === '/usr/bin/security' && args[0] === 'find-identity') {
      return {code: 0, stdout: '  1) ABCDEF1234567890ABCDEF1234567890ABCDEF12 "Developer ID Application: Rhize Media LLC (TEAMID1234)"\n     1 valid identities found\n'};
    }
    if (file === '/usr/bin/codesign') codesignArgs.push(args);
    return base(file, args);
  };
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  // codesign is signed with the HASH, not the display name (finding #9) —
  // a renewed certificate can share a display name with its predecessor,
  // so the hash is the only identifier that's unambiguous to codesign too.
  assert.deepEqual(codesignArgs[0].slice(0, 3), ['--force', '--sign', 'ABCDEF1234567890ABCDEF1234567890ABCDEF12']);
  assert.equal(result.signingIdentity, 'developer-id');
  const manifest = JSON.parse(await readFile(paths.installationManifestPath, 'utf8'));
  assert.equal(manifest.signingIdentity, 'developer-id');
});

test('signing identity falls back to ad-hoc when multiple Developer ID identities are ambiguous', async () => {
  const home = await shortTempHome('sign-ambiguous');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const codesignArgs = [];
  const base = dualAgentRun();
  const run = async (file, args) => {
    if (file === '/usr/bin/security' && args[0] === 'find-identity') {
      return {
        code: 0,
        stdout: [
          '  1) 1111111111111111111111111111111111111111 "Developer ID Application: Rhize Media LLC (TEAMID1234)"',
          '  2) 2222222222222222222222222222222222222222 "Developer ID Application: Someone Else (TEAMID5678)"',
          '     2 valid identities found',
        ].join('\n'),
      };
    }
    if (file === '/usr/bin/codesign') codesignArgs.push(args);
    return base(file, args);
  };
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  assert.deepEqual(codesignArgs[0].slice(0, 3), ['--force', '--sign', '-']);
  assert.equal(result.signingIdentity, 'ad-hoc');
});

test('signing identity env override still wins over auto-detection and records the literal identity name', async () => {
  const home = await shortTempHome('sign-override');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const codesignArgs = [];
  let securityCalled = false;
  const base = dualAgentRun();
  const run = async (file, args) => {
    if (file === '/usr/bin/security' && args[0] === 'find-identity') { securityCalled = true; return {code: 0, stdout: ''}; }
    if (file === '/usr/bin/codesign') codesignArgs.push(args);
    return base(file, args);
  };
  process.env.RHIZE_TASKS_SIGN_IDENTITY = 'Developer ID Application: Explicit Override';
  let result;
  try {
    result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  } finally {
    delete process.env.RHIZE_TASKS_SIGN_IDENTITY;
  }
  assert.deepEqual(codesignArgs[0].slice(0, 3), ['--force', '--sign', 'Developer ID Application: Explicit Override']);
  assert.equal(result.signingIdentity, 'Developer ID Application: Explicit Override');
  assert.equal(securityCalled, false, 'an explicit override must short-circuit before probing security at all');
});

test('resolveSigningIdentity is directly testable without shelling out to the real security tool', async () => {
  const noIdentity = await resolveSigningIdentity({run: async () => ({code: 0, stdout: ''})});
  assert.deepEqual(noIdentity, {identity: '-', kind: 'ad-hoc'});

  // A line with an identity that isn't a real 40-hex-char SHA-1 hash (a
  // malformed or truncated `security` line) must not match at all, not be
  // accepted as "close enough" — the hash is exactly what makes an
  // identity unambiguous to codesign (finding #9).
  const malformedHash = await resolveSigningIdentity({run: async () => ({code: 0, stdout: '  1) AA "Developer ID Application: Only One (TEAM1)"\n'})});
  assert.deepEqual(malformedHash, {identity: '-', kind: 'ad-hoc'});

  const oneIdentity = await resolveSigningIdentity({run: async () => ({code: 0, stdout: '  1) 0123456789ABCDEF0123456789ABCDEF01234567 "Developer ID Application: Only One (TEAM1)"\n'})});
  assert.deepEqual(oneIdentity, {identity: '0123456789ABCDEF0123456789ABCDEF01234567', kind: 'developer-id'});

  const securityFailed = await resolveSigningIdentity({run: async () => { throw new Error('security_unavailable'); }});
  assert.deepEqual(securityFailed, {identity: '-', kind: 'ad-hoc'});

  const override = await resolveSigningIdentity({envOverride: 'My Custom Identity', run: async () => { throw new Error('must not be called'); }});
  assert.deepEqual(override, {identity: 'My Custom Identity', kind: 'My Custom Identity'});
});

test('resolveSigningIdentity treats a renewed certificate (same display name, new hash) as ambiguous rather than collapsing it to "one" identity', async () => {
  // The exact scenario finding #9 exists to fix: two DISTINCT, currently
  // valid certificates sharing one display name (a renewal keeps the name,
  // mints a new hash). Deduping by name alone would see "one" identity
  // here and hand codesign a name that's still ambiguous to IT.
  const sameNameDifferentHash = await resolveSigningIdentity({run: async () => ({
    code: 0,
    stdout: [
      '  1) AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA "Developer ID Application: Rhize Media LLC (TEAMID1234)"',
      '  2) BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB "Developer ID Application: Rhize Media LLC (TEAMID1234)"',
      '     2 valid identities found',
    ].join('\n'),
  })});
  assert.deepEqual(sameNameDifferentHash, {identity: '-', kind: 'ad-hoc'});
});

test('uninstall boots out both agents by label, tolerating not-loaded, and removes the helper plist/socket/bundle', async () => {
  const root = await shortTempHome('uninstall-dual');
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await mkdir(path.join(paths.supportDir, 'native', 'RhizeRemindersHelper.app', 'Contents', 'MacOS'), {recursive: true});
  await writeFile(paths.launchAgentPath, 'routine plist');
  await writeFile(paths.helperLaunchAgentPath, 'helper plist');
  await writeFile(path.join(paths.supportDir, 'native', 'RhizeRemindersHelper.app', 'Contents', 'MacOS', 'RhizeRemindersHelper'), '#!/bin/sh\n');
  const bootoutCalls = [];
  const run = async (file, args) => {
    if (file === '/bin/launchctl' && args[0] === 'bootout') bootoutCalls.push(args);
    // Every bootout reports "not loaded" — must be tolerated, not thrown.
    return {code: 3, stderr: 'Boot-out failed: 3: No such process'};
  };
  const result = await uninstallRuntime({choices: {data: 'delete', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501});
  assert.equal(result.ok, true);
  assert.equal(bootoutCalls.length, 2);
  assert.ok(bootoutCalls.some(args => args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'))), 'the helper must be booted out too');
  await assert.rejects(access(paths.helperLaunchAgentPath));
  await assert.rejects(access(paths.helperSocketPath));
  await assert.rejects(access(path.join(paths.supportDir, 'native')));
});

test('uninstall with --retain-data keeps sqlite state but still removes the helper bundle (code, not data)', async () => {
  const root = await shortTempHome('uninstall-retain');
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await mkdir(path.join(paths.supportDir, 'native', 'RhizeRemindersHelper.app', 'Contents', 'MacOS'), {recursive: true});
  await writeFile(path.join(paths.supportDir, 'state.sqlite'), 'keep-me');
  await writeFile(paths.launchAgentPath, 'routine plist');
  await writeFile(paths.helperLaunchAgentPath, 'helper plist');
  const run = async () => ({code: 0, stdout: ''});
  const result = await uninstallRuntime({choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501});
  assert.equal(result.dataRetained, true);
  assert.equal(await readFile(path.join(paths.supportDir, 'state.sqlite'), 'utf8'), 'keep-me');
  await assert.rejects(access(path.join(paths.supportDir, 'native')));
  await assert.rejects(access(paths.helperLaunchAgentPath));
});

test('a helper-only bootout failure leaves the helper artifact untouched while the routine agent still rolls back cleanly', async () => {
  // The routine and helper are independent launchd resources — if the
  // HELPER'S bootout can never be confirmed, install() must not guess it's
  // safe to touch the helper's own files, while the ROUTINE side (whose own
  // launchd state was never perturbed at all in this scenario) is untouched
  // by that uncertainty and needs no rollback of its own.
  const home = await shortTempHome('helper-only-fail');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await mkdir(path.join(paths.supportDir, 'native'), {recursive: true});
  await writeFile(paths.helperLaunchAgentPath, 'old helper plist');
  const run = async (file, args) => {
    if (file === '/usr/bin/security' && args[0] === 'find-generic-password') return {code: 0, stdout: `${'t'.repeat(43)}\n`};
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    const isHelper = args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'));
    if (isHelper) {
      if (args[0] === 'print') return {code: 0, stdout: `path = ${paths.helperLaunchAgentPath}\n`};
      if (args[0] === 'bootout') throw new Error('helper_bootout_uncertain');
      return {code: 0, stdout: ''};
    }
    if (args[0] === 'print') return {code: 113, stderr: 'not loaded'};
    return {code: 0, stdout: ''};
  };
  const error = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}).catch(value => value);
  assert.ok(error, 'install must reject');
  assert.match(error.rollbackState, /manual_recovery_required/);
  // The helper's prior plist must be exactly as it was — never touched,
  // since its own stop could never be confirmed.
  assert.equal(await readFile(paths.helperLaunchAgentPath, 'utf8'), 'old helper plist');
  // No routine agent was ever loaded in this scenario, so nothing about
  // the routine required manual recovery — the ONLY reason this install
  // failed at all is the helper's own uncertain bootout.
  await assert.rejects(access(paths.launchAgentPath));
});

// #7 (major) — item cleanup's CLI subprocess talks to Reminders through the
// helper's socket. Booting the helper out BEFORE cleanup would force it
// onto the direct-spawn fallback for every call — the exact
// per-request-process TCC exposure this whole redesign removes. The helper
// must stay up through cleanup and only be booted out afterward.
test('uninstall runs item cleanup while the helper is still up, and boots the helper out only afterward', async () => {
  const root = await shortTempHome('uninstall-order');
  const paths = exactInstallPaths(root);
  const runtimePath = path.join(paths.runtimeDir, 'versions', '0.1.0');
  const cliPath = path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs');
  await mkdir(path.dirname(cliPath), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(cliPath, '');
  await writeFile(paths.launchAgentPath, 'routine plist');
  await writeFile(paths.helperLaunchAgentPath, 'helper plist');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, runtimePath, cliPath})}\n`);

  const events = [];
  const run = async (file, args) => {
    if (file === '/bin/launchctl' && args[0] === 'bootout') {
      const isHelper = args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'));
      events.push(isHelper ? 'helper_bootout' : 'routine_bootout');
      return {code: 0, stderr: ''};
    }
    if (file === '/bin/launchctl') return {code: 0, stderr: ''};
    // Anything else is the item-cleanup CLI subprocess.
    events.push('item_cleanup');
    return {code: 0, stdout: '{"ok":true,"reminders":{"verified":true,"deleted":1},"calendar":{"verified":true,"deleted":2}}\n'};
  };
  const result = await uninstallRuntime({choices: {data: 'retain', items: 'delete'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501, nodePath: '/opt/node'});
  assert.equal(result.itemsRetained, false);
  assert.deepEqual(events, ['routine_bootout', 'item_cleanup', 'helper_bootout']);
});
