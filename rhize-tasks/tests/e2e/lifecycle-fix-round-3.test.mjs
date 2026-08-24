import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {constants as fsConstants} from 'node:fs';
import {access, mkdir, mkdtemp, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import process from 'node:process';
import test from 'node:test';

import {
  atomicWriteFile,
  checkLoopbackPort,
  ensureApiBearer,
  install as installRuntime,
  renderLaunchAgent,
  resolveInstallNodePath,
  servePidPath,
  stopServeProcessIfRunning,
} from '../../installer/install.mjs';
import {createTestPathPolicy, exactInstallPaths} from '../../installer/safe-paths.mjs';
import {uninstall as uninstallRuntime} from '../../installer/uninstall.mjs';
import {errorKind, ensureServerRunning, main, runCli, serializeError} from '../../service/bin/rhize-tasks.mjs';
import {createServiceContext} from '../../service/src/api/context.mjs';
import {hasActiveProcessGroups, killActiveProcessGroups, runProcess} from '../../service/src/connectors/process-runner.mjs';
import {withSingleInstance} from '../../service/src/scheduler/single-instance.mjs';

const existingKeychain = () => ({async get() { return 't'.repeat(43); }, async set() {}, async delete() {}});
// probeHelperSocketReady defaults to a no-op: production's real default
// (waitForHelperSocketReady -> an actual socket connect) would otherwise
// poll for up to 5s and then fail every single test here, since none of
// these fakes ever start a real listening helper process. Tests of the
// readiness check itself (finding #3) override this explicitly.
const install = options => installRuntime({keychain: existingKeychain(), checkNodePathExecutable: async () => {}, verifyNodePathCapable: async () => true, probeHelperSocketReady: async () => {}, ...options});

// os.tmpdir() on macOS resolves to a long per-user path (~46+ bytes,
// /var/folders/<hash>/<hash>/T/) that, combined with Library/Application
// Support/Rhize Tasks/reminders-helper.sock (65 bytes), reliably exceeds
// sockaddr_un's 104-byte sun_path limit and trips install()'s new
// helper_socket_path_too_long guard (finding #3) — not hypothetical, it
// broke every install() test in this file the moment the guard was added.
// /tmp (13 real bytes as /private/tmp) with a length-capped prefix stays
// well clear of that limit. (tmpdir() itself is still used directly by the
// one test below that deliberately needs a long-lived, symlink-safe path
// outside any per-test directory it also creates.)
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

// Tracks the routine agent and the helper agent independently — install()
// now bootstraps/boots out two separate launchd labels, and a shared single
// `isLoaded`/plist-path pair (the pre-dual-agent shape of this fake) makes
// print() answer with the ROUTINE's plist path even when the HELPER's
// label was queried, tripping `launchctl_configuration_mismatch` spuriously.
// `loaded` seeds the ROUTINE's initial state only (matches every existing
// caller's intent); the helper always starts unloaded unless a test
// bootstraps it itself. Target detection is by substring on the call's own
// args, so no caller needs to say which target it's calling.
function fakeRun(plistPath, {loaded = false, calls = []} = {}) {
  let routineLoaded = loaded;
  let routinePlistPath = plistPath;
  let helperLoaded = false;
  let helperPlistPath = null;
  return async (file, args) => {
    calls.push([file, args]);
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

// #5 — orphaned grandchild holding stdout must not hang the promise forever.
test('runProcess resolves on timeout even when an orphaned grandchild still holds stdout (finding #5)', async () => {
  const start = Date.now();
  const result = await runProcess('/bin/sh', ['-c', '(sleep 10; echo late) & exec sleep 30'], {timeoutMs: 1_000});
  assert.equal(result.timedOut, true);
  assert.ok(Date.now() - start < 3_000, `expected settlement well under the orphan's lifetime, took ${Date.now() - start}ms`);
});

test('runProcess kills the whole process group, not just the direct child (finding #5)', async () => {
  const result = await runProcess('/bin/sh', ['-c', 'echo hello'], {timeoutMs: 2_000});
  assert.equal(result.code, 0);
  assert.equal(result.stdout, 'hello\n');
});

test('runProcess timeout actually terminates a grandchild, not just resolves quickly (finding #5/#6-followup)', async () => {
  // The earlier "resolves quickly" test proves the PROMISE doesn't hang; it
  // does not prove the orphaned grandchild is actually dead. Prove
  // termination directly: the grandchild writes its own pid, then loops
  // appending to a marker file — after the group is killed, both the marker
  // must stop growing and the grandchild's pid must no longer exist.
  const dir = await shortTempHome('groupkill');
  const marker = path.join(dir, 'marker.log');
  const pidFile = path.join(dir, 'grandchild.pid');
  const script = `(echo $$ > ${JSON.stringify(pidFile)}; while true; do echo tick >> ${JSON.stringify(marker)}; sleep 0.1; done) & exec sleep 30`;
  const result = await runProcess('/bin/sh', ['-c', script], {timeoutMs: 500});
  assert.equal(result.timedOut, true);
  await new Promise(resolve => setTimeout(resolve, 300));
  const grandchildPid = Number.parseInt(await readFile(pidFile, 'utf8'), 10);
  assert.ok(Number.isInteger(grandchildPid) && grandchildPid > 0, 'grandchild must have recorded its pid before the group was killed');
  const sizeBefore = (await stat(marker)).size;
  await new Promise(resolve => setTimeout(resolve, 400));
  const sizeAfter = (await stat(marker)).size;
  assert.equal(sizeAfter, sizeBefore, 'the grandchild must have stopped writing once the group was killed');
  assert.throws(() => process.kill(grandchildPid, 0), /ESRCH/);
  await rm(dir, {recursive: true, force: true});
});

test('killActiveProcessGroups reaches a still-running child\'s grandchild too (finding #6-followup)', async () => {
  const dir = await shortTempHome('killactive');
  const marker = path.join(dir, 'marker.log');
  const pidFile = path.join(dir, 'grandchild.pid');
  const script = `(echo $$ > ${JSON.stringify(pidFile)}; while true; do echo tick >> ${JSON.stringify(marker)}; sleep 0.1; done) & exec sleep 30`;
  // Long timeout: the group must still be alive (and tracked) when we call
  // killActiveProcessGroups ourselves, mirroring what single-instance's
  // SIGTERM handler now does before releasing its lock.
  const runPromise = runProcess('/bin/sh', ['-c', script], {timeoutMs: 30_000});
  const deadline = Date.now() + 3_000;
  while (!hasActiveProcessGroups() && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(hasActiveProcessGroups(), true);
  await new Promise(resolve => setTimeout(resolve, 300));
  const grandchildPid = Number.parseInt(await readFile(pidFile, 'utf8'), 10);
  killActiveProcessGroups('SIGKILL');
  await runPromise;
  await new Promise(resolve => setTimeout(resolve, 300));
  assert.throws(() => process.kill(grandchildPid, 0), /ESRCH/);
  assert.equal(hasActiveProcessGroups(), false);
  await rm(dir, {recursive: true, force: true});
});

// Several tests below hand-write a bespoke `run` closure to exercise a
// specific ROUTINE-agent launchctl sequence in detail. None of them are
// about the helper agent, so every helper-targeted call just succeeds
// uninterrupted (tracking its own trivial loaded/not-loaded state so the
// post-bootstrap activation-verification print still answers correctly).
function helperSucceedsHandler(paths) {
  let loaded = false;
  return async args => {
    if (args[0] === 'print') return loaded ? {code: 0, stdout: `path = ${paths.helperLaunchAgentPath}\n`} : {code: 113, stderr: 'not loaded'};
    if (args[0] === 'bootout') { loaded = false; return {code: 0, stdout: ''}; }
    if (args[0] === 'bootstrap') { loaded = true; return {code: 0, stdout: ''}; }
    return {code: 0, stdout: ''};
  };
}

// #21 — bootout before the runtime swap.
test('same-version reinstall stops the old agent before the runtime directory is swapped (finding #21)', async () => {
  const home = await shortTempHome('reorder');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const priorRuntime = path.join(paths.runtimeDir, 'versions', '0.1.0');
  const cliInPriorRuntime = path.join(priorRuntime, 'service', 'bin', 'rhize-tasks.mjs');
  await mkdir(path.dirname(cliInPriorRuntime), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(cliInPriorRuntime, 'old code\n');
  await writeFile(paths.launchAgentPath, 'old plist\n');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, runtimePath: priorRuntime, cliPath: cliInPriorRuntime})}\n`);
  let observedAtBootout = null;
  const helperHandler = helperSucceedsHandler(paths);
  const run = async (file, args) => {
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    // This test is about the ROUTINE agent only — no prior helper exists.
    if (args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'))) return helperHandler(args);
    if (args[0] === 'print') return {code: 0, stdout: `path = ${paths.launchAgentPath}\n`};
    if (args[0] === 'bootout') {
      observedAtBootout = await readFile(cliInPriorRuntime, 'utf8').catch(() => 'MISSING');
      return {code: 0, stdout: ''};
    }
    return {code: 0, stdout: ''};
  };
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  assert.equal(observedAtBootout, 'old code\n', 'the old runtime must still be in place at the moment the old agent is stopped');
  assert.notEqual(await readFile(path.join(result.runtimePath, 'service', 'bin', 'rhize-tasks.mjs'), 'utf8'), 'old code\n', 'the runtime must be swapped to the new build after bootout');
});

// #22 — SIGTERM releases the lock, and a dead pid is reclaimable regardless of age.
test('withSingleInstance releases its lock on SIGTERM instead of leaving it stale for 30 minutes (finding #22)', async () => {
  const directory = await shortTempHome('sigterm');
  const lockPath = path.join(directory, 'routine.lock');
  // The action's promise must keep the event loop non-idle (a live timer),
  // or Node's own "unsettled top-level await" detector force-exits the
  // process with code 13 before SIGTERM is even relevant — an artifact of
  // this test harness, not something a real long-running routine (which is
  // always waiting on real I/O) would ever hit.
  const script = `
    import {withSingleInstance} from ${JSON.stringify(new URL('../../service/src/scheduler/single-instance.mjs', import.meta.url).pathname)};
    await withSingleInstance(${JSON.stringify(lockPath)}, () => new Promise(() => { process.stdout.write('ready\\n'); setInterval(() => {}, 1000); }));
  `;
  const child = spawn(process.execPath, ['--input-type=module', '--eval', script], {stdio: ['ignore', 'pipe', 'pipe']});
  try {
    await new Promise((resolve, reject) => {
      let buffer = '';
      const onData = chunk => { buffer += chunk.toString(); if (buffer.includes('ready')) { child.stdout.off('data', onData); resolve(); } };
      child.stdout.on('data', onData);
      child.once('error', reject);
      setTimeout(() => reject(new Error('child did not report ready in time')), 5_000).unref?.();
    });
    await access(lockPath);
    child.kill('SIGTERM');
    await new Promise((resolve, reject) => {
      child.once('exit', resolve);
      setTimeout(() => reject(new Error('child did not exit after SIGTERM')), 5_000).unref?.();
    });
    await assert.rejects(access(lockPath), /ENOENT/);
  } finally {
    child.kill('SIGKILL');
    await rm(directory, {recursive: true, force: true});
  }
});

test('withSingleInstance reclaims a dead pid immediately, without waiting out the 30-minute age gate (finding #22)', async () => {
  const directory = await shortTempHome('reclaim');
  const lockPath = path.join(directory, 'routine.lock');
  await writeFile(lockPath, JSON.stringify({pid: 999999, token: 'stale', startedAt: new Date().toISOString()}), {mode: 0o600});
  const result = await withSingleInstance(lockPath, async () => 'reclaimed-immediately');
  assert.equal(result, 'reclaimed-immediately');
  await rm(directory, {recursive: true, force: true});
});

// #23 — stale artifact sweep and atomicWriteFile EEXIST recovery.
test('install sweeps a dead pid\'s leftover .installing-<pid> stage dir and <version>.previous-<pid> backup (finding #23)', async () => {
  const home = await shortTempHome('sweep');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const deadPid = 999999;
  const staleStage = path.join(paths.runtimeDir, `.installing-${deadPid}`);
  const staleBackup = path.join(paths.runtimeDir, 'versions', `0.1.0.previous-${deadPid}`);
  await mkdir(staleStage, {recursive: true});
  await writeFile(path.join(staleStage, 'leftover'), 'leftover');
  await mkdir(staleBackup, {recursive: true});
  await writeFile(path.join(staleBackup, 'leftover'), 'leftover');
  const run = fakeRun(paths.launchAgentPath);
  await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  await assert.rejects(access(staleStage));
  await assert.rejects(access(staleBackup));
});

test('install does not sweep a stage dir or backup whose pid is still running (finding #23)', async () => {
  const home = await shortTempHome('sweep-live');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  // pid 1 (launchd) is always running and is never the current process's own
  // pid, so it can't collide with placeRuntimeCandidate's own backup path
  // (which uses process.pid) the way reusing our own pid here would.
  const livePid = 1;
  const liveBackup = path.join(paths.runtimeDir, 'versions', `0.1.0.previous-${livePid}`);
  await mkdir(liveBackup, {recursive: true});
  await writeFile(path.join(liveBackup, 'leftover'), 'leftover');
  const run = fakeRun(paths.launchAgentPath);
  await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  await access(liveBackup);
  await rm(liveBackup, {recursive: true, force: true});
});

test('atomicWriteFile clears a stale same-pid .installing temp file instead of hard-failing EEXIST (finding #23)', async () => {
  const directory = await shortTempHome('atomic-eexist');
  const target = path.join(directory, 'file.json');
  const temporary = `${target}.installing-${process.pid}`;
  await writeFile(temporary, 'orphaned debris from an earlier run that reused this pid');
  await atomicWriteFile(target, 'fresh content');
  assert.equal(await readFile(target, 'utf8'), 'fresh content');
  await assert.rejects(access(temporary));
  await rm(directory, {recursive: true, force: true});
});

// #24 — corrupt/short Keychain token is overwritten, not a dead end.
test('ensureApiBearer overwrites a corrupt or too-short existing token instead of throwing api_token_invalid (finding #24)', async () => {
  let value = 'short'; let writes = 0; let deletes = 0;
  const keychain = {
    async get() { if (value === null) throw {kind: 'not_found'}; return value; },
    async set(_service, _account, next) { writes += 1; value = next; },
    async delete() { deletes += 1; value = null; },
  };
  const result = await ensureApiBearer({keychain, randomBytesImpl: () => Buffer.alloc(32, 9)});
  assert.deepEqual(result, {created: true});
  assert.equal(writes, 1);
  assert.equal(deletes, 0);
  assert.equal(value.length >= 32, true);
});

test('a token overwrite failure still names the exact Keychain remediation command (finding #24)', async () => {
  let value = 'short';
  const keychain = {
    async get() { return value; },
    async set() { throw new Error('keychain_write_failed'); },
    async delete() { value = null; },
  };
  await assert.rejects(
    ensureApiBearer({keychain, randomBytesImpl: () => Buffer.alloc(32, 9)}),
    error => error.code === 'api_token_cleanup_failed' && error.remediation === 'security delete-generic-password -s media.rhize.tasks.api -a bearer' && error.message.includes(error.remediation),
  );
});

// #4 / #9 — stable node path resolution, verified for real capability.
test('resolveInstallNodePath prefers a stable, capable alternate over an ephemeral fnm/nvm/Cellar path (finding #4)', async () => {
  const checkExecutable = async candidate => { if (candidate !== '/opt/homebrew/bin/node') throw new Error('not executable'); };
  const verifyCapable = async candidate => candidate === '/opt/homebrew/bin/node';
  const result = await resolveInstallNodePath('/Users/tom/.local/state/fnm_multishells/12345_1700000000/bin/node', checkExecutable, {verifyCapable});
  assert.equal(result.nodePath, '/opt/homebrew/bin/node');
  assert.deepEqual(result.warnings, []);
});

test('resolveInstallNodePath skips an executable but incapable stable alternate — an old Node or one lacking node:sqlite (finding #9)', async () => {
  // /usr/local/bin/node exists and is executable but is (say) Node 18; only
  // /opt/homebrew/bin/node actually passes the version/node:sqlite probe.
  const checkExecutable = async () => {};
  const verifyCapable = async candidate => candidate === '/opt/homebrew/bin/node';
  const result = await resolveInstallNodePath('/Users/tom/.local/state/fnm_multishells/12345_1700000000/bin/node', checkExecutable, {verifyCapable});
  assert.equal(result.nodePath, '/opt/homebrew/bin/node');
});

test('resolveInstallNodePath fails closed when only an ephemeral path exists, naming the nodejs.org remediation (finding #9)', async () => {
  const checkExecutable = async candidate => { if (candidate.includes('fnm_multishells')) return; throw new Error('not executable'); };
  await assert.rejects(
    resolveInstallNodePath('/Users/tom/.local/state/fnm_multishells/12345_1700000000/bin/node', checkExecutable, {verifyCapable: async () => true, allowEphemeral: false}),
    error => error.code === 'node_path_ephemeral_no_stable_alternative' && /nodejs\.org/.test(error.remediation) && /RHIZE_TASKS_ALLOW_EPHEMERAL_NODE/.test(error.remediation),
  );
});

test('resolveInstallNodePath persists the ephemeral path with a warning only when explicitly overridden (finding #9)', async () => {
  const checkExecutable = async candidate => { if (candidate.includes('fnm_multishells')) return; throw new Error('not executable'); };
  const result = await resolveInstallNodePath('/Users/tom/.local/state/fnm_multishells/12345_1700000000/bin/node', checkExecutable, {verifyCapable: async () => true, allowEphemeral: true});
  assert.equal(result.nodePath, '/Users/tom/.local/state/fnm_multishells/12345_1700000000/bin/node');
  assert.deepEqual(result.warnings, ['node_path_ephemeral:/Users/tom/.local/state/fnm_multishells/12345_1700000000/bin/node']);
});

test('resolveInstallNodePath rejects a node path that is not executable (finding #4)', async () => {
  await assert.rejects(resolveInstallNodePath('/opt/not-node', async () => { throw new Error('ENOENT'); }, {verifyCapable: async () => true}), /node_path_not_executable:\/opt\/not-node/);
});

test('resolveInstallNodePath rejects an executable but incapable stable-looking candidate (finding #9)', async () => {
  await assert.rejects(
    resolveInstallNodePath('/usr/bin/some-old-node', async () => {}, {verifyCapable: async () => false}),
    error => error.code === 'node_path_incapable',
  );
});

test('install records the resolved node path in installation.json for doctor to check (finding #4)', async () => {
  const home = await shortTempHome('nodepath-manifest');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const run = fakeRun(paths.launchAgentPath);
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, nodePath: '/usr/bin/env-node-stub', checkNodePathExecutable: async () => {}, verifyNodePathCapable: async () => true, validate: async () => ({})});
  assert.equal(result.nodePath, '/usr/bin/env-node-stub');
  const manifest = JSON.parse(await readFile(paths.installationManifestPath, 'utf8'));
  assert.equal(manifest.nodePath, '/usr/bin/env-node-stub');
});

test('resolveInstallNodePath default capability probe accepts the real, currently-running node (finding #9)', async () => {
  // Exercises the actual production default (real spawn, real X_OK check,
  // no fakes at all) against process.execPath, which is by construction
  // >=22 with node:sqlite. On a Homebrew machine process.execPath itself is
  // Cellar-shaped (ephemeral), so this also proves the real substitution
  // path lands on a genuinely capable binary, not just any capable-looking
  // one — it doesn't hardcode which exact path comes back.
  const result = await resolveInstallNodePath(process.execPath, file => access(file, fsConstants.X_OK));
  await access(result.nodePath, fsConstants.X_OK);
  assert.deepEqual(result.warnings, []);
});

// #3 — stable version metadata, old-version pruning, signing identity override.
test('install syncs CFBundleShortVersionString/CFBundleVersion into the staged Info.plist from package.json (finding #3)', async () => {
  const home = await shortTempHome('plist-version');
  const {sourceRoot} = await seedInstallSource(home, '0.7.3');
  const paths = exactInstallPaths(home);
  const run = fakeRun(paths.launchAgentPath);
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  const infoPlist = await readFile(path.join(result.appPath, 'Contents', 'Info.plist'), 'utf8');
  assert.match(infoPlist, /<key>CFBundleShortVersionString<\/key>\s*<string>0\.7\.3<\/string>/);
  assert.match(infoPlist, /<key>CFBundleVersion<\/key>\s*<string>0\.7\.3<\/string>/);
});

test('install prunes old runtime version directories after a successful install (finding #3)', async () => {
  const home = await shortTempHome('prune');
  const {sourceRoot} = await seedInstallSource(home, '0.2.0');
  const paths = exactInstallPaths(home);
  const oldVersionDir = path.join(paths.runtimeDir, 'versions', '0.1.0');
  await mkdir(oldVersionDir, {recursive: true});
  await writeFile(path.join(oldVersionDir, 'stale-bundle-marker'), 'stale');
  const run = fakeRun(paths.launchAgentPath);
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  await assert.rejects(access(oldVersionDir));
  await access(result.runtimePath);
});

test('install ad-hoc signs by default but honors RHIZE_TASKS_SIGN_IDENTITY when set (finding #3)', async () => {
  const home = await shortTempHome('sign-identity');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const codesignArgs = [];
  const base = fakeRun(paths.launchAgentPath);
  const run = async (file, args) => {
    if (file === '/usr/bin/codesign') { codesignArgs.push(args); return {code: 0, stdout: ''}; }
    return base(file, args);
  };
  await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  assert.deepEqual(codesignArgs[0].slice(0, 3), ['--force', '--sign', '-']);

  const home2 = await shortTempHome('sign-identity-2');
  const {sourceRoot: sourceRoot2} = await seedInstallSource(home2);
  const paths2 = exactInstallPaths(home2);
  const codesignArgs2 = [];
  const base2 = fakeRun(paths2.launchAgentPath);
  const run2 = async (file, args) => {
    if (file === '/usr/bin/codesign') { codesignArgs2.push(args); return {code: 0, stdout: ''}; }
    return base2(file, args);
  };
  process.env.RHIZE_TASKS_SIGN_IDENTITY = 'Developer ID Application: Rhize Media';
  try {
    await install({paths: paths2, pathPolicy: createTestPathPolicy(home2), sourceRoot: sourceRoot2, run: run2, uid: 501, validate: async () => ({})});
  } finally {
    delete process.env.RHIZE_TASKS_SIGN_IDENTITY;
  }
  assert.deepEqual(codesignArgs2[0].slice(0, 3), ['--force', '--sign', 'Developer ID Application: Rhize Media']);
});

// #25 — codesign before hardenTree, so signature material is also normalized to 0600.
test('codesign runs before hardenTree so _CodeSignature material is also normalized to 0600 (finding #25)', async () => {
  const home = await shortTempHome('sign-order');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const base = fakeRun(paths.launchAgentPath);
  const run = async (file, args) => {
    if (file === '/usr/bin/codesign') {
      const appPathInStage = args.at(-1);
      const codeSigDir = path.join(appPathInStage, 'Contents', '_CodeSignature');
      await mkdir(codeSigDir, {recursive: true});
      await writeFile(path.join(codeSigDir, 'CodeResources'), 'signature', {mode: 0o644});
      return {code: 0, stdout: ''};
    }
    return base(file, args);
  };
  const result = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})});
  const codeResourcesPath = path.join(result.appPath, 'Contents', '_CodeSignature', 'CodeResources');
  assert.equal((await stat(codeResourcesPath)).mode & 0o777, 0o600);
});

// #25 — symlinked $HOME message.
test('a symlinked $HOME reports a clear message instead of reading as a security violation (finding #25)', async () => {
  const real = await shortTempHome('real-home');
  const link = path.join(tmpdir(), `rhize-tasks-home-link-${process.pid}-${Date.now()}`);
  const {symlink} = await import('node:fs/promises');
  await symlink(real, link);
  try {
    const paths = exactInstallPaths(link);
    await assert.rejects(
      install({paths, pathPolicy: createTestPathPolicy(link), sourceRoot: real, run: fakeRun(paths.launchAgentPath), uid: 501, validate: async () => ({})}),
      error => /home_directory_is_symlink/.test(error.message) && /install path checks cannot be enforced/.test(error.message),
    );
  } finally {
    await rm(link, {force: true});
    await rm(real, {recursive: true, force: true});
  }
});

// #25 — secret-scanner false positive on path-shaped placeholder values.
test('renderLaunchAgent does not false-positive on "secrets" appearing inside a path (finding #25)', async () => {
  const dir = await shortTempHome('plist-secretpath');
  const templatePath = path.join(dir, 'template.plist');
  await writeFile(templatePath, await readFile(new URL('../../installer/media.rhize.tasks.plist.template', import.meta.url), 'utf8'));
  const output = await renderLaunchAgent({
    nodePath: '/Users/tom/dev/secrets-tooling/node',
    cliPath: '/Users/tom/dev/secrets-tooling/rhize-tasks/service/bin/rhize-tasks.mjs',
    stdoutPath: '/Users/tom/dev/secrets-tooling/logs/routine.log',
    stderrPath: '/Users/tom/dev/secrets-tooling/logs/routine-error.log',
    templatePath,
  });
  assert.match(output, /secrets-tooling/);
});

test('renderLaunchAgent still rejects a real secret injected outside the known path placeholders (finding #25)', async () => {
  const dir = await shortTempHome('plist-realsecret');
  const templatePath = path.join(dir, 'template.plist');
  const original = await readFile(new URL('../../installer/media.rhize.tasks.plist.template', import.meta.url), 'utf8');
  await writeFile(templatePath, original.replace('<key>Label</key>', '<key>Label</key>\n  <!-- bearer-token-leak -->'));
  await assert.rejects(
    renderLaunchAgent({nodePath: '/opt/node', cliPath: '/opt/cli.mjs', stdoutPath: '/tmp/out', stderrPath: '/tmp/err', templatePath}),
    /launch_agent_may_not_contain_secrets/,
  );
});

// #25 — plist passes --no-warnings so node:sqlite's ExperimentalWarning does not spam the log every 15 minutes.
test('rendered launch agent passes --no-warnings to node so node:sqlite does not spam the log every 15 minutes (finding #25)', async () => {
  const dir = await shortTempHome('plist-nowarn');
  const templatePath = path.join(dir, 'template.plist');
  await writeFile(templatePath, await readFile(new URL('../../installer/media.rhize.tasks.plist.template', import.meta.url), 'utf8'));
  const output = await renderLaunchAgent({nodePath: '/opt/node', cliPath: '/opt/cli.mjs', stdoutPath: '/tmp/out', stderrPath: '/tmp/err', templatePath});
  assert.match(output, /<string>\/opt\/node<\/string>\s*<string>--no-warnings<\/string>\s*<string>\/opt\/cli\.mjs<\/string>/);
});

// #6 — installer errors classify cleanly through the CLI's errorKind, including uppercase Node ERR_* codes.
test('errorKind derives a classification from message or code when .kind is absent (finding #6)', () => {
  assert.equal(errorKind(new Error('macos_14_required')), 'macos_14_required');
  assert.equal(errorKind(Object.assign(new Error('boom'), {code: 'ERR_UNKNOWN_BUILTIN_MODULE'})), 'err_unknown_builtin_module');
  assert.equal(errorKind({kind: 'already_running'}), 'already_running');
  assert.equal(errorKind(new Error('symlink_install_path:/Users/tom')), 'symlink_install_path');
  assert.equal(errorKind(new Error('')), 'command_failed');
  assert.equal(errorKind(null), 'command_failed');
});

test('runChecked failures surface the command, exit code, and output tail instead of a bare command_failed (finding #6)', async () => {
  const home = await shortTempHome('runchecked');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const run = async file => {
    if (file === '/usr/bin/swift') return {code: 1, stdout: 'building...\n', stderr: 'error: CommandLineTools-only toolchain, missing Swift.\n', timedOut: false};
    return {code: 0, stdout: ''};
  };
  await assert.rejects(
    install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}),
    error => error.code === 'installer_command_failed' && error.exitCode === 1 && error.stderr.includes('CommandLineTools-only toolchain'),
  );
});

// #1 — dashboard ensures the server is actually listening before handing back a URL.
test('ensureServerRunning does nothing when the server already answers /health (finding #1)', async () => {
  let spawnCalls = 0;
  await ensureServerRunning('127.0.0.1', 43179, {
    probe: async () => ({status: 'ok', version: '0.1.0'}),
    spawnServe: () => { spawnCalls += 1; return {unref() {}}; },
  });
  assert.equal(spawnCalls, 0);
});

test('ensureServerRunning spawns a detached serve process and waits for health when nothing answers (finding #1)', async () => {
  const spawnCalls = [];
  await ensureServerRunning('127.0.0.1', 43179, {
    probe: async () => null,
    wait: async () => ({status: 'ok', version: '0.1.0'}),
    spawnServe: (nodePath, args, options) => { spawnCalls.push({nodePath, args, options}); return {unref() {}}; },
    cliPath: '/opt/rhize-tasks/service/bin/rhize-tasks.mjs',
    nodePath: '/opt/node',
    mkdirImpl: async () => {},
    openLogFd: () => 7,
    closeLogFd: () => {},
  });
  assert.equal(spawnCalls.length, 1);
  assert.equal(spawnCalls[0].nodePath, '/opt/node');
  assert.deepEqual(spawnCalls[0].args, ['/opt/rhize-tasks/service/bin/rhize-tasks.mjs', 'serve']);
  assert.equal(spawnCalls[0].options.detached, true);
});

test('ensureServerRunning throws a diagnosable error when the spawned server never becomes healthy (finding #1)', async () => {
  await assert.rejects(
    ensureServerRunning('127.0.0.1', 43179, {
      probe: async () => null,
      wait: async () => null,
      spawnServe: () => ({unref() {}}),
      mkdirImpl: async () => {},
      openLogFd: () => 7,
      closeLogFd: () => {},
    }),
    error => error.code === 'dashboard_server_did_not_start',
  );
});

// #1-followup — reinstall/uninstall must be able to find and stop a
// dashboard-spawned `serve` process via its pidfile, instead of either
// failing outright (checkLoopbackPort) or deleting the runtime out from
// under it (uninstall).
test('the serve command writes a pidfile on start and removes it on shutdown (finding #1)', async () => {
  const directory = await shortTempHome('servepid');
  const stored = new Map([['media.rhize.tasks.api\0bearer', 't'.repeat(43)]]);
  const keychain = {
    async get(service, account) { const value = stored.get(`${service}\0${account}`); if (!value) throw {kind: 'not_found'}; return value; },
    async set(service, account, value) { stored.set(`${service}\0${account}`, value); },
    async delete(service, account) { stored.delete(`${service}\0${account}`); },
  };
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain, connectors: {jira: empty, calendar: empty, reminders: empty, slack: empty}, port: 0, host: '127.0.0.1'});
  const pidPath = path.join(directory, 'serve.pid');
  let releaseShutdown;
  const runPromise = runCli(['serve'], {
    createContext: async () => context,
    servePidFilePath: pidPath,
    waitForShutdown: () => new Promise(resolve => { releaseShutdown = resolve; }),
    stdout: () => {},
  });
  const deadline = Date.now() + 3_000;
  while (!(await access(pidPath).then(() => true, () => false)) && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(await readFile(pidPath, 'utf8'), String(process.pid));
  releaseShutdown();
  await runPromise;
  await assert.rejects(access(pidPath));
  await rm(directory, {recursive: true, force: true});
});

test('serve writes its pidfile before listening, so a write failure never leaves a listening server untracked (finding #1-followup)', async () => {
  const directory = await shortTempHome('servepid-writefail');
  const stored = new Map([['media.rhize.tasks.api\0bearer', 't'.repeat(43)]]);
  const keychain = {
    async get(service, account) { const value = stored.get(`${service}\0${account}`); if (!value) throw {kind: 'not_found'}; return value; },
    async set(service, account, value) { stored.set(`${service}\0${account}`, value); },
    async delete(service, account) { stored.delete(`${service}\0${account}`); },
  };
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain, connectors: {jira: empty, calendar: empty, reminders: empty, slack: empty}, port: 0, host: '127.0.0.1'});
  let listenAttempted = false;
  const spyingWaitForShutdown = server => { listenAttempted = server.listening === true; return new Promise(() => {}); };
  await assert.rejects(
    runCli(['serve'], {
      createContext: async () => context,
      servePidFilePath: path.join(directory, 'serve.pid'),
      writeServePid: async () => { throw new Error('disk_full'); },
      waitForShutdown: spyingWaitForShutdown,
      stdout: () => {},
    }),
    /disk_full/,
  );
  assert.equal(listenAttempted, false, 'listen() must never be attempted when the pidfile write fails');
  await rm(directory, {recursive: true, force: true});
});

test('serve cleans up its pidfile when listen() fails after a successful write, instead of leaving it stale (finding #1-followup)', async () => {
  const directory = await shortTempHome('servepid-listenfail');
  const stored = new Map([['media.rhize.tasks.api\0bearer', 't'.repeat(43)]]);
  const keychain = {
    async get(service, account) { const value = stored.get(`${service}\0${account}`); if (!value) throw {kind: 'not_found'}; return value; },
    async set(service, account, value) { stored.set(`${service}\0${account}`, value); },
    async delete(service, account) { stored.delete(`${service}\0${account}`); },
  };
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  // port: -1 makes the real net.Server.listen() reject synchronously with
  // ERR_SOCKET_BAD_PORT, giving a real (not faked) listen failure.
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain, connectors: {jira: empty, calendar: empty, reminders: empty, slack: empty}, port: -1, host: '127.0.0.1'});
  const pidPath = path.join(directory, 'serve.pid');
  await assert.rejects(runCli(['serve'], {createContext: async () => context, servePidFilePath: pidPath, stdout: () => {}}));
  await assert.rejects(access(pidPath), /ENOENT/);
  await rm(directory, {recursive: true, force: true});
});

test('checkLoopbackPort stops its own server via the pidfile and proceeds instead of throwing a bare port conflict (finding #1)', async () => {
  // First bind attempt (the initial probe) finds the port busy; the second
  // (after stopOwnServer reports success) must succeed, proving the port
  // was genuinely re-checked rather than just trusted.
  let bindAttempts = 0;
  const fakeCreateServer = () => ({
    unref() {},
    once(_event, handler) { this.errorHandler = handler; },
    listen(_options, callback) {
      bindAttempts += 1;
      if (bindAttempts === 1) { const error = new Error('busy'); error.code = 'EADDRINUSE'; this.errorHandler(error); return; }
      callback();
    },
    close(callback) { callback?.(); },
  });
  const stopCalls = [];
  await checkLoopbackPort(43179, {
    createServerImpl: fakeCreateServer,
    probeOwnServer: async () => ({status: 'ok', version: '0.1.0'}),
    pidPath: '/tmp/does-not-matter.pid',
    stopOwnServer: async options => { stopCalls.push(options); return {stopped: true, reason: 'terminated'}; },
  });
  assert.deepEqual(stopCalls, [{pidPath: '/tmp/does-not-matter.pid'}]);
  assert.equal(bindAttempts, 2);
});

test('checkLoopbackPort fails loudly, naming why, when it cannot confirm its own server actually stopped (finding #1)', async () => {
  const fakeCreateServer = () => ({
    unref() {},
    once(_event, handler) { this.handler = handler; },
    listen() { const error = new Error('busy'); error.code = 'EADDRINUSE'; this.handler(error); },
  });
  await assert.rejects(
    checkLoopbackPort(43179, {
      createServerImpl: fakeCreateServer,
      probeOwnServer: async () => ({status: 'ok', version: '0.1.0'}),
      stopOwnServer: async () => ({stopped: false, reason: 'timed_out'}),
    }),
    error => error.code === 'loopback_port_held_by_own_server' && error.reason === 'timed_out',
  );
});

test('checkLoopbackPort actually stops a real detached process via its pidfile (finding #1)', async () => {
  // End-to-end proof of the real, non-faked stopServeProcessIfRunning path:
  // spawn a real dummy "serve" stand-in, write its pid to a file, and
  // confirm checkLoopbackPort's default stopOwnServer terminates it.
  const dir = await shortTempHome('stopserver');
  const pidPath = path.join(dir, 'serve.pid');
  const child = spawn(process.execPath, ['--input-type=module', '--eval', "setInterval(() => {}, 1000); process.stdout.write('ready\\n');"], {stdio: ['ignore', 'pipe', 'ignore']});
  await new Promise((resolve, reject) => {
    child.stdout.once('data', () => resolve());
    setTimeout(() => reject(new Error('dummy server did not start')), 3_000).unref?.();
  });
  await writeFile(pidPath, String(child.pid));
  let bindAttempts = 0;
  const fakeCreateServer = () => ({
    unref() {},
    once(_event, handler) { this.errorHandler = handler; },
    listen(_options, callback) {
      bindAttempts += 1;
      if (bindAttempts === 1) { const error = new Error('busy'); error.code = 'EADDRINUSE'; this.errorHandler(error); return; }
      callback();
    },
    close(callback) { callback?.(); },
  });
  await checkLoopbackPort(43179, {createServerImpl: fakeCreateServer, probeOwnServer: async () => ({status: 'ok', version: '0.1.0'}), pidPath});
  assert.throws(() => process.kill(child.pid, 0), /ESRCH/);
  await rm(dir, {recursive: true, force: true});
});

test('uninstall stops its own running server before deleting the runtime/database out from under it (finding #1)', async () => {
  const root = await shortTempHome('uninstall-stopserver');
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  const stopCalls = [];
  await uninstallRuntime({
    choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501,
    stopOwnServer: async options => { stopCalls.push(options); return {stopped: true, reason: 'terminated'}; },
  });
  assert.deepEqual(stopCalls, [{pidPath: servePidPath(paths.supportDir)}]);
});

test('uninstall aborts instead of deleting the runtime when it cannot confirm its own server stopped (finding #1)', async () => {
  const root = await shortTempHome('uninstall-stopserver-fail');
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  await assert.rejects(
    uninstallRuntime({
      choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501,
      stopOwnServer: async () => ({stopped: false, reason: 'timed_out'}),
    }),
    error => error.code === 'own_server_stop_failed',
  );
  await access(paths.runtimeDir);
});

test('uninstall probes /health and aborts instead of deleting the runtime when no pidfile exists but a server still answers (finding #1-followup)', async () => {
  // "No pidfile" used to be trusted as "nothing to stop" outright — but an
  // install from before the pidfile mechanism existed, a manually deleted
  // pidfile, or a corrupted write could all leave a real server running
  // with no pidfile pointing at it.
  const root = await shortTempHome('uninstall-nopid-answering');
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  const probeCalls = [];
  await assert.rejects(
    uninstallRuntime({
      choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501, port: 43179,
      // No pidfile at all -> the real stopServeProcessIfRunning default reports 'no_pid_file'.
      probeOwnServer: async port => { probeCalls.push(port); return {status: 'ok', version: '0.1.0'}; },
    }),
    error => error.code === 'own_server_stop_failed' && error.reason === 'no_pid_file_but_still_answering',
  );
  assert.deepEqual(probeCalls, [43179]);
  await access(paths.runtimeDir);
});

test('uninstall proceeds when there is no pidfile and nothing answers /health either (finding #1-followup)', async () => {
  const root = await shortTempHome('uninstall-nopid-quiet');
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  const result = await uninstallRuntime({
    choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501,
    // Real stopServeProcessIfRunning default -> no pidfile -> 'no_pid_file'; probe confirms quiet.
    probeOwnServer: async () => null,
  });
  assert.equal(result.ok, true);
  await assert.rejects(access(paths.runtimeDir));
});

// #4 rollback ordering — a failure before the old agent was ever stopped
// must not attempt to "restore" it, and a failure after the swap where we
// cannot confirm the new job is stopped must not touch the runtime/plist.
test('a stage-build failure before the old agent is stopped never attempts to re-bootstrap it (finding #4-followup)', async () => {
  const home = await shortTempHome('preswap-fail');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'old plist');
  const bootstrapCalls = [];
  const helperHandler = helperSucceedsHandler(paths);
  const run = async (file, args) => {
    if (file === '/usr/bin/codesign') throw new Error('codesign_unavailable');
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    // No prior helper in this scenario — only the routine's prior agent
    // matters to this test.
    if (args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'))) return helperHandler(args);
    if (args[0] === 'print') return {code: 0, stdout: `path = ${paths.launchAgentPath}\n`};
    if (args[0] === 'bootstrap') bootstrapCalls.push(args);
    return {code: 0, stdout: ''};
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => error.activationState === 'stage_build_failed');
  assert.deepEqual(bootstrapCalls, [], 'the old agent was never stopped, so rollback must never try to re-bootstrap it');
  assert.equal(await readFile(paths.launchAgentPath, 'utf8'), 'old plist', 'untouched throughout');
});

test('a post-swap failure that cannot confirm the new job stopped leaves the runtime and plist untouched, reporting manual recovery (finding #4-followup)', async () => {
  const home = await shortTempHome('postswap-fail');
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await mkdir(paths.supportDir, {recursive: true});
  await writeFile(paths.launchAgentPath, 'old plist');
  await writeFile(paths.installationManifestPath, 'old manifest');
  const helperHandler = helperSucceedsHandler(paths);
  const run = async (file, args) => {
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    // No prior helper in this scenario — only the routine's prior agent
    // matters to this test, so the helper's own swap+rollback proceeds
    // uneventfully while the routine's bootout is what can never be
    // confirmed (both the forward attempt and rollback's own re-attempt hit
    // the same unconditional throw below).
    if (args.some(arg => typeof arg === 'string' && arg.includes('reminders-helper'))) return helperHandler(args);
    if (args[0] === 'print') return {code: 0, stdout: `path = ${paths.launchAgentPath}\n`};
    if (args[0] === 'bootout') throw new Error('unconfirmable');
    return {code: 0, stdout: ''};
  };
  const error = await install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}).catch(value => value);
  assert.ok(error, 'install must reject');
  assert.match(error.rollbackState, /manual_recovery_required/);
  // The runtime/plist must be left exactly as the (uncertain) forward path
  // left them — NOT reverted — because we could never confirm it was safe.
  assert.equal(await readFile(paths.launchAgentPath, 'utf8'), 'old plist', 'first bootout of the OLD agent also throws in this fake, so the plist was never actually overwritten');
});

// #11 — the CLI boundary must not drop runChecked's stdout/stderr tail.
test('serializeError includes the command, exit code, and stderr/stdout tails when present (finding #11)', () => {
  const bare = serializeError(new Error('macos_14_required'));
  assert.deepEqual(bare, {kind: 'macos_14_required'});
  const rich = Object.assign(new Error('installer_command_failed:swift:exit_1'), {
    code: 'installer_command_failed', command: '/usr/bin/swift', exitCode: 1,
    stdout: 'building...\n', stderr: 'error: CommandLineTools-only toolchain, missing Swift.\n',
  });
  assert.deepEqual(serializeError(rich), {
    kind: 'installer_command_failed', command: '/usr/bin/swift', exitCode: 1,
    stdoutTail: 'building...\n', stderrTail: 'error: CommandLineTools-only toolchain, missing Swift.\n',
  });
});

test('main() serializes the runChecked stderr tail at the real CLI boundary, not just on the internal error object (finding #11)', async () => {
  const enriched = Object.assign(new Error('installer_command_failed:swift:exit_1'), {
    code: 'installer_command_failed', command: '/usr/bin/swift', exitCode: 1,
    stdout: '', stderr: 'error: CommandLineTools-only toolchain, missing Swift.\n',
  });
  const written = [];
  const originalWrite = process.stderr.write;
  const originalExitCode = process.exitCode;
  process.stderr.write = chunk => { written.push(chunk.toString()); return true; };
  try {
    await main(['install'], {installLocal: async () => { throw enriched; }});
  } finally {
    process.stderr.write = originalWrite;
  }
  assert.equal(process.exitCode, 1);
  process.exitCode = originalExitCode;
  const payload = JSON.parse(written.join(''));
  assert.equal(payload.ok, false);
  assert.equal(payload.error.kind, 'installer_command_failed');
  assert.equal(payload.error.exitCode, 1);
  assert.match(payload.error.stderrTail, /CommandLineTools-only toolchain/);
});
