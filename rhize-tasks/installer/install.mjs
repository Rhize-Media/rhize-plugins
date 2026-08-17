import {access, chmod, copyFile, cp, lstat, mkdir, open, readFile, readdir, rename, rm, writeFile} from 'node:fs/promises';
import {constants as fsConstants} from 'node:fs';
import {createServer} from 'node:net';
import {randomBytes} from 'node:crypto';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {bootoutIfLoaded, bootoutServiceIfLoaded, getLaunchAgentState} from './launchctl.mjs';
import {assertInstallPathIdentities, captureInstallPathIdentities, exactInstallPaths, productionPathPolicy, verifyInstallPaths, verifyRuntimePath} from './safe-paths.mjs';
import {runProcess} from '../service/src/connectors/process-runner.mjs';
import {createKeychain} from '../service/src/connectors/keychain.mjs';

const installerDir = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.dirname(installerDir);
export const label = 'media.rhize.tasks';
const runtimeEntries = ['package.json', 'service', 'schemas', 'setup', 'installer', 'dashboard', 'skills', 'commands'];

export const defaultInstallPaths = exactInstallPaths;

function executableCheck(file, accessImpl = access) {
  return accessImpl(file, fsConstants.X_OK);
}

// A bare "port in use" reads like an unrelated conflict even when the
// holder is our own already-running `serve` process — increasingly likely
// once `dashboard` starts spawning it on demand (finding #1). Distinguish
// the two by asking the holder what it is before reporting a conflict.
// Exported so uninstall.mjs can reuse it as a fallback when there's no
// pidfile to trust (finding #1-followup).
export async function defaultProbeOwnServer(port) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1_500);
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`, {signal: controller.signal});
    if (!response.ok) return null;
    const body = await response.json();
    return body?.status === 'ok' && typeof body?.version === 'string' ? body : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// `dashboard` (finding #1) writes this file with the pid of the `serve`
// process it spawned, so install/uninstall can find and stop it without
// guessing. `serve` itself owns writing/removing it (rhize-tasks.mjs).
export function servePidPath(supportDir = defaultInstallPaths().supportDir) {
  return path.join(supportDir, 'serve.pid');
}

async function readServePid(pidPath) {
  try {
    const raw = (await readFile(pidPath, 'utf8')).trim();
    const pid = Number.parseInt(raw, 10);
    return Number.isInteger(pid) && pid > 0 ? pid : null;
  } catch {
    return null;
  }
}

// A dashboard-spawned `serve` process holds the SQLite DB open and keeps
// running indefinitely — reinstalling or uninstalling used to either fail
// outright (checkLoopbackPort below) or delete the runtime/database out
// from under it (finding #1). Stop it, using the pidfile it wrote, and
// confirm it actually exited before the caller proceeds.
export async function stopServeProcessIfRunning({
  pidPath,
  readPidFile = readServePid,
  killPid = (pid, signal) => process.kill(pid, signal),
  isRunning = pid => { try { process.kill(pid, 0); return true; } catch (error) { return error.code === 'EPERM'; } },
  waitMs = 3_000,
  pollMs = 100,
} = {}) {
  const pid = await readPidFile(pidPath);
  if (!Number.isInteger(pid)) return {stopped: false, reason: 'no_pid_file'};
  try {
    killPid(pid, 'SIGTERM');
  } catch (error) {
    if (error.code === 'ESRCH') return {stopped: true, reason: 'already_exited'};
    throw error;
  }
  const deadline = Date.now() + waitMs;
  while (Date.now() < deadline) {
    if (!isRunning(pid)) return {stopped: true, reason: 'terminated'};
    await new Promise(resolve => setTimeout(resolve, pollMs));
  }
  return {stopped: false, reason: 'timed_out'};
}

function tryBind(port, createServerImpl) {
  return new Promise((resolve, reject) => {
    const server = createServerImpl();
    server.unref?.();
    server.once('error', error => resolve({free: false, error}));
    server.listen({host: '127.0.0.1', port, exclusive: true}, () => server.close(() => resolve({free: true})));
  });
}

export async function checkLoopbackPort(port, {
  createServerImpl = createServer,
  probeOwnServer = defaultProbeOwnServer,
  pidPath = servePidPath(),
  stopOwnServer = stopServeProcessIfRunning,
} = {}) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('invalid_loopback_port');
  let attempt = await tryBind(port, createServerImpl);
  if (attempt.free) return;
  if (attempt.error.code !== 'EADDRINUSE') throw new Error('loopback_port_check_failed');

  const ownServer = await probeOwnServer(port).catch(() => null);
  if (!ownServer) throw new Error('loopback_port_in_use');

  // It's our own `serve` process, not an unrelated conflict — stop it and
  // proceed instead of reporting a bare "port in use" the user can't act on
  // (finding #1). If we can't confirm it actually stopped, fail loudly
  // rather than racing a bind against a process that might still be there.
  const outcome = await stopOwnServer({pidPath});
  if (!outcome.stopped) {
    throw Object.assign(new Error(`loopback_port_held_by_own_server:${ownServer.version}:${outcome.reason}`), {code: 'loopback_port_held_by_own_server', version: ownServer.version, reason: outcome.reason});
  }

  attempt = await tryBind(port, createServerImpl);
  if (!attempt.free) throw Object.assign(new Error('own_server_stop_did_not_free_port'), {code: 'own_server_stop_did_not_free_port'});
}

// `>= 22` alone is too loose: node:sqlite (service/src/storage/database.mjs)
// needed --experimental-sqlite for part of the 22.x line, the plist passes
// no flags, and a build that lacks it dies at import with
// ERR_UNKNOWN_BUILTIN_MODULE weeks after a clean-looking install (finding
// #25). Rather than hardcode a minor-version cutover that could itself go
// stale, probe the actual node binary for the capability it needs.
export async function checkNodeSqliteAvailable({run = runProcess, nodePath = process.execPath} = {}) {
  let result;
  try {
    result = await run(nodePath, ['--input-type=module', '--eval', "await import('node:sqlite'); process.stdout.write('ok');"], {timeoutMs: 10_000, maxOutputBytes: 4_096});
  } catch {
    throw new Error('node_sqlite_unavailable');
  }
  if (!result || result.code !== 0 || result.timedOut || result.stdout?.trim() !== 'ok') throw new Error('node_sqlite_unavailable');
}

export async function validatePrerequisites({
  platform = process.platform,
  macOSVersion,
  nodeVersion = process.versions.node,
  nodePath = process.execPath,
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
  await checkNodeSqliteAvailable({run, nodePath});
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
  await checkPort(port, {pidPath: servePidPath(supportDir)});
  return {platform, macOSVersion: detectedVersion, nodeMajor: Number.parseInt(nodeVersion.split('.')[0], 10), port};
}

function xmlEscape(value) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');
}

const OUTPUT_TAIL_CHARS = 4_000;
function outputTail(text) {
  if (typeof text !== 'string' || text.length <= OUTPUT_TAIL_CHARS) return text ?? '';
  return `…${text.slice(-OUTPUT_TAIL_CHARS)}`;
}

// Previously discarded stdout/stderr entirely, so the top first-install
// failure (CLT-only toolchain popping the Swift build modal) left no trace
// of *why* the command failed (finding #6). Every field here is safe to
// surface: these two commands (`swift build`, `codesign`) never receive
// secrets on their command line or in their own output.
async function runChecked(file, args, options = {}, run = runProcess) {
  const result = await run(file, args, options);
  if (!result || result.code !== 0 || result.timedOut) {
    const reason = result?.timedOut ? 'timed_out' : `exit_${result?.code ?? 'unknown'}`;
    const error = new Error(`installer_command_failed:${path.basename(file)}:${reason}`);
    error.code = 'installer_command_failed';
    error.command = file;
    error.args = args;
    error.exitCode = result?.code ?? null;
    error.timedOut = result?.timedOut === true;
    error.stdout = outputTail(result?.stdout);
    error.stderr = outputTail(result?.stderr);
    throw error;
  }
  return result;
}

async function removeApiBearer(keychain) {
  const failures = [];
  try { await keychain.delete('media.rhize.tasks.api', 'bearer'); } catch { failures.push('token_delete_failed'); }
  try { await keychain.get('media.rhize.tasks.api', 'bearer'); failures.push('token_delete_unverified'); } catch (error) { if (error?.kind !== 'not_found') failures.push('token_absence_verification_failed'); }
  return failures;
}

const TOKEN_DELETE_REMEDIATION = 'security delete-generic-password -s media.rhize.tasks.api -a bearer';

function tokenCleanupError(cause, failures) {
  const error = new Error(`api_token_cleanup_failed:${failures.join(',')}. Run: ${TOKEN_DELETE_REMEDIATION}`); error.code = 'api_token_cleanup_failed'; error.cleanupState = failures.join(','); error.remediation = TOKEN_DELETE_REMEDIATION; error.cause = cause; return error;
}

// A prior invalid/corrupt token (too short to be one of ours) used to be an
// unrecoverable dead end: this threw api_token_invalid and never reached the
// `-U` (overwrite) keychain call below it, so every later install failed the
// same way with no documented recovery (finding #24). Keychain's `set()`
// already overwrites via `-U`, so an invalid existing value now just falls
// through to being replaced like a missing one; only a failure to overwrite
// (handled by the catch below, via tokenCleanupError's remediation hint)
// remains a dead end.
export async function ensureApiBearer({keychain, randomBytesImpl = randomBytes}) {
  if (!keychain?.get || !keychain?.set || !keychain?.delete) throw new TypeError('invalid_keychain');
  try {
    const existing = await keychain.get('media.rhize.tasks.api', 'bearer');
    if (typeof existing === 'string' && existing.length >= 32) return {created: false};
  } catch (error) {
    if (error?.kind !== 'not_found') throw error;
  }
  const value = randomBytesImpl(32).toString('base64url');
  try {
    await keychain.set('media.rhize.tasks.api', 'bearer', value);
    if (await keychain.get('media.rhize.tasks.api', 'bearer') !== value) throw new Error('api_token_verification_failed');
    return {created: true};
  } catch (error) {
    const cleanupFailures = await removeApiBearer(keychain);
    if (cleanupFailures.length) throw tokenCleanupError(error, cleanupFailures);
    throw error;
  }
}

// These four placeholders are always filesystem paths in this template,
// never credential material — a checkout under a path like
// ~/dev/secrets-tooling/ must not fail install just because the word
// "secrets" appears inside NODE_PATH/CLI_PATH/STDOUT_PATH/STDERR_PATH
// (finding #25). Scan everything else (the static template plus any future
// placeholder not listed here) so real secret material is still caught.
const pathShapedPlaceholders = new Set(['NODE_PATH', 'CLI_PATH', 'STDOUT_PATH', 'STDERR_PATH']);

export async function renderLaunchAgent({nodePath, cliPath, stdoutPath, stderrPath, templatePath = path.join(installerDir, 'media.rhize.tasks.plist.template')}) {
  const template = await readFile(templatePath, 'utf8');
  const values = {NODE_PATH: nodePath, CLI_PATH: cliPath, STDOUT_PATH: stdoutPath, STDERR_PATH: stderrPath};
  const rendered = Object.entries(values).reduce((text, [key, value]) => text.replaceAll(`{{${key}}}`, xmlEscape(path.resolve(value))), template);
  if (/{{[A-Z_]+}}/.test(rendered)) throw new Error('unresolved_launch_agent_placeholder');
  const scanTarget = Object.entries(values).reduce((text, [key, value]) => pathShapedPlaceholders.has(key) ? text.replaceAll(xmlEscape(path.resolve(value)), '') : text, rendered);
  if (/token|secret|password|bearer/i.test(scanTarget)) throw new Error('launch_agent_may_not_contain_secrets');
  return rendered;
}

// process.execPath is realpath()'d by libuv, so a version-manager shim
// resolves to a path that stops existing the moment the version changes or
// the installing terminal closes — fnm's multishell dir dies with the
// terminal, nvm's lives under a version directory, Homebrew's default
// cleanup deletes the old Cellar path on upgrade (finding #4). The agent
// would then fail posix_spawn every 15 minutes with no obvious signal.
const ephemeralNodePathPatterns = [/\.nvm\//, /fnm_multishells/, /\/Cellar\/node\//, /\/n\/versions\/node\//, /\.volta\/tmp\//];

function looksEphemeral(candidate) {
  return ephemeralNodePathPatterns.some(pattern => pattern.test(candidate));
}

const NODE_PATH_REMEDIATION = 'Install Node from https://nodejs.org/en/download (the macOS .pkg installer, not a version manager) so the LaunchAgent has a path that survives logout, or set RHIZE_TASKS_ALLOW_EPHEMERAL_NODE=1 to install anyway.';

// X_OK alone only proves the candidate is *a* node binary, not a capable
// one — /usr/local/bin/node or /opt/homebrew/bin/node could be an old
// Node 18 install or otherwise lack node:sqlite, and would still pass
// checkExecutable (finding #4-followup / #9). Probe the actual binary for
// both the version floor and node:sqlite, the same capability the plist
// will need at runtime.
async function defaultVerifyNodeCapable(nodePath, {run = runProcess} = {}) {
  let result;
  try {
    result = await run(nodePath, ['--input-type=module', '--eval', "if (Number.parseInt(process.versions.node.split('.')[0], 10) < 22) throw new Error('node_floor'); await import('node:sqlite'); process.stdout.write('ok');"], {timeoutMs: 10_000, maxOutputBytes: 4_096});
  } catch {
    return false;
  }
  return Boolean(result && result.code === 0 && !result.timedOut && result.stdout?.trim() === 'ok');
}

export async function resolveInstallNodePath(candidate, checkExecutable, {
  verifyCapable = defaultVerifyNodeCapable,
  allowEphemeral = process.env.RHIZE_TASKS_ALLOW_EPHEMERAL_NODE === '1',
} = {}) {
  const warnings = [];
  if (looksEphemeral(candidate)) {
    for (const alternate of ['/usr/local/bin/node', '/opt/homebrew/bin/node']) {
      const executable = await checkExecutable(alternate).then(() => true, () => false);
      if (executable && await verifyCapable(alternate)) return {nodePath: alternate, warnings};
    }
    // No stable, capable alternative exists. Persisting the ephemeral path
    // anyway means the LaunchAgent posix_spawn-fails silently the moment the
    // installing terminal closes (fnm) or the version manager cleans up the
    // old path (nvm/Homebrew) — finding #4/#9. Fail closed by default.
    if (!allowEphemeral) {
      throw Object.assign(new Error(`node_path_ephemeral_no_stable_alternative:${candidate}`), {
        code: 'node_path_ephemeral_no_stable_alternative',
        remediation: NODE_PATH_REMEDIATION,
      });
    }
    warnings.push(`node_path_ephemeral:${candidate}`);
  }
  try {
    await checkExecutable(candidate);
  } catch {
    throw new Error(`node_path_not_executable:${candidate}`);
  }
  if (!await verifyCapable(candidate)) throw Object.assign(new Error(`node_path_incapable:${candidate}`), {code: 'node_path_incapable'});
  return {nodePath: candidate, warnings};
}

// Best-effort only: the seeded test fixture's Info.plist has neither key,
// and that must stay a no-op rather than a hard failure — this exists to
// stop N differently-signed bundles from all claiming the same
// CFBundleShortVersionString (finding #3), not to enforce plist shape.
function withPlistStringValue(xml, key, value) {
  const pattern = new RegExp(`(<key>${key}</key>\\s*<string>)[^<]*(</string>)`);
  return pattern.test(xml) ? xml.replace(pattern, (_, prefix, suffix) => `${prefix}${xmlEscape(value)}${suffix}`) : xml;
}

async function renderHelperInfoPlist({templatePath, version}) {
  const template = await readFile(templatePath, 'utf8');
  return withPlistStringValue(withPlistStringValue(template, 'CFBundleShortVersionString', version), 'CFBundleVersion', version);
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

async function placeRuntimeCandidate(stagePath, targetPath, beforeMutation = async () => {}) {
  const backupPath = `${targetPath}.previous-${process.pid}`;
  let hadTarget = false;
  try {
    await access(targetPath);
    hadTarget = true;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  await beforeMutation(backupPath);
  await rm(backupPath, {recursive: true, force: true});
  if (hadTarget) {
    await beforeMutation(targetPath);
    await rename(targetPath, backupPath);
  }
  try {
    await beforeMutation(targetPath);
    await rename(stagePath, targetPath);
  } catch (error) {
    if (hadTarget) {
      await beforeMutation(targetPath);
      await rename(backupPath, targetPath);
    }
    throw error;
  }
  return {backupPath, hadTarget, targetPath};
}

async function rollbackRuntimeCandidate(transaction, beforeMutation = async () => {}) {
  await beforeMutation(transaction.targetPath);
  await rm(transaction.targetPath, {recursive: true, force: true});
  if (transaction.hadTarget) {
    await beforeMutation(transaction.targetPath);
    await rename(transaction.backupPath, transaction.targetPath);
  }
}

async function finalizeRuntimeCandidate(transaction, beforeMutation = async () => {}) {
  await beforeMutation(transaction.backupPath);
  await rm(transaction.backupPath, {recursive: true, force: true});
}

// Shared by pruneOldRuntimeVersions and sweepStaleArtifacts: matches both
// `.installing-<pid>` stage dirs and `<version>.previous-<pid>` backups.
const staleArtifactSuffixPattern = /\.(?:installing|previous)-\d+$/;

// Old numbered version directories (versions/0.1.0 next to versions/0.2.0)
// used to survive forever, each one an independently ad-hoc-signed bundle at
// its own path (finding #3). .installing-<pid>/.previous-<pid> artifacts are
// a separate, pid-liveness-checked concern (sweepStaleArtifacts, finding
// #23) and are deliberately left alone here — an unconditional delete here
// could otherwise race a concurrently *running* install's own backup.
async function pruneOldRuntimeVersions(versionsDir, currentVersion, beforeMutation = async () => {}) {
  let entries;
  try { entries = await readdir(versionsDir); } catch { return; }
  for (const entry of entries) {
    if (entry === currentVersion || staleArtifactSuffixPattern.test(entry)) continue;
    const target = path.join(versionsDir, entry);
    try {
      await beforeMutation(target);
      await rm(target, {recursive: true, force: true});
    } catch {}
  }
}

const runningPid = pid => { try { process.kill(pid, 0); return true; } catch (error) { return error.code === 'EPERM'; } };

// Ctrl-C during the ~2 minute Swift build (or any other interruption) used
// to leave a complete runtime copy behind per attempt, since .installing-*
// stage dirs and *.previous-<pid> rollback backups were only ever cleaned
// up on the happy path (finding #23). Sweep any such artifact whose
// embedded pid is no longer running before starting a new install.
async function sweepStaleArtifacts(directory, pattern, beforeMutation = async () => {}) {
  let entries;
  try { entries = await readdir(directory); } catch { return; }
  for (const entry of entries) {
    const match = pattern.exec(entry);
    if (!match) continue;
    const pid = Number.parseInt(match[1], 10);
    if (!Number.isInteger(pid) || runningPid(pid)) continue;
    const target = path.join(directory, entry);
    try {
      await beforeMutation(target);
      await rm(target, {recursive: true, force: true});
    } catch {}
  }
}

export async function atomicWriteFile(target, value, mode = 0o600, {beforeMutation = async () => {}} = {}) {
  const temporary = `${target}.installing-${process.pid}`;
  let handle;
  try {
    await beforeMutation(target);
    try {
      handle = await open(temporary, 'wx', mode);
    } catch (error) {
      // This filename embeds our own pid, so a pre-existing file here can
      // only be orphaned debris from an earlier process that reused this
      // pid across a reboot (finding #23) — never a concurrent writer,
      // since only one process can hold this pid right now. Clear it and
      // retry once instead of hard-failing with EEXIST.
      if (error.code !== 'EEXIST') throw error;
      await beforeMutation(temporary);
      await rm(temporary, {force: true});
      handle = await open(temporary, 'wx', mode);
    }
    await handle.writeFile(value);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await chmod(temporary, mode);
    await beforeMutation(target);
    await rename(temporary, target);
    const directory = await open(path.dirname(target), 'r');
    try {
      await directory.sync();
    } finally {
      await directory.close();
    }
  } catch (error) {
    await handle?.close().catch(() => {});
    try {
      await beforeMutation(target);
      await rm(temporary, {force: true});
    } catch {}
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

async function restoreFile(target, snapshot, writeMetadata, beforeMutation) {
  await beforeMutation(target);
  if (!snapshot.exists) {
    await rm(target, {force: true});
    return;
  }
  await writeMetadata(target, snapshot.bytes, snapshot.mode, {beforeMutation});
}

async function assertFileRestored(target, snapshot) {
  if (!snapshot.exists) {
    try {
      await lstat(target);
    } catch (error) {
      if (error.code === 'ENOENT') return;
      throw error;
    }
    throw new Error('restored_file_should_be_absent');
  }
  const metadata = await lstat(target);
  if (!metadata.isFile() || metadata.isSymbolicLink() || (metadata.mode & 0o777) !== snapshot.mode || !(await readFile(target)).equals(snapshot.bytes)) throw new Error('restored_file_mismatch');
}

function activationError(activationState, cause, rollbackFailures = []) {
  const error = new Error(rollbackFailures.length === 0 ? `local_activation_failed:${activationState}` : `local_activation_rollback_failed:${activationState}:${rollbackFailures.join(',')}`);
  error.code = rollbackFailures.length === 0 ? 'local_activation_failed' : 'local_activation_rollback_failed';
  error.activationState = activationState;
  error.rollbackState = rollbackFailures.length === 0 ? 'restored' : rollbackFailures.join(',');
  error.cause = cause;
  return error;
}

function assertLoadedConfiguration(state, plistPath) {
  if (!state.loaded || typeof state.configurationPath !== 'string' || path.resolve(state.configurationPath) !== path.resolve(plistPath)) throw new Error('launchctl_configuration_mismatch');
}

function isBootstrapInProgress(result) {
  return typeof result?.stderr === 'string' && /Operation already in progress/i.test(result.stderr);
}

const defaultSleep = ms => new Promise(resolve => setTimeout(resolve, ms));

// A bootout immediately followed by bootstrap can race the old job's
// termination — launchctl then answers "Bootstrap failed: 37: Operation
// already in progress", which used to roll back an otherwise-healthy
// install (finding #20). Retry is deliberately narrow: it only fires for
// this specific, identified transient message, so a genuinely broken plist
// still fails on the first attempt exactly as before.
async function bootstrapAgent({run, domain, plistPath}, attempts = 3, delayMs = 250, sleep = defaultSleep) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    let result;
    try {
      result = await run('/bin/launchctl', ['bootstrap', domain, plistPath], {timeoutMs: 15_000, maxOutputBytes: 64_000});
    } catch {
      throw new Error('launchctl_bootstrap_uncertain');
    }
    if (result?.code === 0 && !result.timedOut) return;
    if (attempt < attempts - 1 && isBootstrapInProgress(result)) { await sleep(delayMs); continue; }
    break;
  }
  throw new Error('launchctl_bootstrap_uncertain');
}

export async function install({
  paths = defaultInstallPaths(),
  pathPolicy = productionPathPolicy(),
  port = 43179,
  run = runProcess,
  uid = process.getuid?.(),
  nodePath = process.execPath,
  checkNodePathExecutable = file => access(file, fsConstants.X_OK),
  verifyNodePathCapable = defaultVerifyNodeCapable,
  sourceRoot = pluginRoot,
  validate = validatePrerequisites,
  writeMetadata = atomicWriteFile,
  keychain = createKeychain({spawnFile: run}),
} = {}) {
  await verifyInstallPaths(paths, pathPolicy);
  await validate({supportDir: paths.supportDir, port, run});
  await verifyInstallPaths(paths, pathPolicy);
  const packageDocument = JSON.parse(await readFile(path.join(sourceRoot, 'package.json'), 'utf8'));
  if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(packageDocument.version ?? '')) throw new Error('invalid_runtime_version');
  const version = packageDocument.version;
  // Validate and, where the resolved path looks ephemeral, stabilize the
  // node path BEFORE the ~2 minute Swift build (finding #4) so a bad path
  // fails fast instead of after paying that cost.
  const {nodePath: resolvedNodePath, warnings: nodePathWarnings} = await resolveInstallNodePath(nodePath, checkNodePathExecutable, {verifyCapable: verifyNodePathCapable});
  const packagePath = path.join(sourceRoot, 'native', 'reminders-helper');
  // No paid Developer ID identity is available on this machine today (0
  // identities), so ad-hoc signing (`-`) remains the default; this override
  // lets a future stable signing identity be supplied without a code change.
  const signingIdentity = (process.env.RHIZE_TASKS_SIGN_IDENTITY ?? '').trim() || '-';
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
  const pathIdentities = await captureInstallPathIdentities(paths, pathPolicy);
  const beforeMutation = target => assertInstallPathIdentities(pathIdentities, target);
  // A kill during a prior install (Ctrl-C during the ~2 minute Swift build
  // is the likely case, per finding #5) used to leave a complete runtime
  // copy behind forever — nothing ever swept a dead pid's leftover
  // .installing-<pid> stage dir or <version>.previous-<pid> backup
  // (finding #23). Sweep any such artifact whose owning pid is no longer
  // running before this install adds one of its own.
  await sweepStaleArtifacts(paths.runtimeDir, /^\.installing-(\d+)$/, beforeMutation);
  await sweepStaleArtifacts(versionsDir, /\.previous-(\d+)$/, beforeMutation);
  const priorPlist = await snapshotFile(paths.launchAgentPath);
  const priorManifest = await snapshotFile(paths.installationManifestPath);
  const domain = `gui/${uid}`;
  const priorAgent = await getLaunchAgentState({run, domain, label});
  if (priorAgent.loaded) assertLoadedConfiguration(priorAgent, paths.launchAgentPath);
  const stagePath = path.join(paths.runtimeDir, `.installing-${process.pid}`);
  const runtimePath = path.join(versionsDir, version);
  await verifyRuntimePath(paths, runtimePath, pathPolicy);
  await beforeMutation(stagePath);
  await rm(stagePath, {recursive: true, force: true});

  let runtimeTransaction;
  let activationState = 'stage_build_failed';
  let priorBootoutAttempted = false;
  let oldAgentStopped = false;
  let newBootstrapState = 'not_attempted';
  let tokenCreated = false;
  let appPath;
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
    await writeFile(path.join(appPathInStage, 'Contents', 'Info.plist'), await renderHelperInfoPlist({templatePath: path.join(packagePath, 'Resources', 'Info.plist'), version}));
    await chmod(path.join(appPathInStage, 'Contents', 'MacOS', 'RhizeRemindersHelper'), 0o700);
    // codesign BEFORE hardenTree (finding #25): signing after hardening left
    // the generated _CodeSignature/CodeResources at the process umask,
    // breaking the "everything is 0600" invariant for exactly the signature
    // material. hardenTree now walks the tree once, after signing, so it
    // normalizes what codesign just wrote too.
    await runChecked('/usr/bin/codesign', ['--force', '--sign', signingIdentity, appPathInStage], {timeoutMs: 30_000}, run);
    await hardenTree(stagePath, new Set(['RhizeRemindersHelper']));
    await assertInstallPathIdentities(pathIdentities);

    // Stop the OLD agent BEFORE the runtime directory is swapped (finding
    // #21). On a same-version reinstall — the common case — the swap target
    // IS the currently-running agent's code: booting out afterward left a
    // window where a running routine could be mid-import()ing from a
    // directory that had just been renamed away and was about to be
    // deleted, and let launchd's 15-minute timer spawn a fresh job from the
    // OLD plist against the NEW code in between.
    activationState = 'bootout_failed';
    if (priorAgent.loaded) {
      priorBootoutAttempted = true;
      await bootoutIfLoaded({run, domain, plistPath: paths.launchAgentPath, label});
      oldAgentStopped = true;
    }

    activationState = 'runtime_swap_failed';
    runtimeTransaction = await placeRuntimeCandidate(stagePath, runtimePath, beforeMutation);

    const cliPath = path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs');
    appPath = path.join(runtimePath, 'native', 'RhizeRemindersHelper.app');
    const plist = await renderLaunchAgent({
      nodePath: resolvedNodePath,
      cliPath,
      stdoutPath: path.join(paths.logDir, 'routine.log'),
      stderrPath: path.join(paths.logDir, 'routine-error.log'),
    });
    // Recorded so `doctor` can assert the plist's node path still exists
    // without re-deriving the ephemeral-path heuristic itself.
    const manifest = `${JSON.stringify({schemaVersion: 1, version, runtimePath, cliPath, appPath, label, nodePath: resolvedNodePath}, null, 2)}\n`;

    await assertInstallPathIdentities(pathIdentities);
    activationState = 'token_provision_failed';
    tokenCreated = (await ensureApiBearer({keychain})).created;
    activationState = 'metadata_write_failed';
    await assertInstallPathIdentities(pathIdentities);
    await writeMetadata(paths.launchAgentPath, plist, 0o600, {beforeMutation});
    await assertInstallPathIdentities(pathIdentities);
    await writeMetadata(paths.installationManifestPath, manifest, 0o600, {beforeMutation});
    await verifyInstallPaths(paths, pathPolicy);
    activationState = 'bootstrap_failed';
    await assertInstallPathIdentities(pathIdentities);
    newBootstrapState = 'attempted_uncertain';
    await bootstrapAgent({run, domain, plistPath: paths.launchAgentPath});
    newBootstrapState = 'succeeded';
    activationState = 'activation_verification_failed';
    assertLoadedConfiguration(await getLaunchAgentState({run, domain, label}), paths.launchAgentPath);
    await finalizeRuntimeCandidate(runtimeTransaction, beforeMutation);
    // Best-effort: an old version dir left behind is hygiene debt, not a
    // reason to fail an otherwise-successful install (finding #3 — "old
    // versions are never pruned", multiplying stale ad-hoc-signed bundles).
    await pruneOldRuntimeVersions(versionsDir, version, beforeMutation);
    return {appPath, launchAgentPath: paths.launchAgentPath, runtimePath, version, label, nodePath: resolvedNodePath, ...(nodePathWarnings.length ? {nodePathWarnings} : {})};
  } catch (activationFailure) {
    const rollbackFailures = [];
    // `agentMayHaveChanged` is "did we touch launchd at all" (old bootout
    // attempted, or a new bootstrap attempted) — it does NOT mean either one
    // actually succeeded. Rolling back on the strength of "attempted" alone
    // used to have two failure modes (finding #4-followup): (a) a failure
    // *before* the old agent was ever stopped still tried to re-bootstrap
    // it — harmless in itself, but it turns a pre-swap failure like a
    // codesign error into a confusing local_activation_rollback_failed; (b)
    // a failure *after* the swap, where confirming the new job's bootout
    // itself failed, still went ahead and swapped the runtime/plist back —
    // pulling the rug out from under a process we never confirmed was
    // stopped, recreating the exact race finding #21 exists to prevent,
    // just during rollback. `agentConfirmedStopped` gates the two mutating
    // steps that only matter once we KNOW nothing is running against the
    // runtime we're about to touch.
    const agentMayHaveChanged = priorBootoutAttempted || newBootstrapState !== 'not_attempted';
    let agentConfirmedStopped = !agentMayHaveChanged;
    if (agentMayHaveChanged) {
      try {
        await beforeMutation(paths.launchAgentPath);
        await bootoutServiceIfLoaded({run, domain, label});
        if ((await getLaunchAgentState({run, domain, label})).loaded) throw new Error('launchctl_service_still_loaded');
        agentConfirmedStopped = true;
      } catch {
        rollbackFailures.push('agent_bootout_failed');
      }
    }

    // Always safe regardless of agent state: our own not-yet-activated
    // stage directory. Only reached when the swap never happened
    // (runtimeTransaction unset), so nothing live is at risk either way.
    if (!runtimeTransaction) {
      try {
        await beforeMutation(stagePath);
        await rm(stagePath, {recursive: true, force: true});
      } catch {}
    }

    if (!agentConfirmedStopped) {
      throw activationError(activationState, activationFailure, [...rollbackFailures, 'manual_recovery_required']);
    }

    if (runtimeTransaction) {
      try { await rollbackRuntimeCandidate(runtimeTransaction, beforeMutation); } catch { rollbackFailures.push('runtime_restore_failed'); }
    }
    if (tokenCreated) rollbackFailures.push(...await removeApiBearer(keychain));
    try { await restoreFile(paths.installationManifestPath, priorManifest, writeMetadata, beforeMutation); } catch { rollbackFailures.push('manifest_restore_failed'); }
    try { await restoreFile(paths.launchAgentPath, priorPlist, writeMetadata, beforeMutation); } catch { rollbackFailures.push('plist_restore_failed'); }
    try {
      await assertFileRestored(paths.launchAgentPath, priorPlist);
      await assertFileRestored(paths.installationManifestPath, priorManifest);
    } catch {
      rollbackFailures.push('metadata_verification_failed');
    }
    if (priorAgent.loaded && oldAgentStopped) {
      try {
        await beforeMutation(paths.launchAgentPath);
        if (!priorPlist.exists || !priorManifest.exists) throw new Error('prior_configuration_incomplete');
        await assertFileRestored(paths.launchAgentPath, priorPlist);
        await assertFileRestored(paths.installationManifestPath, priorManifest);
        await bootstrapAgent({run, domain, plistPath: paths.launchAgentPath});
        assertLoadedConfiguration(await getLaunchAgentState({run, domain, label}), paths.launchAgentPath);
      } catch {
        rollbackFailures.push('agent_restore_failed');
      }
    } else if (!priorAgent.loaded) {
      try {
        const current = await getLaunchAgentState({run, domain, label});
        if (current.loaded) {
          await beforeMutation(paths.launchAgentPath);
          await bootoutServiceIfLoaded({run, domain, label});
        }
        if ((await getLaunchAgentState({run, domain, label})).loaded) throw new Error('launchctl_service_still_loaded');
      } catch {
        rollbackFailures.push('agent_restore_failed');
      }
    }
    // else: priorAgent.loaded && !oldAgentStopped -> the old agent was
    // never touched (nothing to restore); leaving it running as-is is
    // correct.
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
