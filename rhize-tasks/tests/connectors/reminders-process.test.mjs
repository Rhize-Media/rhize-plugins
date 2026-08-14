import assert from 'node:assert/strict';
import {access, mkdir, mkdtemp, readFile, writeFile} from 'node:fs/promises';
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
    runner: async () => (++calls === 1 ? {code: 0, stdout: '{"ok":true}\n'} : {code: 1, stdout: ''}),
  }), /cleanup_failed/);
});

test('installer preflight enforces macOS, Node floor, tools, writable support, and loopback check', async () => {
  const calls = [];
  const options = {
    platform: 'darwin', nodeVersion: '22.1.0', supportDir: '/tmp/Rhize Tasks', port: 43179,
    accessImpl: async value => calls.push(['access', value]),
    mkdirImpl: async value => calls.push(['mkdir', value]),
    checkPort: async value => calls.push(['port', value]),
  };
  const result = await validatePrerequisites(options);
  assert.equal(result.nodeMajor, 22);
  assert.ok(calls.some(call => call[0] === 'port'));
  await assert.rejects(validatePrerequisites({...options, platform: 'linux'}), /macos_required/);
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
  await writeFile(path.join(packageRoot, '.build', 'release', 'RhizeRemindersHelper'), '#!/bin/sh\n');
  await writeFile(path.join(packageRoot, 'Resources', 'Info.plist'), '<plist version="1.0"><dict/></plist>');
  const supportDir = path.join(root, 'Library', 'Application Support', 'Rhize Tasks');
  const paths = {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    appPath: path.join(supportDir, 'runtime', 'RhizeRemindersHelper.app'),
    launchAgentPath: path.join(root, 'Library', 'LaunchAgents', 'media.rhize.tasks.plist'),
    logDir: path.join(supportDir, 'logs'),
  };
  const calls = [];
  const run = async (file, args) => { calls.push([file, args]); return {code: 0, stdout: ''}; };
  const result = await install({paths, sourceRoot, run, uid: 501, nodePath: '/opt/node', validate: async () => ({})});
  await access(path.join(result.appPath, 'Contents', 'MacOS', 'RhizeRemindersHelper'));
  assert.ok(calls.some(([file, args]) => file === '/usr/bin/codesign' && args.includes('--sign')));
  assert.equal(calls.filter(([file, args]) => file === '/bin/launchctl' && args[0] === 'bootstrap').length, 1);
});

test('uninstall requires exactly one explicit retention choice', () => {
  assert.throws(() => parseUninstallChoice([]), /choose_exactly_one/);
  assert.throws(() => parseUninstallChoice(['--retain-data', '--delete-data']), /choose_exactly_one/);
  assert.equal(parseUninstallChoice(['--retain-data']), 'retain');
  assert.equal(parseUninstallChoice(['--delete-data']), 'delete');
});

test('uninstall retains data or deletes it only after the explicit choice', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-uninstall-'));
  const supportDir = path.join(root, 'Rhize Tasks');
  const paths = {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    launchAgentPath: path.join(root, 'media.rhize.tasks.plist'),
  };
  await mkdir(paths.runtimeDir, {recursive: true});
  await writeFile(path.join(supportDir, 'history.sqlite'), 'history');
  await writeFile(paths.launchAgentPath, 'plist');
  const run = async () => ({code: 0, stdout: ''});
  const retained = await uninstall({choice: 'retain', paths, run, uid: 501});
  assert.equal(retained.dataRetained, true);
  assert.equal(await readFile(path.join(supportDir, 'history.sqlite'), 'utf8'), 'history');
  await mkdir(paths.runtimeDir, {recursive: true});
  const deleted = await uninstall({choice: 'delete', paths, run, uid: 501});
  assert.equal(deleted.dataRetained, false);
  await assert.rejects(access(supportDir));
});
