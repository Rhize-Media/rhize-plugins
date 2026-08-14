import {access, chmod, copyFile, mkdir, readFile, rename, rm, writeFile} from 'node:fs/promises';
import {constants as fsConstants} from 'node:fs';
import {createServer} from 'node:net';
import {homedir} from 'node:os';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {runProcess} from '../service/src/connectors/process-runner.mjs';

const installerDir = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.dirname(installerDir);
const label = 'media.rhize.tasks';

export function defaultInstallPaths(home = homedir()) {
  const supportDir = path.join(home, 'Library', 'Application Support', 'Rhize Tasks');
  return {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    appPath: path.join(supportDir, 'runtime', 'RhizeRemindersHelper.app'),
    launchAgentPath: path.join(home, 'Library', 'LaunchAgents', `${label}.plist`),
    logDir: path.join(supportDir, 'logs'),
  };
}

function executableCheck(file, accessImpl = access) {
  return accessImpl(file, fsConstants.X_OK);
}

export async function checkLoopbackPort(port, {createServerImpl = createServer} = {}) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('invalid_loopback_port');
  await new Promise((resolve, reject) => {
    const server = createServerImpl();
    server.unref?.();
    server.once('error', error => reject(new Error(error.code === 'EADDRINUSE' ? 'loopback_port_in_use' : 'loopback_port_check_failed')));
    server.listen({host: '127.0.0.1', port, exclusive: true}, () => server.close(resolve));
  });
}

export async function validatePrerequisites({
  platform = process.platform,
  nodeVersion = process.versions.node,
  supportDir = defaultInstallPaths().supportDir,
  port = 43179,
  accessImpl = access,
  mkdirImpl = mkdir,
  checkPort = checkLoopbackPort,
} = {}) {
  if (platform !== 'darwin') throw new Error('macos_required');
  if (Number.parseInt(nodeVersion.split('.')[0], 10) < 22) throw new Error('node_22_required');
  await Promise.all([
    executableCheck('/usr/bin/security', accessImpl),
    executableCheck('/bin/launchctl', accessImpl),
    executableCheck('/usr/bin/swift', accessImpl),
    executableCheck('/usr/bin/codesign', accessImpl),
  ]).catch(() => { throw new Error('required_macos_tool_missing'); });
  await mkdirImpl(supportDir, {recursive: true, mode: 0o700});
  await accessImpl(supportDir, fsConstants.W_OK);
  await checkPort(port);
  return {platform, nodeMajor: Number.parseInt(nodeVersion.split('.')[0], 10), port};
}

function xmlEscape(value) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');
}

async function runChecked(file, args, options = {}, run = runProcess) {
  const result = await run(file, args, options);
  if (!result || result.code !== 0 || result.timedOut) throw new Error('installer_command_failed');
  return result;
}

export async function renderLaunchAgent({nodePath, cliPath, stdoutPath, stderrPath, templatePath = path.join(installerDir, 'media.rhize.tasks.plist.template')}) {
  const template = await readFile(templatePath, 'utf8');
  const values = {NODE_PATH: nodePath, CLI_PATH: cliPath, STDOUT_PATH: stdoutPath, STDERR_PATH: stderrPath};
  const rendered = Object.entries(values).reduce((text, [key, value]) => text.replaceAll(`{{${key}}}`, xmlEscape(path.resolve(value))), template);
  if (/{{[A-Z_]+}}/.test(rendered)) throw new Error('unresolved_launch_agent_placeholder');
  if (/token|secret|password|bearer/i.test(rendered)) throw new Error('launch_agent_may_not_contain_secrets');
  return rendered;
}

export async function install({
  paths = defaultInstallPaths(),
  port = 43179,
  run = runProcess,
  uid = process.getuid?.(),
  nodePath = process.execPath,
  sourceRoot = pluginRoot,
  validate = validatePrerequisites,
} = {}) {
  await validate({supportDir: paths.supportDir, port});
  const packagePath = path.join(sourceRoot, 'native', 'reminders-helper');
  await runChecked('/usr/bin/swift', ['build', '-c', 'release', '--package-path', packagePath], {timeoutMs: 120_000}, run);

  const temporaryApp = `${paths.appPath}.installing-${process.pid}`;
  await rm(temporaryApp, {recursive: true, force: true});
  await mkdir(path.join(temporaryApp, 'Contents', 'MacOS'), {recursive: true, mode: 0o700});
  await copyFile(path.join(packagePath, '.build', 'release', 'RhizeRemindersHelper'), path.join(temporaryApp, 'Contents', 'MacOS', 'RhizeRemindersHelper'));
  await chmod(path.join(temporaryApp, 'Contents', 'MacOS', 'RhizeRemindersHelper'), 0o700);
  await copyFile(path.join(packagePath, 'Resources', 'Info.plist'), path.join(temporaryApp, 'Contents', 'Info.plist'));
  await runChecked('/usr/bin/codesign', ['--force', '--sign', '-', temporaryApp], {timeoutMs: 30_000}, run);
  await rm(paths.appPath, {recursive: true, force: true});
  await rename(temporaryApp, paths.appPath);

  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true, mode: 0o700});
  await mkdir(paths.logDir, {recursive: true, mode: 0o700});
  const plist = await renderLaunchAgent({
    nodePath,
    cliPath: path.join(sourceRoot, 'service', 'bin', 'rhize-tasks.mjs'),
    stdoutPath: path.join(paths.logDir, 'routine.log'),
    stderrPath: path.join(paths.logDir, 'routine-error.log'),
  });
  await writeFile(paths.launchAgentPath, plist, {encoding: 'utf8', mode: 0o600});
  const domain = `gui/${uid}`;
  await run('/bin/launchctl', ['bootout', domain, paths.launchAgentPath], {timeoutMs: 15_000});
  await runChecked('/bin/launchctl', ['bootstrap', domain, paths.launchAgentPath], {timeoutMs: 15_000}, run);
  return {appPath: paths.appPath, launchAgentPath: paths.launchAgentPath, label};
}

export async function runRemindersAccessProbe({approved, helperPath, listId, operationId, runner = runProcess}) {
  if (approved !== true) throw new Error('approval_required');
  if (![helperPath, listId, operationId].every(value => typeof value === 'string' && value.length > 0)) throw new TypeError('invalid_probe_configuration');
  const externalId = `access-probe:${operationId}`;
  const invoke = async request => {
    const result = await runner(helperPath, [], {
      input: `${JSON.stringify(request)}\n`, timeoutMs: 15_000, maxOutputBytes: 1_000_000,
      env: Object.fromEntries([
        ['HOME', process.env.HOME], ['LANG', process.env.LANG], ['TMPDIR', process.env.TMPDIR],
        ['RHIZE_TASKS_REMINDERS_LIST_ID', listId],
      ].filter(([, value]) => typeof value === 'string')),
    });
    if (!result || result.code !== 0 || result.timedOut) throw new Error('reminders_probe_failed');
    const response = JSON.parse(result.stdout.trim());
    if (response.ok === false) throw new Error(response.error || 'reminders_probe_failed');
    return response;
  };
  await invoke({command: 'upsert', listId, title: 'Rhize Tasks access check', dueAt: null, notes: 'Created and removed by the approved setup access check.', externalId, operationKey: operationId});
  try {
    await invoke({command: 'delete', listId, id: externalId, operationKey: `${operationId}:cleanup`});
  } catch {
    throw new Error('reminders_probe_cleanup_failed');
  }
  return {ok: true, externalId};
}

async function main() {
  try {
    const result = await install();
    process.stdout.write(`${JSON.stringify({ok: true, ...result})}\n`);
  } catch (error) {
    process.stderr.write(`${JSON.stringify({ok: false, error: error.message})}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
