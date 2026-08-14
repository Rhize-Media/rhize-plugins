import assert from 'node:assert/strict';
import {access, mkdir, mkdtemp, readFile, stat, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {runProcess} from '../../service/src/connectors/process-runner.mjs';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';
import {checkLoopbackPort, install, renderLaunchAgent, runRemindersAccessProbe, validatePrerequisites} from '../../installer/install.mjs';
import {parseUninstallChoice, uninstall} from '../../installer/uninstall.mjs';

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
  const sourceRoot = path.join(root, 'plugin');
  const packageRoot = path.join(sourceRoot, 'native', 'reminders-helper');
  await mkdir(path.join(packageRoot, '.build', 'release'), {recursive: true});
  await mkdir(path.join(packageRoot, 'Resources'), {recursive: true});
  await mkdir(path.join(sourceRoot, 'service', 'bin'), {recursive: true});
  await mkdir(path.join(sourceRoot, 'schemas'), {recursive: true});
  await writeFile(path.join(packageRoot, '.build', 'release', 'RhizeRemindersHelper'), '#!/bin/sh\n');
  await writeFile(path.join(packageRoot, 'Resources', 'Info.plist'), '<plist version="1.0"><dict/></plist>');
  await writeFile(path.join(sourceRoot, 'package.json'), '{"name":"rhize-tasks","version":"0.1.0"}\n');
  await writeFile(path.join(sourceRoot, 'service', 'bin', 'rhize-tasks.mjs'), 'process.exit(0);\n');
  await writeFile(path.join(sourceRoot, 'schemas', 'task.schema.json'), '{}\n');
  await writeFile(path.join(sourceRoot, 'service', '.env'), 'SECRET=do-not-copy\n');
  await writeFile(path.join(sourceRoot, 'service', 'history.sqlite'), 'do-not-copy');
  const supportDir = path.join(root, 'Library', 'Application Support', 'Rhize Tasks');
  const paths = {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    launchAgentPath: path.join(root, 'Library', 'LaunchAgents', 'media.rhize.tasks.plist'),
    logDir: path.join(supportDir, 'logs'),
    installationManifestPath: path.join(supportDir, 'installation.json'),
  };
  const calls = [];
  const run = async (file, args) => { calls.push([file, args]); return {code: 0, stdout: ''}; };
  const result = await install({paths, sourceRoot, run, uid: 501, nodePath: '/opt/node', validate: async () => ({})});
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
  let calls = 0;
  await assert.rejects(install({
    paths: {supportDir: '/tmp/Rhize Tasks'},
    run: async () => { calls += 1; return {code: 0}; },
    validate: async () => { calls += 1; },
  }), /invalid_install_path_runtimeDir/);
  assert.equal(calls, 0);
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
  const supportDir = path.join(root, 'Rhize Tasks');
  const paths = {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    launchAgentPath: path.join(root, 'media.rhize.tasks.plist'),
    installationManifestPath: path.join(supportDir, 'installation.json'),
  };
  await mkdir(paths.runtimeDir, {recursive: true});
  await writeFile(path.join(supportDir, 'history.sqlite'), 'history');
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  const retained = await uninstall({choices: {data: 'retain', items: 'retain'}, paths, run, uid: 501});
  assert.equal(retained.dataRetained, true);
  assert.equal(await readFile(path.join(supportDir, 'history.sqlite'), 'utf8'), 'history');
  await mkdir(paths.runtimeDir, {recursive: true});
  const deleted = await uninstall({choices: {data: 'delete', items: 'retain'}, paths, run, uid: 501});
  assert.equal(deleted.dataRetained, false);
  await assert.rejects(access(supportDir));
});

test('uninstall aborts before any deletion on unrecognized launchctl failure', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-bootout-'));
  const supportDir = path.join(root, 'Rhize Tasks');
  const paths = {supportDir, runtimeDir: path.join(supportDir, 'runtime'), launchAgentPath: path.join(root, 'media.rhize.tasks.plist'), installationManifestPath: path.join(supportDir, 'installation.json')};
  await mkdir(paths.runtimeDir, {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  await assert.rejects(uninstall({choices: {data: 'delete', items: 'retain'}, paths, uid: 501, run: async () => ({code: 5, stderr: 'Input/output error'})}), /launchctl_bootout_failed/);
  await access(paths.runtimeDir);
  await access(paths.launchAgentPath);
});

test('uninstall continues only for a clearly recognized not-loaded launchctl result', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-not-loaded-'));
  const supportDir = path.join(root, 'Rhize Tasks');
  const paths = {supportDir, runtimeDir: path.join(supportDir, 'runtime'), launchAgentPath: path.join(root, 'media.rhize.tasks.plist'), installationManifestPath: path.join(supportDir, 'installation.json')};
  await mkdir(paths.runtimeDir, {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  const result = await uninstall({choices: {data: 'retain', items: 'retain'}, paths, uid: 501, run: async () => ({code: 3, stderr: 'Boot-out failed: 3: No such process'})});
  assert.equal(result.ok, true);
  await assert.rejects(access(paths.runtimeDir));
});

test('delete-items requires verified bounded installed CLI results before local deletion', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-items-'));
  const supportDir = path.join(root, 'Rhize Tasks');
  const runtimePath = path.join(supportDir, 'runtime', 'versions', '0.1.0');
  const cliPath = path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs');
  const paths = {supportDir, runtimeDir: path.join(supportDir, 'runtime'), launchAgentPath: path.join(root, 'media.rhize.tasks.plist'), installationManifestPath: path.join(supportDir, 'installation.json')};
  await mkdir(path.dirname(cliPath), {recursive: true});
  await writeFile(cliPath, '');
  await writeFile(paths.launchAgentPath, 'plist');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, runtimePath, cliPath})}\n`);
  const calls = [];
  const run = async (file, args, options) => {
    calls.push({file, args, options});
    if (file === '/bin/launchctl') return {code: 0, stderr: ''};
    return {code: 0, stdout: '{"ok":true,"reminders":{"verified":true,"deleted":1},"calendar":{"verified":true,"deleted":2}}\n'};
  };
  const result = await uninstall({choices: {data: 'retain', items: 'delete'}, paths, run, uid: 501, nodePath: '/opt/node'});
  assert.equal(result.itemsRetained, false);
  const cleanup = calls.find(call => call.file === '/opt/node');
  assert.deepEqual(cleanup.args.slice(1), ['uninstall-items', '--json']);
  assert.deepEqual(JSON.parse(cleanup.options.input).scope, {reminders: 'plugin-owned', calendar: 'plugin-owned'});

  await mkdir(paths.runtimeDir, {recursive: true});
  await writeFile(paths.launchAgentPath, 'plist');
  await writeFile(paths.installationManifestPath, `${JSON.stringify({schemaVersion: 1, runtimePath, cliPath})}\n`);
  await assert.rejects(uninstall({
    choices: {data: 'delete', items: 'delete'}, paths, uid: 501, nodePath: '/opt/node',
    run: async file => file === '/bin/launchctl' ? {code: 0, stderr: ''} : {code: 0, stdout: '{"ok":true,"reminders":{"verified":true,"deleted":1}}\n'},
  }), /item_cleanup_unverified/);
  await access(paths.runtimeDir);
  await access(paths.launchAgentPath);
});
