import {access, chmod, copyFile, cp, lstat, mkdir, readFile, readdir, rename, rm, writeFile} from 'node:fs/promises';
import {constants as fsConstants} from 'node:fs';
import {createServer} from 'node:net';
import {homedir} from 'node:os';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {bootoutIfLoaded} from './launchctl.mjs';
import {runProcess} from '../service/src/connectors/process-runner.mjs';

const installerDir = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.dirname(installerDir);
const label = 'media.rhize.tasks';
const runtimeEntries = ['package.json', 'service', 'schemas', 'setup', 'installer', 'dashboard', 'skills', 'commands'];

export function defaultInstallPaths(home = homedir()) {
  const supportDir = path.join(home, 'Library', 'Application Support', 'Rhize Tasks');
  return {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    launchAgentPath: path.join(home, 'Library', 'LaunchAgents', `${label}.plist`),
    logDir: path.join(supportDir, 'logs'),
    installationManifestPath: path.join(supportDir, 'installation.json'),
  };
}

function assertInstallPaths(paths) {
  for (const key of ['supportDir', 'runtimeDir', 'launchAgentPath', 'logDir', 'installationManifestPath']) {
    if (typeof paths?.[key] !== 'string' || paths[key].length === 0) throw new Error(`invalid_install_path_${key}`);
  }
  const support = path.resolve(paths.supportDir);
  const runtime = path.resolve(paths.runtimeDir);
  const logs = path.resolve(paths.logDir);
  if (path.basename(support) !== 'Rhize Tasks') throw new Error('unsafe_support_directory');
  if (runtime !== path.join(support, 'runtime') || logs !== path.join(support, 'logs')) throw new Error('unsafe_install_subdirectory');
  if (path.resolve(paths.installationManifestPath) !== path.join(support, 'installation.json')) throw new Error('unsafe_installation_manifest');
  if (path.basename(paths.launchAgentPath) !== `${label}.plist`) throw new Error('unsafe_launch_agent_path');
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
  macOSVersion,
  nodeVersion = process.versions.node,
  supportDir = defaultInstallPaths().supportDir,
  port = 43179,
  accessImpl = access,
  mkdirImpl = mkdir,
  chmodImpl = chmod,
  checkPort = checkLoopbackPort,
  run = runProcess,
} = {}) {
  if (platform !== 'darwin') throw new Error('macos_required');
  let detectedVersion = macOSVersion;
  if (detectedVersion === undefined) {
    let result;
    try {
      result = await run('/usr/bin/sw_vers', ['-productVersion'], {timeoutMs: 5_000, maxOutputBytes: 1_024});
    } catch {
      throw new Error('macos_version_unavailable');
    }
    if (!result || result.code !== 0 || result.timedOut || typeof result.stdout !== 'string') throw new Error('macos_version_unavailable');
    detectedVersion = result.stdout.trim();
  }
  if (!/^\d+(?:\.\d+){0,2}$/.test(detectedVersion ?? '') || Number.parseInt(detectedVersion, 10) < 14) throw new Error('macos_14_required');
  if (Number.parseInt(nodeVersion.split('.')[0], 10) < 22) throw new Error('node_22_required');
  await Promise.all([
    executableCheck('/usr/bin/security', accessImpl),
    executableCheck('/bin/launchctl', accessImpl),
    executableCheck('/usr/bin/swift', accessImpl),
    executableCheck('/usr/bin/codesign', accessImpl),
    executableCheck('/usr/bin/sw_vers', accessImpl),
  ]).catch(() => { throw new Error('required_macos_tool_missing'); });
  await mkdirImpl(supportDir, {recursive: true, mode: 0o700});
  await chmodImpl(supportDir, 0o700);
  await accessImpl(supportDir, fsConstants.W_OK);
  await checkPort(port);
  return {platform, macOSVersion: detectedVersion, nodeMajor: Number.parseInt(nodeVersion.split('.')[0], 10), port};
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

function runtimeCopyFilter(source) {
  const name = path.basename(source);
  return name !== 'node_modules' && name !== '.build' && !name.startsWith('.env') && !/\.(?:sqlite|sqlite3|db)(?:-|$)/i.test(name);
}

async function copyIfPresent(source, destination) {
  try {
    await access(source, fsConstants.R_OK);
  } catch (error) {
    if (error.code === 'ENOENT') return false;
    throw error;
  }
  await cp(source, destination, {recursive: true, force: true, filter: runtimeCopyFilter});
  return true;
}

async function hardenTree(root, executableNames = new Set()) {
  const metadata = await lstat(root);
  if (metadata.isSymbolicLink()) throw new Error('runtime_symlink_not_allowed');
  if (metadata.isDirectory()) {
    await chmod(root, 0o700);
    for (const entry of await readdir(root)) await hardenTree(path.join(root, entry), executableNames);
    return;
  }
  await chmod(root, executableNames.has(path.basename(root)) ? 0o700 : 0o600);
}

async function atomicReplaceDirectory(stagePath, targetPath) {
  const backupPath = `${targetPath}.previous-${process.pid}`;
  let hadTarget = false;
  try {
    await access(targetPath);
    hadTarget = true;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  await rm(backupPath, {recursive: true, force: true});
  if (hadTarget) await rename(targetPath, backupPath);
  try {
    await rename(stagePath, targetPath);
  } catch (error) {
    if (hadTarget) await rename(backupPath, targetPath);
    throw error;
  }
  await rm(backupPath, {recursive: true, force: true});
}

async function writeAtomicJson(target, value) {
  const temporary = `${target}.installing-${process.pid}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, {encoding: 'utf8', mode: 0o600});
  await chmod(temporary, 0o600);
  await rename(temporary, target);
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
  assertInstallPaths(paths);
  await validate({supportDir: paths.supportDir, port, run});
  const packageDocument = JSON.parse(await readFile(path.join(sourceRoot, 'package.json'), 'utf8'));
  if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(packageDocument.version ?? '')) throw new Error('invalid_runtime_version');
  const version = packageDocument.version;
  const packagePath = path.join(sourceRoot, 'native', 'reminders-helper');
  await runChecked('/usr/bin/swift', ['build', '-c', 'release', '--package-path', packagePath], {timeoutMs: 120_000}, run);

  await mkdir(paths.runtimeDir, {recursive: true, mode: 0o700});
  await chmod(paths.runtimeDir, 0o700);
  const versionsDir = path.join(paths.runtimeDir, 'versions');
  await mkdir(versionsDir, {recursive: true, mode: 0o700});
  await chmod(versionsDir, 0o700);
  const stagePath = path.join(paths.runtimeDir, `.installing-${process.pid}`);
  const runtimePath = path.join(versionsDir, version);
  await rm(stagePath, {recursive: true, force: true});

  try {
    await mkdir(stagePath, {recursive: true, mode: 0o700});
    for (const entry of runtimeEntries) await copyIfPresent(path.join(sourceRoot, entry), path.join(stagePath, entry));
    await access(path.join(stagePath, 'service'), fsConstants.R_OK);
    await access(path.join(stagePath, 'schemas'), fsConstants.R_OK);
    const cliPathInStage = path.join(stagePath, 'service', 'bin', 'rhize-tasks.mjs');
    await access(cliPathInStage, fsConstants.R_OK);

    const appPathInStage = path.join(stagePath, 'native', 'RhizeRemindersHelper.app');
    await mkdir(path.join(appPathInStage, 'Contents', 'MacOS'), {recursive: true, mode: 0o700});
    await copyFile(path.join(packagePath, '.build', 'release', 'RhizeRemindersHelper'), path.join(appPathInStage, 'Contents', 'MacOS', 'RhizeRemindersHelper'));
    await copyFile(path.join(packagePath, 'Resources', 'Info.plist'), path.join(appPathInStage, 'Contents', 'Info.plist'));
    await chmod(path.join(appPathInStage, 'Contents', 'MacOS', 'RhizeRemindersHelper'), 0o700);
    await hardenTree(stagePath, new Set(['RhizeRemindersHelper']));
    await runChecked('/usr/bin/codesign', ['--force', '--sign', '-', appPathInStage], {timeoutMs: 30_000}, run);
    await atomicReplaceDirectory(stagePath, runtimePath);
  } catch (error) {
    await rm(stagePath, {recursive: true, force: true});
    throw error;
  }

  const cliPath = path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs');
  const appPath = path.join(runtimePath, 'native', 'RhizeRemindersHelper.app');
  await mkdir(paths.logDir, {recursive: true, mode: 0o700});
  await chmod(paths.logDir, 0o700);
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true, mode: 0o700});
  const plist = await renderLaunchAgent({
    nodePath,
    cliPath,
    stdoutPath: path.join(paths.logDir, 'routine.log'),
    stderrPath: path.join(paths.logDir, 'routine-error.log'),
  });
  await writeFile(paths.launchAgentPath, plist, {encoding: 'utf8', mode: 0o600});
  await chmod(paths.launchAgentPath, 0o600);
  await writeAtomicJson(paths.installationManifestPath, {schemaVersion: 1, version, runtimePath, cliPath, appPath, label});

  const domain = `gui/${uid}`;
  await bootoutIfLoaded({run, domain, plistPath: paths.launchAgentPath});
  await runChecked('/bin/launchctl', ['bootstrap', domain, paths.launchAgentPath], {timeoutMs: 15_000}, run);
  return {appPath, launchAgentPath: paths.launchAgentPath, runtimePath, version, label};
}

function parseProbeResponse(result, expectedID) {
  if (!result || result.code !== 0 || result.timedOut || result.outputExceeded || typeof result.stdout !== 'string') throw new Error('reminders_probe_failed');
  const lines = result.stdout.split(/\r?\n/).filter(Boolean);
  if (lines.length !== 1) throw new Error('reminders_probe_failed');
  let response;
  try {
    response = JSON.parse(lines[0]);
  } catch {
    throw new Error('reminders_probe_failed');
  }
  if (response?.ok !== true || response.id !== expectedID || typeof response.revision !== 'string' || response.revision.length === 0) throw new Error('reminders_probe_failed');
  return response;
}

export async function runRemindersAccessProbe({approved, helperPath, listId, operationId, runner = runProcess}) {
  if (approved !== true) throw new Error('approval_required');
  if (![helperPath, listId, operationId].every(value => typeof value === 'string' && value.length > 0)) throw new TypeError('invalid_probe_configuration');
  const externalId = `access-probe:${operationId}`;
  const invoke = async request => parseProbeResponse(await runner(helperPath, [], {
    input: `${JSON.stringify(request)}\n`, timeoutMs: 15_000, maxOutputBytes: 1_000_000,
    env: Object.fromEntries([
      ['HOME', process.env.HOME], ['LANG', process.env.LANG], ['TMPDIR', process.env.TMPDIR],
      ['RHIZE_TASKS_REMINDERS_LIST_ID', listId],
    ].filter(([, value]) => typeof value === 'string')),
  }), request.externalId ?? request.id);
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
