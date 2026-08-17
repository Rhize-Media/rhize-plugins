import {lstat, realpath} from 'node:fs/promises';
import {homedir} from 'node:os';
import path from 'node:path';

const testPolicyMarker = Symbol('Rhize Tasks test path policy');

export function exactInstallPaths(home = homedir()) {
  const resolvedHome = path.resolve(home);
  const supportDir = path.join(resolvedHome, 'Library', 'Application Support', 'Rhize Tasks');
  return {
    supportDir,
    runtimeDir: path.join(supportDir, 'runtime'),
    launchAgentPath: path.join(resolvedHome, 'Library', 'LaunchAgents', 'media.rhize.tasks.plist'),
    // The Reminders helper is its own launchd job (its own TCC-responsible
    // process) with its own stable bundle and socket, outside the
    // per-version runtime tree.
    helperLaunchAgentPath: path.join(resolvedHome, 'Library', 'LaunchAgents', 'media.rhize.tasks.reminders-helper.plist'),
    logDir: path.join(supportDir, 'logs'),
    installationManifestPath: path.join(supportDir, 'installation.json'),
    helperAppPath: path.join(supportDir, 'native', 'RhizeRemindersHelper.app'),
    helperSocketPath: path.join(supportDir, 'reminders-helper.sock'),
  };
}

export function createTestPathPolicy(home) {
  if (typeof home !== 'string' || home.length === 0) throw new TypeError('invalid_test_home');
  return Object.freeze({home: path.resolve(home), [testPolicyMarker]: true});
}

export function productionPathPolicy() {
  return Object.freeze({home: path.resolve(homedir()), production: true});
}

function policyHome(policy) {
  if (policy?.production === true && policy.home === path.resolve(homedir())) return policy.home;
  if (policy?.[testPolicyMarker] === true) return policy.home;
  throw new Error('invalid_install_path_policy');
}

function requireExactPaths(paths, home) {
  const expected = exactInstallPaths(home);
  for (const key of Object.keys(expected)) {
    if (typeof paths?.[key] !== 'string' || path.resolve(paths[key]) !== expected[key]) throw new Error(`unsafe_install_path_${key}`);
  }
}

async function inspectChain(home, target, targetKind = 'either') {
  const relative = path.relative(home, target);
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('install_path_outside_home');
  const segments = relative === '' ? [] : relative.split(path.sep);
  let current = home;
  const chain = [{value: home, final: segments.length === 0}];
  for (let index = 0; index < segments.length; index += 1) {
    current = path.join(current, segments[index]);
    chain.push({value: current, final: index === segments.length - 1});
  }
  for (const entry of chain) {
    let metadata;
    try {
      metadata = await lstat(entry.value);
    } catch (error) {
      if (error.code === 'ENOENT') return;
      throw error;
    }
    if (metadata.isSymbolicLink()) {
      // The home directory itself being a symlink (common on managed Macs
      // with NFS/AFP-mounted or redirected home directories) is a platform
      // fact, not evidence of an attacker swapping one of our own managed
      // subpaths — `symlink_install_path` reads like a security violation
      // for what is really "install path checks cannot be enforced here"
      // (finding #25). Everywhere else in the chain, a symlink is still
      // exactly the tamper signal this function exists to catch.
      if (entry.value === home) throw new Error(`home_directory_is_symlink:${entry.value}: home directory is a symlink; install path checks cannot be enforced`);
      throw new Error(`symlink_install_path:${entry.value}`);
    }
    const expectedKind = entry.final ? targetKind : 'directory';
    if (expectedKind === 'directory' && !metadata.isDirectory()) throw new Error(`non_directory_install_path:${entry.value}`);
    if (expectedKind === 'file' && !metadata.isFile()) throw new Error(`non_file_install_path:${entry.value}`);
    // The helper's Unix socket is a live special file while the helper is
    // running, not a regular file — `isFile()` is always false for it, so
    // it needs its own kind rather than being checked as 'file'.
    if (expectedKind === 'socket' && !metadata.isSocket()) throw new Error(`non_socket_install_path:${entry.value}`);
  }
}

async function assertRealContainment(home, target) {
  let actual;
  try {
    actual = await realpath(target);
  } catch (error) {
    if (error.code === 'ENOENT') return;
    throw error;
  }
  const trusted = await realpath(home);
  const relative = path.relative(trusted, actual);
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('real_install_path_outside_home');
}

async function pathIdentity(target) {
  try {
    const metadata = await lstat(target);
    if (metadata.isSymbolicLink() || !metadata.isDirectory()) throw new Error(`unsafe_identity_path:${target}`);
    return {path: target, exists: true, dev: String(metadata.dev), ino: String(metadata.ino)};
  } catch (error) {
    if (error.code === 'ENOENT') return {path: target, exists: false};
    throw error;
  }
}

function identityTargets(paths, home) {
  return [...new Set([
    home,
    path.join(home, 'Library'),
    path.join(home, 'Library', 'Application Support'),
    paths.supportDir,
    paths.runtimeDir,
    path.join(paths.runtimeDir, 'versions'),
    paths.logDir,
    path.dirname(paths.launchAgentPath),
    // The helper bundle's own stable directory (`supportDir/native`) — like
    // `runtimeDir/versions`, this is tracked rather than the bundle itself,
    // since the bundle is the thing that gets atomically swapped.
    path.dirname(paths.helperAppPath),
  ])];
}

export async function verifyInstallPaths(paths, policy = productionPathPolicy()) {
  const home = policyHome(policy);
  requireExactPaths(paths, home);
  await inspectChain(home, home, 'directory');
  await inspectChain(home, paths.supportDir, 'directory');
  await inspectChain(home, paths.runtimeDir, 'directory');
  await inspectChain(home, paths.logDir, 'directory');
  await inspectChain(home, path.dirname(paths.launchAgentPath), 'directory');
  await inspectChain(home, paths.launchAgentPath, 'file');
  await inspectChain(home, paths.helperLaunchAgentPath, 'file');
  await inspectChain(home, paths.installationManifestPath, 'file');
  await inspectChain(home, path.dirname(paths.helperAppPath), 'directory');
  await inspectChain(home, paths.helperAppPath, 'directory');
  await inspectChain(home, paths.helperSocketPath, 'socket');
  for (const target of [
    paths.supportDir, paths.runtimeDir, paths.logDir, path.dirname(paths.launchAgentPath),
    paths.launchAgentPath, paths.helperLaunchAgentPath, paths.installationManifestPath,
    path.dirname(paths.helperAppPath), paths.helperAppPath, paths.helperSocketPath,
  ]) {
    await assertRealContainment(home, target);
  }
  return {home};
}

export async function captureInstallPathIdentities(paths, policy = productionPathPolicy()) {
  const {home} = await verifyInstallPaths(paths, policy);
  const identities = [];
  for (const target of identityTargets(paths, home)) identities.push(await pathIdentity(target));
  return Object.freeze({home, identities: Object.freeze(identities.map(identity => Object.freeze(identity)))});
}

function isAncestor(parent, target) {
  const relative = path.relative(parent, target);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

export async function assertInstallPathIdentities(snapshot, targets = null) {
  if (!snapshot || typeof snapshot.home !== 'string' || !Array.isArray(snapshot.identities)) throw new TypeError('invalid_install_path_identity_snapshot');
  const checkedTargets = targets === null ? null : (Array.isArray(targets) ? targets : [targets]).map(target => path.resolve(target));
  for (const expected of snapshot.identities.filter(identity => checkedTargets === null || checkedTargets.some(target => isAncestor(identity.path, target)))) {
    let current;
    try {
      current = await pathIdentity(expected.path);
    } catch {
      throw new Error(`install_path_identity_changed:${expected.path}`);
    }
    if (current.exists !== expected.exists || (current.exists && (current.dev !== expected.dev || current.ino !== expected.ino))) throw new Error(`install_path_identity_changed:${expected.path}`);
    if (current.exists) await assertRealContainment(snapshot.home, expected.path);
  }
}

export async function verifyRuntimePath(paths, runtimePath, policy = productionPathPolicy()) {
  const {home} = await verifyInstallPaths(paths, policy);
  const versionsDir = path.join(paths.runtimeDir, 'versions');
  const resolved = path.resolve(runtimePath);
  const relative = path.relative(versionsDir, resolved);
  if (relative.length === 0 || relative.startsWith('..') || path.isAbsolute(relative) || relative.includes(path.sep)) throw new Error('unsafe_installed_runtime_path');
  await inspectChain(home, resolved, 'directory');
  await assertRealContainment(home, resolved);
  return resolved;
}
