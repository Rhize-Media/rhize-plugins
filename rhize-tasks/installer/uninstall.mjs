import {readFile, rm} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {pathToFileURL} from 'node:url';
import {bootoutIfLoaded} from './launchctl.mjs';
import {defaultInstallPaths} from './install.mjs';
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

function validateOwnedPaths(paths) {
  for (const key of ['supportDir', 'runtimeDir', 'launchAgentPath', 'installationManifestPath']) {
    if (typeof paths?.[key] !== 'string' || paths[key].length === 0) throw new Error(`invalid_uninstall_path_${key}`);
  }
  const support = path.resolve(paths.supportDir);
  const runtime = path.resolve(paths.runtimeDir);
  if (path.basename(support) !== 'Rhize Tasks') throw new Error('unsafe_support_directory');
  if (runtime === support || path.relative(support, runtime).startsWith('..')) throw new Error('unsafe_runtime_directory');
  if (path.resolve(paths.installationManifestPath) !== path.join(support, 'installation.json')) throw new Error('unsafe_installation_manifest');
  if (path.basename(paths.launchAgentPath) !== 'media.rhize.tasks.plist') throw new Error('unsafe_launch_agent_path');
  return {support, runtime};
}

function isInside(parent, child) {
  const relative = path.relative(parent, child);
  return relative.length > 0 && !relative.startsWith('..') && !path.isAbsolute(relative);
}

export async function requestInstalledItemCleanup({paths, run = runProcess, nodePath = process.execPath}) {
  let installation;
  try {
    installation = JSON.parse(await readFile(paths.installationManifestPath, 'utf8'));
  } catch {
    throw new Error('item_cleanup_manifest_invalid');
  }
  const runtime = path.resolve(paths.runtimeDir);
  const runtimePath = path.resolve(installation?.runtimePath ?? '');
  const cliPath = path.resolve(installation?.cliPath ?? '');
  if (installation?.schemaVersion !== 1 || !isInside(path.join(runtime, 'versions'), runtimePath) || cliPath !== path.join(runtimePath, 'service', 'bin', 'rhize-tasks.mjs')) {
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

export async function uninstall({choices, paths = defaultInstallPaths(), run = runProcess, uid = process.getuid?.(), nodePath = process.execPath} = {}) {
  validateChoices(choices);
  const {support, runtime} = validateOwnedPaths(paths);
  await bootoutIfLoaded({run, domain: `gui/${uid}`, plistPath: paths.launchAgentPath});
  if (choices.items === 'delete') await requestInstalledItemCleanup({paths, run, nodePath});
  await rm(paths.launchAgentPath, {force: true});
  await rm(paths.installationManifestPath, {force: true});
  if (choices.data === 'delete') await rm(support, {recursive: true, force: true});
  else await rm(runtime, {recursive: true, force: true});
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
