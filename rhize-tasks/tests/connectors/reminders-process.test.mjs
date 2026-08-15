import assert from 'node:assert/strict';
import {access, mkdir, mkdtemp, readFile, readdir, rename, rm, stat, symlink, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {runProcess} from '../../service/src/connectors/process-runner.mjs';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';
import {atomicWriteFile, checkLoopbackPort, install, renderLaunchAgent, runRemindersAccessProbe, validatePrerequisites} from '../../installer/install.mjs';
import {parseUninstallChoice, uninstall} from '../../installer/uninstall.mjs';
import {createTestPathPolicy, exactInstallPaths} from '../../installer/safe-paths.mjs';
import {isKnownBootoutNotLoaded, isKnownPrintNotLoaded} from '../../installer/launchctl.mjs';

async function seedInstallSource(home, version = '0.1.0') {
  const sourceRoot = path.join(home, 'plugin');
  const packageRoot = path.join(sourceRoot, 'native', 'reminders-helper');
  await mkdir(path.join(packageRoot, '.build', 'release'), {recursive: true});
  await mkdir(path.join(packageRoot, 'Resources'), {recursive: true});
  await mkdir(path.join(sourceRoot, 'service', 'bin'), {recursive: true});
  await mkdir(path.join(sourceRoot, 'schemas'), {recursive: true});
  await writeFile(path.join(packageRoot, '.build', 'release', 'RhizeRemindersHelper'), '#!/bin/sh\n');
  await writeFile(path.join(packageRoot, 'Resources', 'Info.plist'), '<plist version="1.0"><dict/></plist>');
  await writeFile(path.join(sourceRoot, 'package.json'), `${JSON.stringify({name: 'rhize-tasks', version})}\n`);
  await writeFile(path.join(sourceRoot, 'service', 'bin', 'rhize-tasks.mjs'), 'process.exit(0);\n');
  await writeFile(path.join(sourceRoot, 'schemas', 'task.schema.json'), '{}\n');
  return {sourceRoot, packageRoot};
}

function fakeInstallerRun({loaded = false, bootstrapCode = 0, bootoutCode = 0, calls = [], plistPath = '/tmp/media.rhize.tasks.plist'} = {}) {
  let isLoaded = loaded;
  return async (file, args) => {
    calls.push([file, args]);
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    if (args[0] === 'print') return isLoaded ? {code: 0, stdout: `path = ${plistPath}\n`} : {code: 113, stderr: 'Bad request.\nCould not find service "media.rhize.tasks" in domain for user gui: 501'};
    if (args[0] === 'bootout') { if (bootoutCode === 0) isLoaded = false; return bootoutCode === 0 ? {code: 0, stdout: ''} : {code: bootoutCode, stderr: 'Input/output error'}; }
    if (args[0] === 'bootstrap') { if (bootstrapCode === 0) isLoaded = true; return {code: bootstrapCode, stderr: bootstrapCode === 0 ? '' : 'Bootstrap failed'}; }
    return {code: 0, stdout: ''};
  };
}

test('launchctl print and bootout use independent narrow absent-service classifiers', () => {
  const expected = {domain: 'gui/501', label: 'media.rhize.tasks'};
  assert.equal(isKnownPrintNotLoaded({code: 113, stderr: 'Bad request.\nCould not find service "media.rhize.tasks" in domain for user gui: 501'}, expected), true);
  assert.equal(isKnownPrintNotLoaded({code: 113, stderr: 'Could not find service "other" in domain for user gui: 501'}, expected), false);
  assert.equal(isKnownPrintNotLoaded({code: 113, stderr: 'Input/output error'}, expected), false);
  assert.equal(isKnownBootoutNotLoaded({code: 3, stderr: 'Boot-out failed: 3: No such process'}), true);
  assert.equal(isKnownBootoutNotLoaded({code: 113, stderr: 'Could not find service "media.rhize.tasks" in domain for user gui: 501'}), false);
});

test('process runner writes one request, captures one response, and enforces timeout', async () => {
  const echo = await runProcess(process.execPath, ['--input-type=module', '--eval', 'process.stdin.pipe(process.stdout)'], {input: '{"command":"lists"}\n', timeoutMs: 2_000});
  assert.equal(echo.code, 0);
  assert.equal(echo.stdout, '{"command":"lists"}\n');
  const timeout = await runProcess(process.execPath, ['--input-type=module', '--eval', 'setInterval(() => {}, 1000)'], {timeoutMs: 20});
  assert.equal(timeout.timedOut, true);
});

test('connector uses newline-delimited JSON, fixed list environment, and rejects malformed extra lines', async () => {
  let invocation;
  const connector = createRemindersConnector({helperPath: '/helper', tasksListId: 'rhize', runner: async (...args) => {
    invocation = args;
    return {code: 0, stdout: '{"ok":true,"items":[]}\n'};
  }});
  await connector.readSnapshot();
  assert.equal(invocation[2].input.endsWith('\n'), true);
  assert.equal(invocation[2].env.RHIZE_TASKS_REMINDERS_LIST_ID, 'rhize');
  assert.equal(Object.hasOwn(invocation[2].env, 'JIRA_API_TOKEN'), false);
  const malformed = createRemindersConnector({helperPath: '/helper', tasksListId: 'rhize', runner: async () => ({code: 0, stdout: '{}\n{}\n'})});
  await assert.rejects(malformed.readSnapshot(), error => error.kind === 'malformed_response');
});

test('connector requires proven command-specific helper results', async () => {
  const operation = {kind: 'reminder_upsert', targetId: 'RHIZE-1', idempotencyKey: 'op-1', payload: {listId: 'rhize', title: 'Task', dueAt: null, notes: '', externalId: 'RHIZE-1'}};
  for (const response of [
    {},
    {ok: true},
    {ok: true, id: 'OTHER-1', revision: '1'},
    {ok: true, id: 'RHIZE-1'},
  ]) {
    const connector = createRemindersConnector({helperPath: '/helper', tasksListId: 'rhize', runner: async () => ({code: 0, stdout: `${JSON.stringify(response)}\n`})});
    await assert.rejects(connector.applyOperation(operation), error => error.kind === 'malformed_response');
  }
  const missingAuthorization = createRemindersConnector({helperPath: '/helper', tasksListId: 'rhize', runner: async () => ({code: 0, stdout: '{"ok":true}\n'})});
  await assert.rejects(missingAuthorization.health(), error => error.kind === 'malformed_response');
  const missingLists = createRemindersConnector({helperPath: '/helper', tasksListId: 'rhize', runner: async () => ({code: 0, stdout: '{"ok":true,"items":[]}\n'})});
  await assert.rejects(missingLists.discover(), error => error.kind === 'malformed_response');
  const mismatchedDelete = createRemindersConnector({helperPath: '/helper', tasksListId: 'rhize', runner: async () => ({code: 0, stdout: '{"ok":true,"id":"OTHER-1","revision":"1"}\n'})});
  await assert.rejects(mismatchedDelete.applyOperation({kind: 'reminder_delete', targetId: 'RHIZE-1', idempotencyKey: 'op-2', payload: {}}), error => error.kind === 'malformed_response');
});

test('process runner stops output beyond the configured ceiling', async () => {
  const result = await runProcess(process.execPath, ['--input-type=module', '--eval', 'process.stdout.write("x".repeat(4096))'], {maxOutputBytes: 32, timeoutMs: 2_000});
  assert.equal(result.outputExceeded, true);
  assert.equal(result.code, 1);
});

test('approved reversible probe creates then deletes the same stable item', async () => {
  const requests = [];
  const runner = async (_file, _args, options) => {
    requests.push(JSON.parse(options.input));
    return {code: 0, stdout: `${JSON.stringify({ok: true, id: requests.at(-1).externalId ?? requests.at(-1).id, revision: '1'})}\n`};
  };
  await assert.rejects(runRemindersAccessProbe({approved: false, helperPath: '/helper', listId: 'rhize', operationId: 'op', runner}), /approval_required/);
  await runRemindersAccessProbe({approved: true, helperPath: '/helper', listId: 'rhize', operationId: 'op', runner});
  assert.deepEqual(requests.map(value => value.command), ['upsert', 'delete']);
  assert.equal(requests[0].externalId, requests[1].id);
});

test('probe reports cleanup failure instead of claiming success', async () => {
  let calls = 0;
  await assert.rejects(runRemindersAccessProbe({
    approved: true, helperPath: '/helper', listId: 'rhize', operationId: 'op',
    runner: async () => (++calls === 1 ? {code: 0, stdout: '{"ok":true,"id":"access-probe:op","revision":"1"}\n'} : {code: 0, stdout: '{"ok":true,"id":"wrong","revision":"2"}\n'}),
  }), /cleanup_failed/);
});

test('probe rejects unproven creation before attempting cleanup', async () => {
  let calls = 0;
  await assert.rejects(runRemindersAccessProbe({
    approved: true, helperPath: '/helper', listId: 'rhize', operationId: 'op',
    runner: async () => { calls += 1; return {code: 0, stdout: '{}\n'}; },
  }), /reminders_probe_failed/);
  assert.equal(calls, 1);
});

test('installer preflight enforces macOS, Node floor, tools, writable support, and loopback check', async () => {
  const calls = [];
  const options = {
    platform: 'darwin', macOSVersion: '14.0', nodeVersion: '22.1.0', supportDir: '/tmp/Rhize Tasks', port: 43179,
    accessImpl: async value => calls.push(['access', value]),
    mkdirImpl: async value => calls.push(['mkdir', value]),
    chmodImpl: async value => calls.push(['chmod', value]),
    checkPort: async value => calls.push(['port', value]),
  };
  const result = await validatePrerequisites(options);
  assert.equal(result.nodeMajor, 22);
  assert.ok(calls.some(call => call[0] === 'port'));
  await assert.rejects(validatePrerequisites({...options, platform: 'linux'}), /macos_required/);
  await assert.rejects(validatePrerequisites({...options, macOSVersion: '13.6.9'}), /macos_14_required/);
  await assert.rejects(validatePrerequisites({...options, nodeVersion: '21.9.0'}), /node_22_required/);
});

test('loopback check normalizes occupied port', async () => {
  const fake = () => ({
    unref() {},
    once(_event, handler) { this.handler = handler; },
    listen() { const error = new Error('busy'); error.code = 'EADDRINUSE'; this.handler(error); },
  });
  await assert.rejects(checkLoopbackPort(43179, {createServerImpl: fake}), /loopback_port_in_use/);
});

test('launch agent has explicit paths, one catch-up command, and no secret material', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-plist-'));
  const templatePath = path.join(dir, 'template.plist');
  await writeFile(templatePath, await readFile(new URL('../../installer/media.rhize.tasks.plist.template', import.meta.url), 'utf8'));
  const output = await renderLaunchAgent({nodePath: '/opt/node', cliPath: '/opt/rhize tasks/cli.mjs', stdoutPath: '/tmp/out', stderrPath: '/tmp/err', templatePath});
  assert.match(output, /<string>catch-up<\/string>/);
  assert.equal((output.match(/<key>Label<\/key>/g) ?? []).length, 1);
  assert.doesNotMatch(output, /bearer|password|secret/i);
  assert.match(output, /rhize tasks/);
});

test('helper app metadata has a stable identity and Reminders privacy purpose', async () => {
  const info = await readFile(new URL('../../native/reminders-helper/Resources/Info.plist', import.meta.url), 'utf8');
  assert.match(info, /<string>media\.rhize\.tasks\.reminders-helper<\/string>/);
  assert.match(info, /<key>NSRemindersUsageDescription<\/key>/);
  assert.match(info, /<key>NSRemindersFullAccessUsageDescription<\/key>/);
});

test('installer constructs and signs the app then bootstraps one user agent', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-install-'));
  const {sourceRoot} = await seedInstallSource(root);
  await writeFile(path.join(sourceRoot, 'service', '.env'), 'SECRET=do-not-copy\n');
  await writeFile(path.join(sourceRoot, 'service', 'history.sqlite'), 'do-not-copy');
  const paths = exactInstallPaths(root);
  const calls = [];
  const run = fakeInstallerRun({calls, plistPath: paths.launchAgentPath});
  const result = await install({paths, pathPolicy: createTestPathPolicy(root), sourceRoot, run, uid: 501, nodePath: '/opt/node', validate: async () => ({})});
  await access(path.join(result.appPath, 'Contents', 'MacOS', 'RhizeRemindersHelper'));
  await access(path.join(result.runtimePath, 'service', 'bin', 'rhize-tasks.mjs'));
  await access(path.join(result.runtimePath, 'schemas', 'task.schema.json'));
  await assert.rejects(access(path.join(result.runtimePath, 'service', '.env')));
  await assert.rejects(access(path.join(result.runtimePath, 'service', 'history.sqlite')));
  assert.ok(calls.some(([file, args]) => file === '/usr/bin/codesign' && args.includes('--sign')));
  assert.equal(calls.filter(([file, args]) => file === '/bin/launchctl' && args[0] === 'bootstrap').length, 1);
  const plist = await readFile(paths.launchAgentPath, 'utf8');
  assert.match(plist, new RegExp(result.runtimePath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.doesNotMatch(plist, new RegExp(sourceRoot.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.equal((await stat(paths.supportDir)).mode & 0o777, 0o700);
  assert.equal((await stat(paths.runtimeDir)).mode & 0o777, 0o700);
  assert.equal((await stat(paths.logDir)).mode & 0o777, 0o700);
  assert.equal((await stat(paths.launchAgentPath)).mode & 0o777, 0o600);
  assert.equal((await stat(paths.installationManifestPath)).mode & 0o777, 0o600);
  assert.equal((await stat(path.join(result.runtimePath, 'schemas', 'task.schema.json'))).mode & 0o777, 0o600);
  assert.equal((await stat(path.join(result.appPath, 'Contents', 'MacOS', 'RhizeRemindersHelper'))).mode & 0o777, 0o700);
  assert.match(result.runtimePath, /runtime\/versions\/0\.1\.0$/);
});

test('installer rejects incomplete paths before any command or filesystem write', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-incomplete-paths-'));
  const paths = exactInstallPaths(home);
  delete paths.runtimeDir;
  let calls = 0;
  await assert.rejects(install({
    paths,
    pathPolicy: createTestPathPolicy(home),
    run: async () => { calls += 1; return {code: 0}; },
    validate: async () => { calls += 1; },
  }), /unsafe_install_path_runtimeDir/);
  assert.equal(calls, 0);
});

test('initial install bootstrap failure rolls back all introduced metadata and runtime', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-bootstrap-fail-'));
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const run = fakeInstallerRun({bootstrapCode: 5, plistPath: paths.launchAgentPath});
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => error.code === 'local_activation_failed' && error.activationState === 'bootstrap_failed');
  await assert.rejects(access(paths.launchAgentPath));
  await assert.rejects(access(paths.installationManifestPath));
  await assert.rejects(access(path.join(paths.runtimeDir, 'versions', '0.1.0')));
});

test('upgrade bootstrap failure restores prior bytes, modes, runtime, and loaded service', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-upgrade-fail-'));
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const priorRuntime = path.join(paths.runtimeDir, 'versions', '0.1.0');
  const priorPlist = Buffer.from('prior plist\n');
  const priorManifest = Buffer.from(`${JSON.stringify({schemaVersion: 1, runtimePath: priorRuntime, cliPath: path.join(priorRuntime, 'service', 'bin', 'rhize-tasks.mjs')})}\n`);
  await mkdir(path.join(priorRuntime, 'service', 'bin'), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(path.join(priorRuntime, 'old-runtime-marker'), 'old');
  await writeFile(paths.launchAgentPath, priorPlist, {mode: 0o640});
  await writeFile(paths.installationManifestPath, priorManifest, {mode: 0o640});
  const calls = [];
  let loaded = true;
  let bootstrapCalls = 0;
  const run = async (file, args) => {
    calls.push([file, args]);
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    if (args[0] === 'print') return loaded ? {code: 0, stdout: `path = ${paths.launchAgentPath}\n`} : {code: 113, stderr: 'Bad request.\nCould not find service "media.rhize.tasks" in domain for user gui: 501'};
    if (args[0] === 'bootout') { loaded = false; return {code: 0, stdout: ''}; }
    if (args[0] === 'bootstrap') { bootstrapCalls += 1; if (bootstrapCalls === 1) return {code: 5, stderr: 'Bootstrap failed'}; loaded = true; return {code: 0, stdout: ''}; }
    return {code: 0, stdout: ''};
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => error.code === 'local_activation_failed');
  assert.deepEqual(await readFile(paths.launchAgentPath), priorPlist);
  assert.deepEqual(await readFile(paths.installationManifestPath), priorManifest);
  assert.equal((await stat(paths.launchAgentPath)).mode & 0o777, 0o640);
  assert.equal((await stat(paths.installationManifestPath)).mode & 0o777, 0o640);
  assert.equal(await readFile(path.join(priorRuntime, 'old-runtime-marker'), 'utf8'), 'old');
  assert.equal(bootstrapCalls, 2);
  assert.equal(loaded, true);
});

test('verification failure after successful bootstrap boots out new state and restores the exact prior cross-version config', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-verify-rollback-'));
  const {sourceRoot} = await seedInstallSource(home, '0.2.0');
  const paths = exactInstallPaths(home);
  const priorRuntime = path.join(paths.runtimeDir, 'versions', '0.1.0');
  const newRuntime = path.join(paths.runtimeDir, 'versions', '0.2.0');
  const priorPlist = Buffer.from(`old-runtime=${priorRuntime}\n`);
  const priorManifest = Buffer.from(`${JSON.stringify({schemaVersion: 1, version: '0.1.0', runtimePath: priorRuntime, cliPath: path.join(priorRuntime, 'service', 'bin', 'rhize-tasks.mjs')})}\n`);
  await mkdir(path.join(priorRuntime, 'service', 'bin'), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(path.join(priorRuntime, 'old-runtime-marker'), 'old');
  await writeFile(paths.launchAgentPath, priorPlist);
  await writeFile(paths.installationManifestPath, priorManifest);
  let loaded = true;
  let printCalls = 0;
  let bootstrapCalls = 0;
  let restoredBootstrapPlist = null;
  const run = async (file, args) => {
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    if (args[0] === 'print') {
      printCalls += 1;
      if (printCalls === 2) return {code: 5, stderr: 'state temporarily unavailable'};
      return loaded ? {code: 0, stdout: `path = ${paths.launchAgentPath}\n`} : {code: 113, stderr: 'Bad request.\nCould not find service "media.rhize.tasks" in domain for user gui: 501'};
    }
    if (args[0] === 'bootout') { loaded = false; return {code: 0, stdout: ''}; }
    if (args[0] === 'bootstrap') { bootstrapCalls += 1; if (bootstrapCalls === 2) restoredBootstrapPlist = await readFile(args[2]); loaded = true; return {code: 0, stdout: ''}; }
    return {code: 0, stdout: ''};
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => error.activationState === 'activation_verification_failed' && error.rollbackState === 'restored');
  assert.deepEqual(await readFile(paths.launchAgentPath), priorPlist);
  assert.deepEqual(await readFile(paths.installationManifestPath), priorManifest);
  assert.equal(await readFile(path.join(priorRuntime, 'old-runtime-marker'), 'utf8'), 'old');
  await assert.rejects(access(newRuntime));
  assert.equal(loaded, true);
  assert.equal(bootstrapCalls, 2);
  assert.deepEqual(restoredBootstrapPlist, priorPlist);
});

test('ambiguous new bootstrap is treated as possibly loaded and restored to the prior agent', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-ambiguous-bootstrap-'));
  const {sourceRoot} = await seedInstallSource(home, '0.2.0');
  const paths = exactInstallPaths(home);
  const priorRuntime = path.join(paths.runtimeDir, 'versions', '0.1.0');
  await mkdir(path.join(priorRuntime, 'service', 'bin'), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, `old=${priorRuntime}\n`);
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, version: '0.1.0', runtimePath: priorRuntime})}\n`);
  let loaded = true;
  let bootstrapCalls = 0;
  let bootoutCalls = 0;
  const run = async (file, args) => {
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    if (args[0] === 'print') return loaded ? {code: 0, stdout: `path = ${paths.launchAgentPath}\n`} : {code: 113, stderr: 'Could not find service "media.rhize.tasks" in domain for user gui: 501'};
    if (args[0] === 'bootout') { bootoutCalls += 1; loaded = false; return {code: 0, stdout: ''}; }
    if (args[0] === 'bootstrap') {
      bootstrapCalls += 1;
      loaded = true;
      if (bootstrapCalls === 1) throw new Error('lost bootstrap response');
      return {code: 0, stdout: ''};
    }
    return {code: 0, stdout: ''};
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => error.activationState === 'bootstrap_failed' && error.rollbackState === 'restored');
  assert.equal(loaded, true);
  assert.equal(bootstrapCalls, 2);
  assert.equal(bootoutCalls, 2);
  assert.match(await readFile(paths.launchAgentPath, 'utf8'), /0\.1\.0/);
});

test('prior-unloaded rollback removes a newly loaded service even when the restored plist is absent', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-unloaded-rollback-'));
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  let loaded = false;
  let printCalls = 0;
  let bootoutCalls = 0;
  const run = async (file, args) => {
    if (file !== '/bin/launchctl') return {code: 0, stdout: ''};
    if (args[0] === 'print') {
      printCalls += 1;
      if (printCalls === 2) return {code: 5, stderr: 'state temporarily unavailable'};
      return loaded ? {code: 0, stdout: `path = ${paths.launchAgentPath}\n`} : {code: 113, stderr: 'Could not find service "media.rhize.tasks" in domain for user gui: 501'};
    }
    if (args[0] === 'bootstrap') { loaded = true; return {code: 0, stdout: ''}; }
    if (args[0] === 'bootout') { bootoutCalls += 1; loaded = false; return {code: 0, stdout: ''}; }
    return {code: 0, stdout: ''};
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => error.activationState === 'activation_verification_failed' && error.rollbackState === 'restored');
  assert.equal(loaded, false);
  assert.equal(bootoutCalls, 1);
  await assert.rejects(access(paths.launchAgentPath));
  await assert.rejects(access(paths.installationManifestPath));
});

test('bootout failure leaves prior metadata and runtime untouched', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-bootout-transaction-'));
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const priorRuntime = path.join(paths.runtimeDir, 'versions', '0.1.0');
  await mkdir(path.join(priorRuntime, 'service'), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(path.join(priorRuntime, 'old'), 'old');
  await writeFile(paths.launchAgentPath, 'old plist');
  await writeFile(paths.installationManifestPath, 'old manifest');
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run: fakeInstallerRun({loaded: true, bootoutCode: 5, plistPath: paths.launchAgentPath}), uid: 501, validate: async () => ({})}), error => error.activationState === 'bootout_failed');
  assert.equal(await readFile(paths.launchAgentPath, 'utf8'), 'old plist');
  assert.equal(await readFile(paths.installationManifestPath, 'utf8'), 'old manifest');
  assert.equal(await readFile(path.join(priorRuntime, 'old'), 'utf8'), 'old');
});

test('manifest atomic-write failure restores plist and removes new runtime', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-manifest-fail-'));
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  let writes = 0;
  const writeMetadata = async (...args) => {
    writes += 1;
    if (writes === 2) throw new Error('injected_manifest_rename_failure');
    return atomicWriteFile(...args);
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run: fakeInstallerRun({plistPath: paths.launchAgentPath}), uid: 501, validate: async () => ({}), writeMetadata}), error => error.activationState === 'metadata_write_failed');
  await assert.rejects(access(paths.launchAgentPath));
  await assert.rejects(access(paths.installationManifestPath));
  await assert.rejects(access(path.join(paths.runtimeDir, 'versions', '0.1.0')));
});

test('installer rejects symlinked trusted ancestors before running commands', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-symlink-install-'));
  const outside = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-outside-'));
  await mkdir(path.join(home, 'Library'), {recursive: true});
  await symlink(outside, path.join(home, 'Library', 'Application Support'));
  const paths = exactInstallPaths(home);
  let calls = 0;
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), run: async () => { calls += 1; return {code: 0}; }, validate: async () => { calls += 1; }}), /symlink/);
  assert.equal(calls, 0);
});

test('installer detects an ancestor identity swap after staging without writing or launching through the attacker path', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-identity-swap-'));
  const attacker = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-attacker-'));
  const {sourceRoot} = await seedInstallSource(home);
  const paths = exactInstallPaths(home);
  const launchAgents = path.dirname(paths.launchAgentPath);
  const originalLaunchAgents = `${launchAgents}.original`;
  const launchctlCalls = [];
  let swapped = false;
  const run = async (file, args) => {
    if (file === '/bin/launchctl') {
      launchctlCalls.push(args);
      return {code: 113, stderr: 'Bad request.\nCould not find service "media.rhize.tasks" in domain for user gui: 501'};
    }
    if (file === '/usr/bin/codesign' && !swapped) {
      swapped = true;
      await rename(launchAgents, originalLaunchAgents);
      await symlink(attacker, launchAgents);
    }
    return {code: 0, stdout: ''};
  };
  await assert.rejects(install({paths, pathPolicy: createTestPathPolicy(home), sourceRoot, run, uid: 501, validate: async () => ({})}), error => /install_path_identity_changed/.test(error.message) || (error.code === 'local_activation_rollback_failed' && /install_path_identity_changed/.test(error.cause?.message ?? '')));
  assert.deepEqual(await readdir(attacker), []);
  assert.equal(launchctlCalls.some(args => args[0] === 'bootout' || args[0] === 'bootstrap'), false);
  await rm(launchAgents);
  await rename(originalLaunchAgents, launchAgents);
});

test('uninstall refuses symlinked runtime and plist targets without removing their targets', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-symlink-uninstall-'));
  const outside = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-outside-runtime-'));
  const paths = exactInstallPaths(home);
  await mkdir(paths.supportDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(path.join(outside, 'keep'), 'keep');
  await symlink(outside, paths.runtimeDir);
  await writeFile(paths.launchAgentPath, 'plist');
  await assert.rejects(uninstall({choices: {data: 'delete', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(home), run: async () => ({code: 0})}), /symlink/);
  assert.equal(await readFile(path.join(outside, 'keep'), 'utf8'), 'keep');
  await rm(paths.runtimeDir);
  await mkdir(paths.runtimeDir);
  const outsidePlist = path.join(outside, 'plist');
  await writeFile(outsidePlist, 'keep plist');
  await rm(paths.launchAgentPath);
  await symlink(outsidePlist, paths.launchAgentPath);
  await assert.rejects(uninstall({choices: {data: 'delete', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(home), run: async () => ({code: 0})}), /symlink/);
  assert.equal(await readFile(outsidePlist, 'utf8'), 'keep plist');
});

test('uninstall rechecks ancestor identities after bootout before removing local files', async () => {
  const home = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-uninstall-swap-'));
  const attacker = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-uninstall-attacker-'));
  const paths = exactInstallPaths(home);
  const launchAgents = path.dirname(paths.launchAgentPath);
  const originalLaunchAgents = `${launchAgents}.original`;
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(launchAgents, {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => {
    await rename(launchAgents, originalLaunchAgents);
    await symlink(attacker, launchAgents);
    return {code: 0, stdout: ''};
  };
  await assert.rejects(uninstall({choices: {data: 'delete', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(home), uid: 501, run}), /install_path_identity_changed|symlink_install_path/);
  assert.deepEqual(await readdir(attacker), []);
  await access(paths.runtimeDir);
  await rm(launchAgents);
  await rename(originalLaunchAgents, launchAgents);
});

test('uninstall requires explicit data and item retention choices', () => {
  assert.throws(() => parseUninstallChoice([]), /choose_exactly_one/);
  assert.throws(() => parseUninstallChoice(['--retain-data']), /choose_exactly_one/);
  assert.throws(() => parseUninstallChoice(['--retain-data', '--delete-data', '--retain-items']), /choose_exactly_one/);
  assert.deepEqual(parseUninstallChoice(['--retain-data', '--retain-items']), {data: 'retain', items: 'retain'});
  assert.deepEqual(parseUninstallChoice(['--delete-data', '--delete-items']), {data: 'delete', items: 'delete'});
});

test('uninstall retains data or deletes it only after the explicit choice', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-uninstall-'));
  const paths = exactInstallPaths(root);
  const supportDir = paths.supportDir;
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(path.join(supportDir, 'history.sqlite'), 'history');
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  const retained = await uninstall({choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501});
  assert.equal(retained.dataRetained, true);
  assert.equal(await readFile(path.join(supportDir, 'history.sqlite'), 'utf8'), 'history');
  await mkdir(paths.runtimeDir, {recursive: true});
  const deleted = await uninstall({choices: {data: 'delete', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501});
  assert.equal(deleted.dataRetained, false);
  await assert.rejects(access(supportDir));
});

test('uninstall aborts before any deletion on unrecognized launchctl failure', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-bootout-'));
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  await assert.rejects(uninstall({choices: {data: 'delete', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), uid: 501, run: async () => ({code: 5, stderr: 'Input/output error'})}), /launchctl_bootout_failed/);
  await access(paths.runtimeDir);
  await access(paths.launchAgentPath);
});

test('uninstall continues only for a clearly recognized not-loaded launchctl result', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-not-loaded-'));
  const paths = exactInstallPaths(root);
  await mkdir(paths.runtimeDir, {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const result = await uninstall({choices: {data: 'retain', items: 'retain'}, paths, pathPolicy: createTestPathPolicy(root), uid: 501, run: async () => ({code: 3, stderr: 'Boot-out failed: 3: No such process'})});
  assert.equal(result.ok, true);
  await assert.rejects(access(paths.runtimeDir));
});

test('delete-items requires verified bounded installed CLI results before local deletion', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-items-'));
  const paths = exactInstallPaths(root);
  const supportDir = paths.supportDir;
  const runtimePath = path.join(supportDir, 'runtime', 'versions', '0.1.0');
  const cliPath = path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs');
  await mkdir(path.dirname(cliPath), {recursive: true});
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true});
  await writeFile(cliPath, '');
  await writeFile(paths.launchAgentPath, 'plist');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, runtimePath, cliPath})}\n`);
  const calls = [];
  const run = async (file, args, options) => {
    calls.push({file, args, options});
    if (file === '/bin/launchctl') return {code: 0, stderr: ''};
    return {code: 0, stdout: '{"ok":true,"reminders":{"verified":true,"deleted":1},"calendar":{"verified":true,"deleted":2}}\n'};
  };
  const result = await uninstall({choices: {data: 'retain', items: 'delete'}, paths, pathPolicy: createTestPathPolicy(root), run, uid: 501, nodePath: '/opt/node'});
  assert.equal(result.itemsRetained, false);
  const cleanup = calls.find(call => call.file === '/opt/node');
  assert.deepEqual(cleanup.args.slice(1), ['uninstall-items', '--json']);
  assert.deepEqual(JSON.parse(cleanup.options.input).scope, {reminders: 'plugin-owned', calendar: 'plugin-owned'});

  await mkdir(paths.runtimeDir, {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, runtimePath, cliPath})}\n`);
  await assert.rejects(uninstall({
    choices: {data: 'delete', items: 'delete'}, paths, pathPolicy: createTestPathPolicy(root), uid: 501, nodePath: '/opt/node',
    run: async file => file === '/bin/launchctl' ? {code: 0, stderr: ''} : {code: 0, stdout: '{"ok":true,"reminders":{"verified":true,"deleted":1}}\n'},
  }), /item_cleanup_unverified/);
  await access(paths.runtimeDir);
  await access(paths.launchAgentPath);
});
