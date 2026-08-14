import {rm} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {pathToFileURL} from 'node:url';
import {defaultInstallPaths} from './install.mjs';
import {runProcess} from '../service/src/connectors/process-runner.mjs';

export function parseUninstallChoice(args) {
  const retain = args.includes('--retain-data');
  const remove = args.includes('--delete-data');
  if (retain === remove) throw new Error('choose_exactly_one_of_retain_data_or_delete_data');
  if (args.some(arg => !['--retain-data', '--delete-data'].includes(arg))) throw new Error('unknown_uninstall_option');
  return remove ? 'delete' : 'retain';
}

export async function uninstall({choice, paths = defaultInstallPaths(), run = runProcess, uid = process.getuid?.()} = {}) {
  if (!['retain', 'delete'].includes(choice)) throw new Error('explicit_data_choice_required');
  const resolvedSupport = path.resolve(paths.supportDir);
  if (path.basename(resolvedSupport) !== 'Rhize Tasks') throw new Error('unsafe_support_directory');
  const resolvedRuntime = path.resolve(paths.runtimeDir);
  if (path.relative(resolvedSupport, resolvedRuntime).startsWith('..') || resolvedRuntime === resolvedSupport) throw new Error('unsafe_runtime_directory');
  await run('/bin/launchctl', ['bootout', `gui/${uid}`, paths.launchAgentPath], {timeoutMs: 15_000});
  await rm(paths.launchAgentPath, {force: true});
  if (choice === 'delete') await rm(resolvedSupport, {recursive: true, force: true});
  else await rm(paths.runtimeDir, {recursive: true, force: true});
  return {ok: true, dataRetained: choice === 'retain'};
}

async function main() {
  try {
    const choice = parseUninstallChoice(process.argv.slice(2));
    process.stdout.write(`${JSON.stringify(await uninstall({choice}))}\n`);
  } catch (error) {
    process.stderr.write(`${JSON.stringify({ok: false, error: error.message})}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
