import {readFile, rm} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {pathToFileURL} from 'node:url';
import {bootoutIfLoaded} from './launchctl.mjs';
import {defaultInstallPaths, defaultProbeOwnServer, label, servePidPath, stopServeProcessIfRunning} from './install.mjs';
import {assertInstallPathIdentities, captureInstallPathIdentities, productionPathPolicy, verifyInstallPaths, verifyRuntimePath} from './safe-paths.mjs';
import {runProcess} from '../service/src/connectors/process-runner.mjs';

const allowedOptions = new Set(['--retain-data', '--delete-data', '--retain-items', '--delete-items']);

export function parseUninstallChoice(args) {
  if (args.some(arg => !allowedOptions.has(arg))) throw new Error('unknown_uninstall_option');
  const dataChoices = args.filter(arg => arg === '--retain-data' || arg === '--delete-data');
  const itemChoices = args.filter(arg => arg === '--retain-items' || arg === '--delete-items');
  if (dataChoices.length !== 1) throw new Error('choose_exactly_one_of_retain_data_or_delete_data');
  if (itemChoices.length !== 1) throw new Error('choose_exactly_one_of_retain_items_or_delete_items');
  return {
    data: dataChoices[0] === '--delete-data' ? 'delete' : 'retain',
    items: itemChoices[0] === '--delete-items' ? 'delete' : 'retain',
  };
}

function validateChoices(choices) {
  if (!choices || !['retain', 'delete'].includes(choices.data)) throw new Error('explicit_data_choice_required');
  if (!['retain', 'delete'].includes(choices.items)) throw new Error('explicit_item_choice_required');
}

export async function requestInstalledItemCleanup({paths, pathPolicy = productionPathPolicy(), run = runProcess, nodePath = process.execPath}) {
  let installation;
  try {
    installation = JSON.parse(await readFile(paths.installationManifestPath, 'utf8'));
  } catch {
    throw new Error('item_cleanup_manifest_invalid');
  }
  const runtimePath = await verifyRuntimePath(paths, installation?.runtimePath ?? '', pathPolicy);
  const cliPath = path.resolve(installation?.cliPath ?? '');
  if (installation?.schemaVersion !== 1 || cliPath !== path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs')) {
    throw new Error('item_cleanup_manifest_invalid');
  }
  const request = {
    schemaVersion: 1,
    scope: {reminders: 'plugin-owned', calendar: 'plugin-owned'},
    ownership: {
      remindersMarkerPrefix: 'rhize-tasks:item:',
      calendarPrivateProperty: 'rhizeOperationKey',
    },
    requireVerifiedResults: true,
  };
  let result;
  try {
    result = await run(nodePath, [cliPath, 'uninstall-items', '--json'], {
      input: `${JSON.stringify(request)}\n`, timeoutMs: 60_000, maxOutputBytes: 256_000,
      env: Object.fromEntries([['HOME', process.env.HOME], ['LANG', process.env.LANG], ['TMPDIR', process.env.TMPDIR]].filter(([, value]) => typeof value === 'string')),
    });
  } catch {
    throw new Error('item_cleanup_failed');
  }
  if (!result || result.code !== 0 || result.timedOut || result.outputExceeded || typeof result.stdout !== 'string') throw new Error('item_cleanup_failed');
  const lines = result.stdout.split(/\r?\n/).filter(Boolean);
  if (lines.length !== 1) throw new Error('item_cleanup_unverified');
  let response;
  try {
    response = JSON.parse(lines[0]);
  } catch {
    throw new Error('item_cleanup_unverified');
  }
  const verified = system => response?.[system]?.verified === true && Number.isInteger(response[system].deleted) && response[system].deleted >= 0;
  if (response?.ok !== true || !verified('reminders') || !verified('calendar')) throw new Error('item_cleanup_unverified');
  return response;
}

export async function uninstall({choices, paths = defaultInstallPaths(), pathPolicy = productionPathPolicy(), run = runProcess, uid = process.getuid?.(), nodePath = process.execPath, port = 43179, stopOwnServer = stopServeProcessIfRunning, probeOwnServer = defaultProbeOwnServer} = {}) {
  validateChoices(choices);
  await verifyInstallPaths(paths, pathPolicy);
  const pathIdentities = await captureInstallPathIdentities(paths, pathPolicy);
  const support = path.resolve(paths.supportDir);
  const runtime = path.resolve(paths.runtimeDir);
  try {
    const installation = JSON.parse(await readFile(paths.installationManifestPath, 'utf8'));
    await verifyRuntimePath(paths, installation.runtimePath ?? '', pathPolicy);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  await assertInstallPathIdentities(pathIdentities, paths.launchAgentPath);
  await bootoutIfLoaded({run, domain: `gui/${uid}`, plistPath: paths.launchAgentPath, label});
  // A `dashboard`-spawned `serve` process holds the SQLite DB open and keeps
  // writing to files under `support`/`runtime` — stop it before the item
  // cleanup subprocess runs against that same runtime, and well before the
  // directories themselves are deleted underneath it (finding #1).
  const serveStopped = await stopOwnServer({pidPath: servePidPath(paths.supportDir)});
  if (!serveStopped.stopped) {
    if (serveStopped.reason === 'no_pid_file') {
      // The pidfile is our primary way to find `serve`'s pid, but its
      // absence is not proof nothing is running — an install from before
      // this mechanism existed, a manually deleted pidfile, or a corrupted
      // write could all leave a real server up with no pidfile to find it
      // by (finding #1-followup). Probe /health directly before trusting
      // "no pidfile" as "nothing to stop".
      const stillAnswering = await probeOwnServer(port).catch(() => null);
      if (stillAnswering) {
        throw Object.assign(new Error(`own_server_stop_failed:no_pid_file_but_still_answering:${stillAnswering.version}`), {code: 'own_server_stop_failed', reason: 'no_pid_file_but_still_answering', version: stillAnswering.version});
      }
    } else {
      throw Object.assign(new Error(`own_server_stop_failed:${serveStopped.reason}`), {code: 'own_server_stop_failed', reason: serveStopped.reason});
    }
  }
  if (choices.items === 'delete') await requestInstalledItemCleanup({paths, pathPolicy, run, nodePath});
  await verifyInstallPaths(paths, pathPolicy);
  await assertInstallPathIdentities(pathIdentities);
  await assertInstallPathIdentities(pathIdentities, paths.launchAgentPath);
  await rm(paths.launchAgentPath, {force: true});
  await assertInstallPathIdentities(pathIdentities, paths.installationManifestPath);
  await rm(paths.installationManifestPath, {force: true});
  if (choices.data === 'delete') {
    await assertInstallPathIdentities(pathIdentities, support);
    await rm(support, {recursive: true, force: true});
  } else {
    await assertInstallPathIdentities(pathIdentities, runtime);
    await rm(runtime, {recursive: true, force: true});
  }
  return {ok: true, dataRetained: choices.data === 'retain', itemsRetained: choices.items === 'retain'};
}

async function main() {
  try {
    const choices = parseUninstallChoice(process.argv.slice(2));
    process.stdout.write(`${JSON.stringify(await uninstall({choices}))}\n`);
  } catch (error) {
    process.stderr.write(`${JSON.stringify({ok: false, error: error.message})}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
