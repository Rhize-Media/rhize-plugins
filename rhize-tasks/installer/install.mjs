import {access, chmod, copyFile, cp, lstat, mkdir, open, readFile, readdir, rename, rm} from 'node:fs/promises';
import {constants as fsConstants} from 'node:fs';
import {createServer} from 'node:net';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {bootoutIfLoaded, getLaunchAgentState} from './launchctl.mjs';
import {exactInstallPaths, productionPathPolicy, verifyInstallPaths, verifyRuntimePath} from './safe-paths.mjs';
import {runProcess} from '../service/src/connectors/process-runner.mjs';

const installerDir = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.dirname(installerDir);
const label = 'media.rhize.tasks';
const runtimeEntries = ['package.json', 'service', 'schemas', 'setup', 'installer', 'dashboard', 'skills', 'commands'];

export const defaultInstallPaths = exactInstallPaths;

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

async function placeRuntimeCandidate(stagePath, targetPath) {
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
  return {backupPath, hadTarget, targetPath};
}

async function rollbackRuntimeCandidate(transaction) {
  await rm(transaction.targetPath, {recursive: true, force: true});
  if (transaction.hadTarget) await rename(transaction.backupPath, transaction.targetPath);
}

async function finalizeRuntimeCandidate(transaction) {
  await rm(transaction.backupPath, {recursive: true, force: true});
}

export async function atomicWriteFile(target, value, mode = 0o600) {
  const temporary = `${target}.installing-${process.pid}`;
  let handle;
  try {
    handle = await open(temporary, 'wx', mode);
    await handle.writeFile(value);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await chmod(temporary, mode);
    await rename(temporary, target);
    const directory = await open(path.dirname(target), 'r');
    try {
      await directory.sync();
    } finally {
      await directory.close();
    }
  } catch (error) {
    await handle?.close().catch(() => {});
    await rm(temporary, {force: true});
    throw error;
  }
}

async function snapshotFile(target) {
  try {
    const metadata = await lstat(target);
    if (metadata.isSymbolicLink()) throw new Error(`symlink_install_path:${target}`);
    if (!metadata.isFile()) throw new Error(`non_file_install_path:${target}`);
    return {exists: true, bytes: await readFile(target), mode: metadata.mode & 0o777};
  } catch (error) {
    if (error.code === 'ENOENT') return {exists: false};
    throw error;
  }
}

async function restoreFile(target, snapshot, writeMetadata) {
  if (!snapshot.exists) {
    await rm(target, {force: true});
    return;
  }
  await writeMetadata(target, snapshot.bytes, snapshot.mode);
}

function activationError(activationState, cause, rollbackFailures = []) {
  const error = new Error(rollbackFailures.length === 0 ? `local_activation_failed:${activationState}` : `local_activation_rollback_failed:${activationState}:${rollbackFailures.join(',')}`);
  error.code = rollbackFailures.length === 0 ? 'local_activation_failed' : 'local_activation_rollback_failed';
  error.activationState = activationState;
  error.rollbackState = rollbackFailures.length === 0 ? 'restored' : rollbackFailures.join(',');
  error.cause = cause;
  return error;
}

export async function install({
  paths = defaultInstallPaths(),
  pathPolicy = productionPathPolicy(),
  port = 43179,
  run = runProcess,
  uid = process.getuid?.(),
  nodePath = process.execPath,
  sourceRoot = pluginRoot,
  validate = validatePrerequisites,
  writeMetadata = atomicWriteFile,
} = {}) {
  await verifyInstallPaths(paths, pathPolicy);
  await validate({supportDir: paths.supportDir, port, run});
  await verifyInstallPaths(paths, pathPolicy);
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
  await mkdir(paths.logDir, {recursive: true, mode: 0o700});
  await chmod(paths.logDir, 0o700);
  await mkdir(path.dirname(paths.launchAgentPath), {recursive: true, mode: 0o700});
  await verifyInstallPaths(paths, pathPolicy);
  const priorPlist = await snapshotFile(paths.launchAgentPath);
  const priorManifest = await snapshotFile(paths.installationManifestPath);
  const domain = `gui/${uid}`;
  const priorAgent = await getLaunchAgentState({run, domain, label});
  const stagePath = path.join(paths.runtimeDir, `.installing-${process.pid}`);
  const runtimePath = path.join(versionsDir, version);
  await verifyRuntimePath(paths, runtimePath, pathPolicy);
  await rm(stagePath, {recursive: true, force: true});

  let runtimeTransaction;
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
    runtimeTransaction = await placeRuntimeCandidate(stagePath, runtimePath);
  } catch (error) {
    await rm(stagePath, {recursive: true, force: true});
    throw error;
  }

  const cliPath = path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs');
  const appPath = path.join(runtimePath, 'native', 'RhizeRemindersHelper.app');
  const plist = await renderLaunchAgent({
    nodePath,
    cliPath,
    stdoutPath: path.join(paths.logDir, 'routine.log'),
    stderrPath: path.join(paths.logDir, 'routine-error.log'),
  });
  const manifest = `${JSON.stringify({schemaVersion: 1, version, runtimePath, cliPath, appPath, label}, null, 2)}\n`;
  let activationState = 'bootout_failed';
  try {
    if (priorAgent.loaded) await bootoutIfLoaded({run, domain, plistPath: paths.launchAgentPath});
    activationState = 'metadata_write_failed';
    await writeMetadata(paths.launchAgentPath, plist, 0o600);
    await writeMetadata(paths.installationManifestPath, manifest, 0o600);
    await verifyInstallPaths(paths, pathPolicy);
    activationState = 'bootstrap_failed';
    await runChecked('/bin/launchctl', ['bootstrap', domain, paths.launchAgentPath], {timeoutMs: 15_000}, run);
    activationState = 'activation_verification_failed';
    if (!(await getLaunchAgentState({run, domain, label})).loaded) throw new Error('new_agent_not_loaded');
    await finalizeRuntimeCandidate(runtimeTransaction);
    return {appPath, launchAgentPath: paths.launchAgentPath, runtimePath, version, label};
  } catch (activationFailure) {
    const rollbackFailures = [];
    try { await restoreFile(paths.launchAgentPath, priorPlist, writeMetadata); } catch { rollbackFailures.push('plist_restore_failed'); }
    try { await restoreFile(paths.installationManifestPath, priorManifest, writeMetadata); } catch { rollbackFailures.push('manifest_restore_failed'); }
    try { await rollbackRuntimeCandidate(runtimeTransaction); } catch { rollbackFailures.push('runtime_restore_failed'); }
    try {
      const current = await getLaunchAgentState({run, domain, label});
      if (priorAgent.loaded && !current.loaded) await runChecked('/bin/launchctl', ['bootstrap', domain, paths.launchAgentPath], {timeoutMs: 15_000}, run);
      if (!priorAgent.loaded && current.loaded) await bootoutIfLoaded({run, domain, plistPath: paths.launchAgentPath});
    } catch {
      rollbackFailures.push('agent_restore_failed');
    }
    throw activationError(activationState, activationFailure, rollbackFailures);
  }
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
